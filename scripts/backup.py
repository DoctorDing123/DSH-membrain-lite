# -*- coding: utf-8 -*-
"""备份记忆库，并按份数轮转。

记忆库就是一个 SQLite 文件，备份 = 复制它。但**别用文件复制**：
正在写的时候直接 copy 可能拿到半截的库（尤其是 WAL 模式）。这里用
`sqlite3.Connection.backup()`，它在 SQLite 内部做一致性快照，写的时候也能安全备份。

用法：

    python scripts/backup.py                 # 备份到 <数据目录>/backups，留最近 14 份
    python scripts/backup.py --keep 30       # 留 30 份
    python scripts/backup.py --to D:\\bak     # 换个地方（比如另一个盘 / 网盘同步目录）
    python scripts/backup.py --list          # 只看现有备份，不新建

建议：Windows 用「任务计划程序」每天跑一次；Linux/macOS 用 cron。
这是唯一必须做的运维动作 —— 库丢了，记忆就真没了。
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
import time
from pathlib import Path


def human(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.1f}{unit}" if unit != "B" else f"{n}B"
        n /= 1024.0
    return f"{n:.1f}GB"


def resolve_db() -> Path:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from membrain.config import Config  # noqa: E402

    return Path(Config.load().db_path)


def make_backup(db: Path, out_dir: Path) -> Path:
    if not db.exists():
        raise SystemExit(f"找不到记忆库：{db}\n（先用 `python -m membrain init` 建一个，或者检查 MEMBRAIN_HOME）")
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    dst = out_dir / f"brain-{stamp}.sqlite"

    src = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        dst_con = sqlite3.connect(str(dst))
        try:
            src.backup(dst_con)          # 一致性快照，写的时候也安全
            dst_con.execute("pragma wal_checkpoint(truncate)")
        finally:
            dst_con.close()
    finally:
        src.close()

    # 校验：备份能打开、表在、条数对得上
    src = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    dst_con = sqlite3.connect(f"file:{dst}?mode=ro", uri=True)
    try:
        want = src.execute("select count(*) from memories").fetchone()[0]
        got = dst_con.execute("select count(*) from memories").fetchone()[0]
    finally:
        src.close()
        dst_con.close()
    if want != got:
        raise SystemExit(f"备份校验失败：源 {want} 条，备份 {got} 条（{dst}）")
    print(f"备份完成：{dst}（{want} 条，{human(dst.stat().st_size)}）")
    return dst


def rotate(out_dir: Path, keep: int) -> None:
    files = sorted(out_dir.glob("brain-*.sqlite"))
    if keep <= 0 or len(files) <= keep:
        if files:
            print(f"现有 {len(files)} 份，保留上限 {keep or '不限'}，无需清理。")
        return
    for old in files[: len(files) - keep]:
        old.unlink()
        print(f"删除旧备份：{old.name}")


def show(out_dir: Path) -> None:
    files = sorted(out_dir.glob("brain-*.sqlite"))
    if not files:
        print(f"{out_dir} 里还没有备份。")
        return
    print(f"{out_dir}（{len(files)} 份）")
    for f in files:
        print(f"  {f.name}  {human(f.stat().st_size)}  {time.strftime('%Y-%m-%d %H:%M', time.localtime(f.stat().st_mtime))}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="备份记忆库并按份数轮转")
    ap.add_argument("--to", default="", help="备份目录（默认 <数据目录>/backups）")
    ap.add_argument("--keep", type=int, default=14, help="保留最近几份（默认 14，0 = 不限）")
    ap.add_argument("--list", action="store_true", help="只列出已有备份")
    args = ap.parse_args(argv)

    db = resolve_db()
    out_dir = Path(args.to).expanduser() if args.to else db.parent / "backups"

    if args.list:
        show(out_dir)
        return 0

    make_backup(db, out_dir)
    rotate(out_dir, args.keep)
    show(out_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
