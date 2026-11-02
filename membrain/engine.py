# -*- coding: utf-8 -*-
"""引擎：写入、检索、遗忘三件事都在这里。

打分 = 语义*0.18 + 关键词*0.46 + 重要性*0.14 + 新鲜度*0.11 + 图谱*0.11
带 explain=True 时把每一路的分都吐出来，方便你调参、也方便排查
「她为什么想起这个」。
"""

from __future__ import annotations

import math
import struct
import time
from typing import Any, Iterable

from . import decay as decay_mod
from .config import Config
from .embed import Embedder
from .store import Store

INTENT_HINTS = {
    "fact": ("规则", "喜欢", "讨厌", "习惯", "叫什么", "生日", "不能", "永远", "是不是", "会不会"),
    "episode": ("那天", "上次", "当时", "记得", "之前", "昨天", "今天", "说好", "答应", "后来"),
}
KIND_BOOST = 0.05


def _pack(vec: list[float]) -> bytes:
    return struct.pack("<%df" % len(vec), *vec)


def _unpack(blob: bytes) -> list[float]:
    n = len(blob) // 4
    return list(struct.unpack("<%df" % n, blob))


def _cos(a: list[float], b: list[float]) -> float:
    if not a or not b:
        return 0.0
    n = min(len(a), len(b))
    dot = sum(a[i] * b[i] for i in range(n))
    na = math.sqrt(sum(x * x for x in a[:n]))
    nb = math.sqrt(sum(x * x for x in b[:n]))
    return dot / (na * nb) if na and nb else 0.0


def _bigrams(text: str) -> set[str]:
    s = "".join(ch for ch in (text or "").lower() if not ch.isspace())
    return {s[i:i + 2] for i in range(len(s) - 1)} or ({s} if s else set())


class Engine:
    def __init__(self, cfg: Config | None = None, *, embedder: Embedder | None = None):
        self.cfg = cfg or Config()
        self.cfg.root.mkdir(parents=True, exist_ok=True)
        self.store = Store(self.cfg.db_path)
        self.embed = embedder or Embedder()

    # ---------------- 写 ----------------
    def remember(self, text: str, *, kind: str = "episode", scope: str = "default",
                 importance: float = 0.5, who: str | None = None, topic: str | None = None,
                 why: str | None = None, note: str | None = None,
                 entities: Iterable[str] = ()) -> dict[str, Any]:
        """写一条记忆。会被去重：意思重复的只加一次「被想起」。"""
        text = (text or "").strip()
        if not text:
            return {"ok": False, "reason": "empty"}
        now = time.time()
        vec = self.embed(text)
        # 去重：只看同 scope 的最近 200 条（向量一次性取出来做成 map）
        vec_ids, vec_blobs, _dim = self.store.vectors()
        vec_map = {mid: _unpack(blob) for mid, blob in zip(vec_ids, vec_blobs)}
        for row in self.store.all_active(scope, limit=200):
            mid = int(row["id"])
            if row["text"] == text:
                self.store.touch([mid], now)
                return {"ok": True, "id": mid, "deduped": True}
            if abs(float(row["created_at"]) - now) > 86400 * 30:
                continue
            other = vec_map.get(mid) or []
            if other and _cos(vec, other) >= self.cfg.dedup_similarity:
                self.store.touch([mid], now)
                return {"ok": True, "id": mid, "deduped": True}
        mid = self.store.add(
            {"text": text, "kind": kind, "scope": scope, "importance": float(importance),
             "created_at": now, "strength": 0.5, "tier": "fading",
             "who": who, "topic": topic, "why": why, "note": note},
            _pack(vec), len(vec), entities,
        )
        return {"ok": True, "id": mid, "deduped": False}

    # ---------------- 读 ----------------
    def recall(self, query: str, k: int = 5, *, scope: str | None = None,
               explain: bool = False, touch: bool = True,
               now: float | None = None) -> list[dict[str, Any]]:
        now = now or time.time()
        w = self.cfg.weights
        qvec = self.embed(query)
        qbi = _bigrams(query)
        rows = self.store.all_active(scope)
        vec_ids, vec_blobs, _dim = self.store.vectors()
        vmap = {mid: _unpack(blob) for mid, blob in zip(vec_ids, vec_blobs)}

        # 关键词：bigram 重合度；用最大重合数归一，避免长文本吃亏
        kw_scores: dict[int, float] = {}
        for row in rows:
            bi = _bigrams(row["text"])
            if not bi:
                continue
            overlap = len(qbi & bi)
            if overlap:
                kw_scores[int(row["id"])] = overlap / max(1, len(qbi))
        top_kw = sorted(kw_scores.values(), reverse=True)[:60]
        kw_cut = top_kw[-1] if top_kw else 0.0
        seeds = [mid for mid, s in kw_scores.items() if s >= kw_cut][:5]
        neighbors = self.store.neighbors(seeds, limit=30) if seeds else set()
        seed_entities: set[str] = set()
        for mid in seeds:
            seed_entities |= self.store.entities_of(mid)

        out: list[dict[str, Any]] = []
        for row in rows:
            mid = int(row["id"])
            s_sem = max(0.0, _cos(qvec, vmap.get(mid, [])))
            s_kw = kw_scores.get(mid, 0.0)
            s_imp = float(row["importance"])
            age_days = max(0.0, (now - float(row["created_at"])) / 86400.0)
            s_rec = 0.5 ** (age_days / max(1e-6, self.cfg.decay.recency_half_life_days))
            ents = self.store.entities_of(mid)
            s_graph = min(1.0, len(ents & seed_entities) / 3.0) if seed_entities else 0.0
            if mid in neighbors:
                s_graph = max(s_graph, 0.34)

            score = (w.semantic * s_sem + w.keyword * s_kw + w.importance * s_imp
                     + w.recency * s_rec + w.graph * s_graph)
            if score <= 0:
                continue
            item: dict[str, Any] = {
                "id": mid, "text": row["text"], "kind": row["kind"],
                "importance": round(s_imp, 3), "created_at": float(row["created_at"]),
                "score": round(score, 4),
            }
            if explain:
                item["why"] = {
                    "semantic": round(s_sem, 3), "keyword": round(s_kw, 3),
                    "importance": round(s_imp, 3), "recency": round(s_rec, 3),
                    "graph": round(s_graph, 3), "neighbor": mid in neighbors,
                }
            out.append(item)

        out.sort(key=lambda x: x["score"], reverse=True)
        out = self._rerank(query, out)
        top = out[: int(k)]
        if touch and top:
            self.store.touch([x["id"] for x in top], now)
        return top

    def _rerank(self, query: str, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """意图偏好：问规则偏 fact，问往事偏 episode。只加一点点。"""
        q = query or ""
        want = None
        for kind, hints in INTENT_HINTS.items():
            if any(h in q for h in hints):
                want = kind
                break
        if want:
            for r in rows:
                if r["kind"] == want:
                    r["score"] = round(r["score"] + KIND_BOOST, 4)
            rows.sort(key=lambda x: x["score"], reverse=True)
        return rows

    # ---------------- 忘 ----------------
    def tick(self, now: float | None = None) -> dict[str, int]:
        now = now or time.time()
        changed = {"habit": 0, "fading": 0, "edge": 0, "archived": 0}
        for row in self.store.all_active():
            mid = int(row["id"])
            age_days = max(0.0, (now - float(row["created_at"])) / 86400.0)
            strength, tier = decay_mod.step(age_days, row["kind"], int(row["hits"]), self.cfg.decay)
            if tier != row["tier"] or abs(strength - float(row["strength"])) > 0.01:
                self.store.update_strength(mid, tier, strength)
                changed[tier] = changed.get(tier, 0) + 1
        cutoff = now - self.cfg.decay.archive_after_days * 86400
        changed["archived"] = self.store.archive(cutoff)
        return changed

    def brief(self, scope: str | None = None, limit: int = 8) -> str:
        """唤醒时注入的那一小段「你还记得什么」。"""
        rows = self.store.all_active(scope, limit=limit)
        if not rows:
            return ""
        lines = [f"【关于 {self.cfg.owner_name} 的几条硬记忆】"]
        for row in rows:
            lines.append(f"- ({row['kind']}) {row['text']}")
        return "\n".join(lines)

    def close(self) -> None:
        self.store.close()

    def export_rows(self, scope: str | None = None, now: float | None = None) -> list[dict]:
        """导出给可视化用的一行行数据（含实体与轻量分数）。"""
        import time as _time

        now = _time.time() if now is None else now
        rows = self.store.all_active(scope, limit=5000)
        out = []
        for row in rows:
            r = dict(row)
            ents = sorted(self.store.entities_of(r["id"]))
            out.append({
                "id": r["id"],
                "text": r["text"],
                "kind": r["kind"],
                "tier": r["tier"],
                "scope": r["scope"],
                "importance": round(float(r["importance"]), 3),
                "strength": round(float(r["strength"]), 3),
                "hits": int(r["hits"]),
                "who": r.get("who") or "",
                "topic": r.get("topic") or "",
                "created_at": int(r["created_at"]),
                "age_days": round((now - float(r["created_at"])) / 86400.0, 2),
                "entities": ents,
            })
        return out
