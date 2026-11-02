# -*- coding: utf-8 -*-
"""命令行：一条命令就能跑起来看效果。

    python -m membrain init
    python -m membrain demo
    python -m membrain add "阿宁说他讨厌被叫机器人" --kind fact --who 阿宁
    python -m membrain recall "阿宁讨厌什么" --explain
    python -m membrain tick
    python -m membrain mirror
    python -m membrain eval
    python -m membrain serve
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .config import Config
from .engine import Engine


def _engine(args) -> Engine:
    cfg = Config.load(getattr(args, "config", None))
    return Engine(cfg)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser("membrain")
    ap.add_argument("--config", default=None, help="config.toml 路径")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init")
    p_exp = sub.add_parser("export")
    p_exp.add_argument("--out", default="memories.jsonl")
    p_exp.add_argument("--scope", default=None)
    p_demo = sub.add_parser("demo")
    p_demo.add_argument("--seed", default=str(Path(__file__).parent.parent / "data" / "seed_demo.jsonl"))

    p_add = sub.add_parser("add")
    p_add.add_argument("text")
    p_add.add_argument("--kind", default="episode")
    p_add.add_argument("--scope", default="default")
    p_add.add_argument("--importance", type=float, default=0.5)
    p_add.add_argument("--who", default=None)
    p_add.add_argument("--topic", default=None)
    p_add.add_argument("--note", default=None)

    p_rec = sub.add_parser("recall")
    p_rec.add_argument("query")
    p_rec.add_argument("-k", type=int, default=5)
    p_rec.add_argument("--scope", default=None)
    p_rec.add_argument("--explain", action="store_true")

    sub.add_parser("tick")
    sub.add_parser("counts")
    sub.add_parser("mirror")
    p_eval = sub.add_parser("eval")
    p_eval.add_argument("--cases", default=str(Path(__file__).parent.parent / "eval" / "cases.jsonl"))
    p_srv = sub.add_parser("serve")
    p_srv.add_argument("--port", type=int, default=None)

    args = ap.parse_args(argv)
    eng = _engine(args)

    if args.cmd == "init":
        eng.cfg.root.mkdir(parents=True, exist_ok=True)
        print(f"初始化完成：{eng.cfg.db_path}")
        return 0

    if args.cmd == "demo":
        seed = Path(args.seed)
        if not seed.is_file():
            print("找不到种子数据：", seed)
            return 2
        n = 0
        for line in seed.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            eng.remember(row["text"], kind=row.get("kind", "episode"), scope=row.get("scope", "default"),
                         importance=float(row.get("importance", 0.5)), who=row.get("who"),
                         topic=row.get("topic"), note=row.get("note"),
                         entities=row.get("entities") or ())
            n += 1
        # 让示例铺满三层：重要的进 habit（并被反复想起），次要的落到 edge
        import time as _t
        now = _t.time()
        for r in eng.store.all_active():
            imp = float(r["importance"] or 0.5)
            if imp >= 0.8:
                eng.store.update_strength(r["id"], "habit", 0.88)
                for _ in range(6):
                    eng.store.touch([r["id"]], now)
            elif imp < 0.55:
                eng.store.update_strength(r["id"], "edge", 0.30)
        print(f"写入 {n} 条示例记忆 → {eng.cfg.db_path}")
        print("试着问：python -m membrain recall \"阿宁讨厌什么\" --explain")
        return 0

    if args.cmd == "add":
        res = eng.remember(args.text, kind=args.kind, scope=args.scope,
                           importance=args.importance, who=args.who,
                           topic=args.topic, note=args.note)
        print(json.dumps(res, ensure_ascii=False))
        return 0

    if args.cmd == "recall":
        items = eng.recall(args.query, args.k, scope=args.scope, explain=args.explain)
        for it in items:
            print(f"[{it['score']:.3f}] ({it['kind']}) {it['text']}")
            if args.explain and "why" in it:
                print("        why:", json.dumps(it["why"], ensure_ascii=False))
        if not items:
            print("（没想起来）")
        return 0

    if args.cmd == "tick":
        print(json.dumps(eng.tick(), ensure_ascii=False))
        return 0

    if args.cmd == "counts":
        print(json.dumps(eng.store.counts(), ensure_ascii=False))
        return 0

    if args.cmd == "export":
        rows = eng.export_rows(scope=args.scope)
        out = Path(args.out)
        with out.open("w", encoding="utf-8") as fh:
            for r in rows:
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")
        print(f"导出 {len(rows)} 条 → {out}")
        return 0

    if args.cmd == "mirror":
        from .mirror import mirror

        print(json.dumps(mirror(eng), ensure_ascii=False))
        return 0

    if args.cmd == "eval":
        from .evalrun import run_eval

        return run_eval(eng, args.cases)

    if args.cmd == "serve":
        from .api import serve

        serve(eng, args.port)
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
