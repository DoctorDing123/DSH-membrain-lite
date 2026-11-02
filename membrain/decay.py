# -*- coding: utf-8 -*-
"""遗忘：不是删掉，是「越来越难想起来」。

三层是视觉化的说法：
  habit  —— 反复被想起来的东西（习惯、原则、口头禅）
  fading —— 正常记忆，会慢慢淡
  edge   —— 快要忘掉的边缘记忆
"""

from __future__ import annotations

import math

from .config import Decay

HABIT_HITS = 5          # 被想起 5 次以上，进 habit 层
EDGE_STRENGTH = 0.18    # 强度掉到这个值以下，进 edge 层


def retention(age_days: float, kind: str, decay: Decay) -> float:
    """指数衰减：半衰期按记忆类型给。"""
    half = float(decay.kind_half_life.get(kind, 21.0))
    return 0.5 ** (max(0.0, age_days) / max(1e-6, half))


def reinforce(base: float, hits: int) -> float:
    """每被想起一次，强度往 1.0 靠一点（边际递减）。"""
    boost = 1.0 - math.exp(-max(0, hits) / 4.0)
    return min(1.0, base + 0.35 * boost)


def tier_of(strength: float, hits: int, decay: Decay) -> str:
    if hits >= HABIT_HITS and strength >= decay.fading_strength:
        return "habit"
    if strength <= EDGE_STRENGTH:
        return "edge"
    return "fading"


def step(age_days: float, kind: str, hits: int, decay: Decay) -> tuple[float, str]:
    """算新强度与新层级。tick() 每条记忆都走一遍。"""
    base = retention(age_days, kind, decay)
    strength = reinforce(base, hits)
    return strength, tier_of(strength, hits, decay)
