# -*- coding: utf-8 -*-
"""评估：40 条问答，算 recall@1 / recall@3。

这不是为了刷分，是为了**改权重的时知道自己在干什么**。
换一次权重就跑一遍，掉分了就退回。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from .engine import Engine


def run_eval(engine: Engine, cases_path: str | Path) -> int:
    p = Path(cases_path)
    if not p.is_file():
        print("找不到评估集：", p)
        return 2
    total = hit1 = hit3 = 0
    misses = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        case = json.loads(line)
        total += 1
        items = engine.recall(case["query"], 3, scope=case.get("scope"), touch=False)
        keys = [c["text"] for c in case["expect"]]
        got = [it["text"] for it in items]
        if got[:1] and any(k in got[0] for k in keys):
            hit1 += 1
        if any(any(k in g for k in keys) for g in got):
            hit3 += 1
        else:
            misses.append((case["query"], keys, got))
    r1 = hit1 / total if total else 0.0
    r3 = hit3 / total if total else 0.0
    print(f"cases={total}  recall@1={r1:.1%}  recall@3={r3:.1%}")
    for q, keys, got in misses[:8]:
        print("  MISS:", q)
        print("    期望:", keys)
        print("    拿到:", got)
    return 0 if r3 >= 0.8 else 1
