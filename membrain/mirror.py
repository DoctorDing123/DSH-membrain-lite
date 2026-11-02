# -*- coding: utf-8 -*-
"""镜像：把库里的记忆写成「人也能读」的 markdown。

为什么要这一步：记忆是给机器检索的，但人是靠翻文件想起东西的。
每天把库导出一遍，出问题时你直接 grep 就能看出她记错了什么。
"""

from __future__ import annotations

import time
from collections import defaultdict
from pathlib import Path

from .engine import Engine


def _day(ts: float) -> str:
    return time.strftime("%Y-%m-%d", time.localtime(ts))


def mirror(engine: Engine, out_dir: str | Path | None = None) -> dict[str, int]:
    root = Path(out_dir or engine.cfg.root) / "mirror"
    root.mkdir(parents=True, exist_ok=True)
    rows = engine.store.all_active()
    by_tier: dict[str, list] = defaultdict(list)
    by_who: dict[str, list] = defaultdict(list)
    by_topic: dict[str, list] = defaultdict(list)
    by_day: dict[str, list] = defaultdict(list)
    for r in rows:
        by_tier[r["tier"]].append(r)
        by_day[_day(float(r["created_at"]))].append(r)
        if r["who"]:
            by_who[r["who"]].append(r)
        if r["topic"]:
            by_topic[r["topic"]].append(r)

    (root / "人物").mkdir(exist_ok=True)
    (root / "话题").mkdir(exist_ok=True)
    (root / "日记").mkdir(exist_ok=True)

    tier_name = {"habit": "习惯", "fading": "可逐渐遗忘", "edge": "边缘"}
    quick = ["# 记忆速查", ""]
    quick.append(f"共 {len(rows)} 条 · 生成于 {time.strftime('%Y-%m-%d %H:%M')}")
    quick.append("")
    for tier, label in (("habit", "习惯"), ("fading", "可逐渐遗忘"), ("edge", "边缘")):
        items = by_tier.get(tier) or []
        quick.append(f"## {label}（{len(items)}）")
        for r in items[:40]:
            quick.append(f"- {r['text']}")
        quick.append("")
    (root / "记忆速查.md").write_text("\n".join(quick), encoding="utf-8")

    for who, items in by_who.items():
        body = [f"# {who}", ""]
        for r in items:
            body.append(f"- [{_day(float(r['created_at']))}] {r['text']}")
            if r["note"]:
                body.append(f"  - 备注：{r['note']}")
        (root / "人物" / f"{who}.md").write_text("\n".join(body), encoding="utf-8")

    for topic, items in by_topic.items():
        body = [f"# {topic}", ""]
        for r in items:
            body.append(f"- [{_day(float(r['created_at']))}] {r['text']}")
        (root / "话题" / f"{topic}.md").write_text("\n".join(body), encoding="utf-8")

    for day, items in by_day.items():
        body = [f"# {day}", ""]
        for r in items:
            body.append(f"- ({r['kind']}) {r['text']}")
        (root / "日记" / f"{day}.md").write_text("\n".join(body), encoding="utf-8")

    return {"total": len(rows), "people": len(by_who), "topics": len(by_topic), "days": len(by_day)}
