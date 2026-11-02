# -*- coding: utf-8 -*-
"""向量：默认零依赖（char-bigram 哈希），可选换成真模型。

为什么默认不用 bge-m3：开源骨架要能 `pip install` 完就跑，
不能让人先下 2GB 模型。真上线时把 embed() 换成 bge-m3 / text2vec 即可，
接口只有「文本 -> float32 向量」这一个约定。
"""

from __future__ import annotations

import hashlib
import re
from typing import Callable

DIM = 512
_WORD = re.compile(r"[a-z0-9]+|[\u4e00-\u9fff]")


def _tokens(text: str) -> list[str]:
    s = (text or "").lower()
    toks = []
    raw = _WORD.findall(s)
    for i, t in enumerate(raw):
        toks.append(t)
        if i + 1 < len(raw):
            toks.append(t + raw[i + 1])  # bigram：中文最稳的最小单位
    return toks


def _hash_embed(text: str, dim: int = DIM) -> list[float]:
    vec = [0.0] * dim
    for tok in _tokens(text):
        h = hashlib.blake2b(tok.encode("utf-8"), digest_size=8).digest()
        idx = int.from_bytes(h[:4], "little") % dim
        sign = 1.0 if h[4] & 1 else -1.0
        vec[idx] += sign
    norm = sum(v * v for v in vec) ** 0.5
    return [v / norm for v in vec] if norm else vec


class Embedder:
    """优先用外部模型，失败就回落到哈希向量。"""

    def __init__(self, model: str | None = None):
        self.model = model
        self._fn: Callable[[str], list[float]] = lambda t: _hash_embed(t)
        if model:
            try:
                from sentence_transformers import SentenceTransformer  # type: ignore

                st = SentenceTransformer(model)
                self._fn = lambda t: [float(x) for x in st.encode(t, normalize_embeddings=True)]
            except Exception:  # noqa: BLE001
                self._fn = lambda t: _hash_embed(t)

    def __call__(self, text: str) -> list[float]:
        return self._fn(text)

    @staticmethod
    def dim(vec: list[float]) -> int:
        return len(vec)
