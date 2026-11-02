# -*- coding: utf-8 -*-
"""配置：一个 toml，全部可覆盖。"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

try:  # py3.11+
    import tomllib as _toml
except ModuleNotFoundError:  # pragma: no cover
    _toml = None


@dataclass
class Weights:
    """五路融合的权重，合计 1.0。

    中文短查询下关键词比余弦更靠谱，所以 keyword 最重；
    语义留给「换个说法也能想起来」；图谱负责「顺藤摸瓜」。
    """

    semantic: float = 0.18
    keyword: float = 0.46
    importance: float = 0.14
    recency: float = 0.11
    graph: float = 0.11

    def total(self) -> float:
        return self.semantic + self.keyword + self.importance + self.recency + self.graph


@dataclass
class Decay:
    """遗忘曲线参数。"""

    recency_half_life_days: float = 14.0
    # 每类记忆的基础半衰期（天）：越「硬」的记忆掉得越慢
    kind_half_life: dict = field(default_factory=lambda: {
        "fact": 365.0,
        "lesson": 240.0,
        "skill": 180.0,
        "episode": 21.0,
        "reflection": 60.0,
    })
    habit_strength: float = 0.62
    fading_strength: float = 0.38
    archive_after_days: float = 400.0


@dataclass
class Config:
    root: Path = field(default_factory=lambda: Path(os.environ.get("MEMBRAIN_HOME", "./.membrain")))
    db: str = "brain.sqlite"
    owner_name: str = "阿宁"
    bot_name: str = "小满"
    port: int = 8765
    weights: Weights = field(default_factory=Weights)
    decay: Decay = field(default_factory=Decay)
    # 去重：同一条意思再写一遍就不要写第二遍
    dedup_similarity: float = 0.92

    @property
    def db_path(self) -> Path:
        return Path(self.root) / self.db

    @classmethod
    def load(cls, path: str | os.PathLike | None = None) -> "Config":
        cfg = cls()
        if path and Path(path).is_file() and _toml is not None:
            with open(path, "rb") as fh:
                data = _toml.load(fh)
            if "root" in data:
                cfg.root = Path(data["root"])
            for key in ("owner_name", "bot_name", "dedup_similarity"):
                if key in data:
                    setattr(cfg, key, data[key])
            if "port" in data:
                cfg.port = int(data["port"])
            if "weights" in data:
                for k, v in data["weights"].items():
                    if hasattr(cfg.weights, k):
                        setattr(cfg.weights, k, float(v))
            if "decay" in data:
                for k, v in data["decay"].items():
                    if k == "kind_half_life":
                        cfg.decay.kind_half_life.update({str(a): float(b) for a, b in v.items()})
                    elif hasattr(cfg.decay, k):
                        setattr(cfg.decay, k, v if isinstance(v, dict) else float(v))
        cfg.root = Path(os.environ.get("MEMBRAIN_HOME", str(cfg.root)))
        return cfg
