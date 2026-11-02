#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""检查仓库里的“死引用”：文档链到的文件在不在、外链还能不能开。

用法：
    python scripts/check_links.py              # 全查（含外链 HTTP）
    python scripts/check_links.py --offline    # 只查本地文件，不联网
    python scripts/check_links.py --json       # 机器可读

退出码 0 = 没发现问题，1 = 有 404 / 缺文件。

判定口径：
- 本地相对链接（文档之间互相链、图片路径）：文件必须存在，否则算错误。
- 反引号里的路径（如 `scripts/backup.py`）：只在它以已知目录开头时检查，
  避免把 `~/.membrain`、`C:/path/to/...` 这类示例当成本仓库文件。
- 外链 http(s)：HEAD 请求，>=400 算错误；403 / 429 只算警告（对方限流）。
- 带 `<...>`、`${...}`、`~` 的占位符一律跳过 —— 那是给读者替换的示例。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

SKIP_DIRS = {".git", ".membrain", "__pycache__", ".venv", "node_modules", "dist", "build", ".mypy_cache"}

DOC_FILES = ["README.md"] + [p.relative_to(ROOT).as_posix() for p in sorted((ROOT / "docs").glob("*.md"))]

# 仓库里必须存在的骨架文件（少了就是安装不完整）
REQUIRED_PATTERNS = [
    "LICENSE",
    "pyproject.toml",
    "config.example.toml",
    "README.md",
    "membrain/__init__.py",
    "membrain/engine.py",
    "membrain/mcp.py",
    "membrain/cli.py",
    "prompts/*.md",
    "data/seed_demo.jsonl",
    "eval/cases.jsonl",
    "examples/radial/index.html",
    "scripts/check_privacy.py",
    "tests/test_core.py",
]

# 反引号里的路径，只有以这些前缀开头才当“仓库内路径”校验
REPO_PREFIXES = ("membrain/", "scripts/", "prompts/", "docs/", "examples/", "data/", "eval/", "tests/")

MD_LINK = re.compile(r"!?\[[^\]]*\]\(\s*(<[^>]*>|[^)\s]+)(?:\s+[\"'][^)]*[\"'])?\s*\)")
HTML_ATTR = re.compile(r'(?:src|href)\s*=\s*["\']([^"\']+)["\']')
CODE_SPAN = re.compile(r"`([^`\n]{2,120})`")
BARE_URL = re.compile(r"https?://[^\s\)\]\"'<>`]+")
PLACEHOLDER = re.compile(r"[<${}~]")


def iter_docs():
    for rel in DOC_FILES:
        p = ROOT / rel
        if p.is_file():
            yield p


def is_placeholder(target: str) -> bool:
    return bool(PLACEHOLDER.search(target))


LOOPBACK_HOSTS = ("127.", "localhost", "0.0.0.0", "::1", "192.168.", "10.", "172.16.", "172.17.",
                  "172.18.", "172.19.", "172.2", "172.30.", "172.31.")


def is_local_host(url: str) -> bool:
    """本机/内网地址：只有自己开着服务才通，不该算 404。"""
    host = url.split("://", 1)[-1].split("/", 1)[0].split(":", 1)[0].lower()
    return host.startswith(LOOPBACK_HOSTS)


def norm(target: str) -> str:
    t = target.strip()
    if t.startswith("<") and t.endswith(">"):
        t = t[1:-1].strip()
    t = t.split("#", 1)[0]
    t = t.split("?", 1)[0]
    return t.strip()


def check_external(url: str, timeout: float) -> tuple[str, str]:
    """返回 (level, message)，level in ok/warn/error。"""
    req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "membrain-lite-linkcheck/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return "ok", f"{r.status}"
    except urllib.error.HTTPError as e:
        if e.code in (403, 429):
            return "warn", f"{e.code}（可能只是限流）"
        if e.code == 405:  # 有些站点不支持 HEAD
            try:
                req2 = urllib.request.Request(url, headers={"User-Agent": "membrain-lite-linkcheck/1.0"})
                with urllib.request.urlopen(req2, timeout=timeout) as r:
                    return "ok", f"{r.status}"
            except urllib.error.HTTPError as e2:
                return ("warn" if e2.code in (403, 429) else "error"), f"{e2.code}"
            except Exception as e2:  # noqa: BLE001
                return "error", f"{type(e2).__name__}"
        return "error", f"{e.code}"
    except urllib.error.URLError as e:
        return "error", f"连不上：{getattr(e, 'reason', e)}"
    except Exception as e:  # noqa: BLE001
        return "error", f"{type(e).__name__}"


def scan(offline: bool, timeout: float):
    problems: list[dict] = []
    warnings: list[dict] = []
    external: dict[str, tuple[str, str]] = {}
    checked_local = 0

    for rel_required in REQUIRED_PATTERNS:
        hits = list(ROOT.glob(rel_required))
        if not hits:
            problems.append({"where": rel_required, "kind": "missing-file", "detail": "骨架文件不存在"})

    for path in iter_docs():
        rel = path.relative_to(ROOT).as_posix()
        text = path.read_text(encoding="utf-8")
        targets: list[tuple[int, str]] = []

        # 代码块里的示例路径/假路径不算引用（与常见链接检查器一致）
        fenced: set[int] = set()
        in_fence = False
        for i, line in enumerate(text.splitlines(), 1):
            if line.lstrip().startswith(("```", "~~~")):
                in_fence = not in_fence
                fenced.add(i)
                continue
            if in_fence:
                fenced.add(i)

        for m in MD_LINK.finditer(text):
            targets.append((text[: m.start()].count("\n") + 1, m.group(1), "link"))
        for m in HTML_ATTR.finditer(text):
            targets.append((text[: m.start()].count("\n") + 1, m.group(1), "link"))
        for m in CODE_SPAN.finditer(text):
            span = m.group(1).strip()
            if span in REQUIRED_PATTERNS or span.startswith(REPO_PREFIXES):
                targets.append((text[: m.start()].count("\n") + 1, span, "code"))
        for m in BARE_URL.finditer(text):
            targets.append((text[: m.start()].count("\n") + 1, m.group(0), "bare"))

        for line_no, raw, kind in targets:
            if line_no in fenced:
                continue
            if is_placeholder(raw):
                continue
            target = norm(raw)
            if not target:
                continue
            if "*" in target:
                continue  # 通配符（`docs/*.md`）是叙述，不是单一文件
            if kind == "code" and ("–" in target or "—" in target or " " in target or target.endswith("/")):
                continue  # `prompts/01–05`、`docs/` 这类是叙述，不是文件
            if target.startswith(("http://", "https://")):
                if offline or is_local_host(target):
                    continue
                if target not in external:
                    external[target] = check_external(target, timeout)
                level, detail = external[target]
                item = {"where": f"{rel}:{line_no}", "kind": "external", "target": target, "detail": detail}
                (problems if level == "error" else warnings if level == "warn" else []).append(item)
                continue
            if target.startswith(("mailto:", "tel:", "#")):
                continue
            if target.startswith("/"):  # 站内绝对路径，本仓库不管
                continue
            checked_local += 1
            if kind == "code":
                candidates = [(ROOT / target).resolve()]
            else:
                candidates = [(path.parent / target).resolve(), (ROOT / target).resolve()]
            if not any(c.exists() for c in candidates):
                problems.append({"where": f"{rel}:{line_no}", "kind": "broken-link", "target": target, "detail": "文件不存在"})

    return problems, warnings, checked_local, len(external)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true", help="不检查外链")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--timeout", type=float, default=8.0)
    args = ap.parse_args()

    problems, warnings, n_local, n_ext = scan(args.offline, args.timeout)

    if args.json:
        print(json.dumps(
            {"ok": not problems, "problems": problems, "warnings": warnings,
             "checked_local": n_local, "checked_external": n_ext},
            ensure_ascii=False, indent=2))
    else:
        for w in warnings:
            print(f"⚠ {w['where']}: {w.get('target', '')} → {w['detail']}")
        for p in problems:
            print(f"✗ {p['where']}: {p['kind']}: {p.get('target', '')} → {p['detail']}")
        tail = f"本地引用 {n_local} 个" + ("" if args.offline else f"、外链 {n_ext} 个")
        if problems:
            print(f"\n共 {len(problems)} 处 404 / 缺文件（{tail}）。修好再提交。")
        else:
            print(f"没问题：{tail}，全部可达。")
    return 0 if not problems else 1


if __name__ == "__main__":
    sys.exit(main())
