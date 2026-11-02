# -*- coding: utf-8 -*-
"""存储：一张表放记忆，一张表放向量，一张表放实体关系。

刻意做得笨：SQLite + 明文 text，随时能 sqlite3 打开看，也随时能删。
"""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any, Iterable

SCHEMA = """
CREATE TABLE IF NOT EXISTS memories (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    text        TEXT NOT NULL,
    kind        TEXT NOT NULL DEFAULT 'episode',
    scope       TEXT NOT NULL DEFAULT 'default',   -- 会话隔离的唯一凭据
    tier        TEXT NOT NULL DEFAULT 'fading',    -- habit / fading / edge
    importance  REAL NOT NULL DEFAULT 0.5,
    strength    REAL NOT NULL DEFAULT 0.5,
    hits        INTEGER NOT NULL DEFAULT 0,
    who         TEXT,
    topic       TEXT,
    why         TEXT,
    note        TEXT,
    created_at  REAL NOT NULL,
    last_hit_at REAL,
    status      TEXT NOT NULL DEFAULT 'active'
);
CREATE INDEX IF NOT EXISTS idx_mem_scope  ON memories(scope, status);
CREATE INDEX IF NOT EXISTS idx_mem_created ON memories(created_at);

CREATE TABLE IF NOT EXISTS vectors (
    memory_id INTEGER PRIMARY KEY REFERENCES memories(id) ON DELETE CASCADE,
    vec       BLOB NOT NULL,
    dim       INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS entities (
    id   INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS links (
    memory_id INTEGER NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
    entity_id INTEGER NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    PRIMARY KEY (memory_id, entity_id)
);

CREATE TABLE IF NOT EXISTS meta (k TEXT PRIMARY KEY, v TEXT);
"""


class Store:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.path))
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    # ---------- 写 ----------
    def add(self, row: dict[str, Any], vec: bytes | None = None, dim: int = 0,
            entities: Iterable[str] = ()) -> int:
        cur = self.conn.execute(
            """INSERT INTO memories
               (text, kind, scope, tier, importance, strength, hits, who, topic, why, note,
                created_at, last_hit_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (row["text"], row.get("kind", "episode"), row.get("scope", "default"),
             row.get("tier", "fading"), float(row.get("importance", 0.5)),
             float(row.get("strength", 0.5)), int(row.get("hits", 0)),
             row.get("who"), row.get("topic"), row.get("why"), row.get("note"),
             float(row.get("created_at", time.time())), row.get("last_hit_at")),
        )
        mid = int(cur.lastrowid)
        if vec is not None:
            self.conn.execute("INSERT INTO vectors(memory_id, vec, dim) VALUES (?,?,?)",
                              (mid, vec, int(dim)))
        for name in entities:
            name = str(name).strip()
            if not name:
                continue
            self.conn.execute("INSERT OR IGNORE INTO entities(name) VALUES (?)", (name,))
            eid = self.conn.execute("SELECT id FROM entities WHERE name=?", (name,)).fetchone()[0]
            self.conn.execute("INSERT OR IGNORE INTO links(memory_id, entity_id) VALUES (?,?)",
                              (mid, eid))
        self.conn.commit()
        return mid

    def touch(self, ids: list[int], now: float | None = None) -> None:
        now = now or time.time()
        for mid in ids:
            self.conn.execute(
                "UPDATE memories SET hits = hits + 1, last_hit_at = ? WHERE id = ?", (now, mid))
        self.conn.commit()

    def update_strength(self, mid: int, tier: str, strength: float) -> None:
        self.conn.execute("UPDATE memories SET tier=?, strength=? WHERE id=?",
                          (tier, float(strength), mid))

    def archive(self, older_than: float) -> int:
        cur = self.conn.execute(
            "UPDATE memories SET status='archived' WHERE status='active' AND created_at < ?",
            (older_than,))
        self.conn.commit()
        return cur.rowcount

    # ---------- 读 ----------
    def all_active(self, scope: str | None = None, limit: int = 5000) -> list[sqlite3.Row]:
        sql = "SELECT * FROM memories WHERE status='active'"
        args: list[Any] = []
        if scope is not None:
            sql += " AND (scope = ? OR scope = 'global')"
            args.append(scope)
        sql += " ORDER BY created_at DESC LIMIT ?"
        args.append(limit)
        return list(self.conn.execute(sql, args))

    def get(self, mid: int) -> sqlite3.Row | None:
        return self.conn.execute("SELECT * FROM memories WHERE id=?", (mid,)).fetchone()

    def vectors(self) -> tuple[list[int], list[bytes], int]:
        ids, blobs, dim = [], [], 0
        for r in self.conn.execute("SELECT memory_id, vec, dim FROM vectors"):
            ids.append(int(r["memory_id"]))
            blobs.append(bytes(r["vec"]))
            dim = int(r["dim"])
        return ids, blobs, dim

    def entities_of(self, mid: int) -> set[str]:
        rows = self.conn.execute(
            "SELECT e.name FROM links l JOIN entities e ON e.id=l.entity_id WHERE l.memory_id=?",
            (mid,))
        return {r[0] for r in rows}

    def neighbors(self, mids: Iterable[int], limit: int = 30) -> set[int]:
        mids = [int(m) for m in mids]
        if not mids:
            return set()
        q = ",".join("?" * len(mids))
        rows = self.conn.execute(
            f"""SELECT DISTINCT l2.memory_id, COUNT(*) c
                FROM links l1 JOIN links l2 ON l2.entity_id = l1.entity_id
                WHERE l1.memory_id IN ({q}) AND l2.memory_id NOT IN ({q})
                GROUP BY l2.memory_id ORDER BY c DESC LIMIT ?""",
            (*mids, *mids, int(limit)))
        return {int(r[0]) for r in rows}

    def counts(self) -> dict[str, int]:
        out = {}
        for r in self.conn.execute("SELECT tier, COUNT(*) c FROM memories WHERE status='active' GROUP BY tier"):
            out[str(r["tier"])] = int(r["c"])
        out["total"] = int(self.conn.execute(
            "SELECT COUNT(*) FROM memories WHERE status='active'").fetchone()[0])
        return out

    def set_meta(self, k: str, v: Any) -> None:
        self.conn.execute("INSERT INTO meta(k,v) VALUES(?,?) ON CONFLICT(k) DO UPDATE SET v=excluded.v",
                          (k, json.dumps(v, ensure_ascii=False)))
        self.conn.commit()

    def close(self) -> None:
        try:
            self.conn.close()
        except Exception:  # noqa: BLE001
            pass
