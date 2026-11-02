#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""提交前自查：仓库里有没有不该出现的东西。

用法：
    python scripts/check_privacy.py
    python scripts/check_privacy.py --json

退出码 0 = 干净，1 = 有命中。
只扫文本文件，跳过 .git / .membrain / __pycache__ / 二进制。

规则设计成“宁可漏报也不要天天误报”：
- 私人称呼：只查你自己加进 DENY_NAMES 的词
- 凭据：Bearer / access_token / cookie / sk- / api_key
- 号码：11 位手机号；以及**同一行带 qq/群号/group/uid 关键词**的 5-12 位数字
- 本机路径：`C:/Users/<你的用户名>`、`/home/<你>`、`/Users/<你>` 这类绝对路径
  （示例里请写 `C:/path/to/...`、`~/...`、`<you>`；这条规则的由来见 docs/PRIVACY.md）
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

SKIP_DIRS = {".git", ".membrain", "__pycache__", ".venv", "node_modules", "dist", "build"}
TEXT_EXT = {".py", ".md", ".jsonl", ".json", ".toml", ".html", ".js", ".css", ".txt", ".yml", ".yaml", ""}

# 检查器自己和说明文档会引用这些词，跳过
SELF_SKIP = {"scripts/check_privacy.py", "docs/PRIVACY.md"}

# 1) 私人称呼：把你机器上用过、绝不该进公开仓库的词加到这里
DENY_NAMES: list[str] = [
    # 例："某个只有我用的昵称",
]

# 2) 凭据形态
SECRET_PATTERNS = [
    (r"Bearer\s+[A-Za-z0-9\-_\.]{12,}", "疑似 Bearer token"),
    (r"(?i)access[_-]?token\s*[=:]\s*[A-Za-z0-9\-_\.]{8,}", "疑似 access_token"),
    (r"(?i)cookie\s*[=:]\s*\S{8,}", "疑似 cookie"),
    (r"\bsk-[A-Za-z0-9]{16,}", "疑似 API key (sk-)"),
    (r"(?i)(api[_-]?key|secret[_-]?key)\s*[=:]\s*['\"]?[A-Za-z0-9]{16,}", "疑似 api key"),
]

# 3) 号码形态
QQ_CTX = re.compile(r"(?i)\b(qq|群号|group[_ ]?id|uid|账号|号码)\b")
PHONE = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")
DIGITS = re.compile(r"(?<![\d.])\d{5,12}(?![\d.])")

# 4) 本机绝对路径（泄露 Windows 用户名 / 家目录名）
#    `C:\Users\<you>`、`/home/<you>`、`/Users/<you>` 这种“真有名字”的才算命中，
#    `<you>` / `<你的用户名>` / `${HOME}` / `~` 这类占位符不算。
WIN_HOME = re.compile(r"[A-Za-z]:\\{1,2}Users\\{1,2}(?![<$\{])[^\\\s'\"]{1,}")
NIX_HOME = re.compile(r"/(?:home|Users)/(?![<$\{])[^/\s'\"]{1,}")


def iter_text_files():
    for p in sorted(ROOT.rglob("*")):
        if p.is_dir():
            continue
        if any(part in SKIP_DIRS for part in p.parts):
            continue
        if p.suffix.lower() not in TEXT_EXT:
            continue
        yield p


def scan() -> list[str]:
    problems: list[str] = []
    for path in iter_text_files():
        rel = path.relative_to(ROOT).as_posix()
        if rel in SELF_SKIP:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        lines = text.splitlines()

        for name in DENY_NAMES:
            for i, line in enumerate(lines, 1):
                if name in line:
                    problems.append(f"{rel}:{i}: 出现私人称呼「{name}」: {line.strip()[:80]}")

        for pattern, label in SECRET_PATTERNS:
            for m in re.finditer(pattern, text):
                line = text[: m.start()].count("\n") + 1
                problems.append(f"{rel}:{line}: {label}")

        for i, line in enumerate(lines, 1):
            if PHONE.search(line):
                problems.append(f"{rel}:{i}: 疑似手机号: {PHONE.search(line).group(0)}")
            if QQ_CTX.search(line):
                m = DIGITS.search(line)
                if m:
                    problems.append(f"{rel}:{i}: 疑似 QQ 号/群号: {m.group(0)}")
            m = WIN_HOME.search(line) or NIX_HOME.search(line)
            if m:
                problems.append(f"{rel}:{i}: 疑似本机家目录路径: {m.group(0)}")
    return problems


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true", help="机器可读输出")
    args = ap.parse_args()

    problems = scan()
    if args.json:
        print(json.dumps({"ok": not problems, "count": len(problems), "items": problems},
                         ensure_ascii=False, indent=2))
    elif not problems:
        print("干净：没发现私人称呼、凭据或号码形态。")
    else:
        for p in problems:
            print("⚠", p)
        print(f"\n共 {len(problems)} 处，确认后再提交。")
    return 0 if not problems else 1


if __name__ == "__main__":
    sys.exit(main())
