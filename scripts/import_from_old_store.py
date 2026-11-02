# -*- coding: utf-8 -*-
"""从「旧记忆库」一次性迁移到本库。

适用场景：你原来有一支自己写的记忆库（比如一个叫 brain.db 的 SQLite），
想把它里面**非隐私**的部分搬进 membrain-lite，而不是从零开始。

设计原则（很重要，别改）：
1. **只读源库**。用 `file:...?mode=ro` 打开，绝不写回去。
2. **默认不导私聊**。私聊记忆跨会话泄漏是最严重的事故，必须显式 `--include-private`
   或用 `--private-allow` 点名才导。
3. **号码不删**。QQ 号 / 群号 / 条目编号是「认人」的依据，本地库原样保留；
   只是提醒你：将来要把这支库分享出去之前，先跑 `scripts/check_privacy.py`。
4. **先 `--dry` 看分布，再实跑**。不带 `--dry` 就直接写。

用法：

    # 1) 先看会导什么、会跳过什么（不写盘）
    python scripts/import_from_old_store.py --from ~/old/brain.db --dry

    # 2) 确认无误后实跑（写入 MEMBRAIN_HOME 指向的库）
    python scripts/import_from_old_store.py --from ~/old/brain.db

    # 3) 顺便扫一遍号码类文本
    python scripts/import_from_old_store.py --from ~/old/brain.db --dry --scan-secrets

    # 4) 只想导某一个私聊
    python scripts/import_from_old_store.py --from ~/old/brain.db --private-allow private:100000002
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import sys
from pathlib import Path

# ---- kind 映射：旧库的叫法 → 本库的五类 -------------------------------------
KIND_MAP = {
    "episode": "episode",
    "fact": "fact",
    "lesson": "lesson",
    "reflection": "reflection",
    "skill": "skill",
    # 常见别名
    "procedural": "skill",     # 程序性记忆 → 技能
    "procedure": "skill",
    "change": "reflection",    # 「我身上的变化」本质是反思
    "preference": "fact",      # 偏好当事实记，重要的给高 importance
    "pref": "fact",
    "topic": "fact",
    "relation": "fact",
    "habit": "lesson",
}

# 旧库里「没有 chat 字段、但属于机器人自己」的 source 值
DEFAULT_SELF_SOURCES = {
    "agent", "agent:habit", "nightly:lesson", "abstract", "reflection", "master",
}

# 隐私扫描：只看形态，不联网
SECRET_PATTERNS = {
    "secret": re.compile(r"(?i)\b(api[_-]?key|secret|token|passwd|password)\b\s*[:=]\s*\S{8,}"),
    "email": re.compile(r"[\w.+-]+@[\w-]+\.[\w.]{2,}"),
    "cn_mobile": re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)"),
    "url": re.compile(r"https?://\S+"),
    "qq_or_longnum": re.compile(r"(?<!\d)\d{6,}(?!\d)"),
}


def _table_columns(con: sqlite3.Connection, table: str) -> set[str]:
    try:
        return {r[1] for r in con.execute(f"pragma table_info({table})")}
    except sqlite3.Error:
        return set()


def _chat_expr(cols: set[str]) -> str:
    """旧库把 chat 放在哪，取决于实现：有的单列，有的塞 meta JSON。"""
    if "chat" in cols:
        return "coalesce(chat,'')"
    if "meta" in cols:
        return "coalesce(json_extract(meta,'$.chat'),'')"
    return "''"


def load_source(path: Path) -> list[sqlite3.Row]:
    if not path.exists():
        raise SystemExit(f"源库不存在：{path}")
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    cols = _table_columns(con, "memories")
    if not cols:
        raise SystemExit("源库里没有 memories 表，这个脚本只认「一张 memories 表」的结构。")

    chat = _chat_expr(cols)
    wanted = ["id", "text", "kind", "importance"]
    select = [c if c in cols else f"null as {c}" for c in wanted]
    select.append(chat + " as chat")
    select.append("coalesce(source,'') as source" if "source" in cols else "'' as source")
    select.append("coalesce(note,'') as note" if "note" in cols else "'' as note")
    select.append("coalesce(status,'active') as status" if "status" in cols else "'active' as status")

    rows = list(con.execute(f"select {', '.join(select)} from memories order by id"))
    con.close()
    return rows


def pick(rows, include_private: bool, private_allow: set[str], self_sources: set[str]):
    picked, skipped = [], {"archived": 0, "empty": 0, "other_chat": 0, "bad_kind": 0}
    for r in rows:
        if (r["status"] or "") == "archived":
            skipped["archived"] += 1
            continue
        text = (r["text"] or "").strip()
        if not text:
            skipped["empty"] += 1
            continue

        chat = (r["chat"] or "").strip()
        source = (r["source"] or "").strip()
        if chat.startswith("group:"):
            scope = chat
        elif chat.startswith("private:"):
            if not (include_private or chat in private_allow):
                skipped["other_chat"] += 1
                continue
            scope = chat
        elif chat == "" and (source in self_sources or source.startswith("agent")):
            scope = "self"
        else:
            skipped["other_chat"] += 1
            continue

        kind = KIND_MAP.get((r["kind"] or "").strip())
        if not kind:
            skipped["bad_kind"] += 1
            continue

        try:
            imp = float(r["importance"] or 0.5)
        except (TypeError, ValueError):
            imp = 0.5
        picked.append({
            "src_id": r["id"],
            "text": text,
            "kind": kind,
            "scope": scope,
            "importance": max(0.05, min(1.0, imp)),
            "note": (r["note"] or "").strip() or None,
        })
    return picked, skipped


def scan(texts: list[str]) -> dict[str, list[int]]:
    hits: dict[str, list[int]] = {k: [] for k in SECRET_PATTERNS}
    for i, t in enumerate(texts):
        for name, pat in SECRET_PATTERNS.items():
            if pat.search(t):
                hits[name].append(i)
    return hits


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="把旧记忆库迁移进 membrain-lite（只读源库）")
    ap.add_argument("--from", dest="src", required=True, help="旧库路径（SQLite，含 memories 表）")
    ap.add_argument("--dry", action="store_true", help="只打印分布和抽样，不写盘")
    ap.add_argument("--include-private", action="store_true", help="连私聊一起导（默认不导）")
    ap.add_argument("--private-allow", default="", help="只导这些私聊，逗号分隔，如 private:100000002")
    ap.add_argument("--self-scope", default="self", help="机器人自身记忆归到哪个 scope（默认 self）")
    ap.add_argument("--scan-secrets", action="store_true", help="扫描号码/凭据形态并给出条数")
    ap.add_argument("--no-backfill", action="store_true", help="不按 importance 回填 hits（默认回填）")
    ap.add_argument("--no-tick", action="store_true", help="导完不跑一次 tick（默认跑）")
    args = ap.parse_args(argv)

    rows = load_source(Path(args.src).expanduser())
    private_allow = {s.strip() for s in args.private_allow.split(",") if s.strip()}
    picked, skipped = pick(rows, args.include_private, private_allow, DEFAULT_SELF_SOURCES)
    for p in picked:
        if p["scope"] == "self":
            p["scope"] = args.self_scope

    print(f"源库 {len(rows)} 条 → 候选 {len(picked)} 条；跳过 {skipped}")
    per_scope: dict[str, int] = {}
    per_kind: dict[str, int] = {}
    for p in picked:
        per_scope[p["scope"]] = per_scope.get(p["scope"], 0) + 1
        per_kind[p["kind"]] = per_kind.get(p["kind"], 0) + 1
    print("  按 scope：" + ", ".join(f"{k} {v}" for k, v in sorted(per_scope.items(), key=lambda kv: -kv[1])))
    print("  按 kind ：" + ", ".join(f"{k} {v}" for k, v in sorted(per_kind.items(), key=lambda kv: -kv[1])))

    if args.scan_secrets:
        hits = scan([p["text"] for p in picked])
        print("  隐私扫描：" + ", ".join(f"{k} {len(v)}" for k, v in hits.items()))
        for name, idx in hits.items():
            if name.startswith("secret") and idx:
                print(f"    ⚠️ {name} 命中 {len(idx)} 条，实跑前请先看：")
                for i in idx[:3]:
                    print("       " + picked[i]["text"][:80])

    if args.dry:
        print("\n[dry] 抽样 5 条（不写盘）：")
        for p in picked[:5]:
            print(f"   #{p['src_id']} [{p['scope']}/{p['kind']} {p['importance']:.2f}] {p['text'][:60]}")
        return 0

    # 这里才 import，保证 --dry 不需要 membrain 装好
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from membrain.config import Config  # noqa: E402
    from membrain.engine import Engine  # noqa: E402

    cfg = Config.load()
    eng = Engine(cfg)

    added = deduped = failed = 0
    for p in picked:
        res = eng.remember(
            p["text"], kind=p["kind"], scope=p["scope"],
            importance=p["importance"], note=p["note"],
        )
        if not res.get("ok"):
            failed += 1
            print(f"   失败 #{p['src_id']}: {res}")
        elif res.get("deduped"):
            deduped += 1
        else:
            added += 1
    if not args.no_backfill:
        _backfill_hits(eng.store)
    if not args.no_tick:
        eng.tick()

    print(f"\n写入 {added} 条，去重跳过 {deduped} 条，失败 {failed} 条")
    print("库统计：", json.dumps(eng.store.counts(), ensure_ascii=False))
    print("数据目录：", cfg.db_path)
    eng.close()
    return 0


def _backfill_hits(store) -> None:
    """旧库没记「被想起过几次」，但它的 importance 本身就含这个信息。

    不补的话，导进来全部落在 fading 层 —— 明明是天天提起的事，看起来像第一次听说。
    这里按 importance 反推一个 hits（0.86 → 5 次，够到 HABIT_HITS 进习惯层）。
    """
    cur = store.conn.execute(
        "update memories set hits = max(0, cast(round(importance*6) as int)) "
        "where hits = 0 and status != 'archived'"
    )
    store.conn.commit()
    print(f"回填 hits：{cur.rowcount} 行（按 importance 反推）")


if __name__ == "__main__":
    raise SystemExit(main())
