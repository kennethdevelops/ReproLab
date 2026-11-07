"""Embedding providers (ADR-0002).

Local fastembed is the default. `hashing` is a deterministic, dependency-free embedder for offline
tests and CI. It is a bag-of-tokens model, not a semantic one, and benchmark results produced
with it must say so.
"""

from __future__ import annotations

import hashlib
import math
import re
from collections.abc import Sequence
from functools import lru_cache
from typing import Any, Protocol

from reprolab.config.settings import Settings, get_settings


class Embedder(Protocol):
    model_id: str
    dim: int

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]: ...

    def embed_query(self, text: str) -> list[float]: ...


_TOKEN = re.compile(r"[A-Z]?[a-z]+|[A-Z]+(?![a-z])|\d+")


class HashingEmbedder:
    def __init__(self, dim: int = 256) -> None:
        self.dim = dim
        self.model_id = f"hashing-{dim}"

    def _vector(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        for token in _TOKEN.findall(text):
            t = token.lower()
            if len(t) < 2:
                continue
            h = int.from_bytes(hashlib.blake2b(t.encode(), digest_size=8).digest(), "big")
            vec[h % self.dim] += 1.0 if (h >> 63) & 1 else -1.0
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        return [self._vector(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._vector(text)


class FastEmbedEmbedder:
    """Runs locally (ONNX). The model is downloaded once on first use, then cached."""

    def __init__(self, model: str, cache_dir: str | None = None, batch_size: int = 32) -> None:
        from fastembed import TextEmbedding

        self.model_id = model
        self._model: Any = TextEmbedding(model_name=model, cache_dir=cache_dir)
        self._batch = batch_size
        self.dim = len(self.embed_query("dimension probe"))

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        vectors = self._model.passage_embed(list(texts), batch_size=self._batch)
        return [[float(x) for x in v] for v in vectors]

    def embed_query(self, text: str) -> list[float]:
        return [float(x) for x in next(iter(self._model.query_embed(text)))]


@lru_cache(maxsize=4)
def _build(provider: str, model: str, cache_dir: str | None) -> Embedder:
    if provider == "hashing":
        return HashingEmbedder()
    if provider == "fastembed":
        return FastEmbedEmbedder(model, cache_dir)
    raise ValueError(f"unknown embedding provider {provider!r}")


def get_embedder(settings: Settings | None = None) -> Embedder:
    s = settings or get_settings()
    cache = str(s.embedding_cache_dir) if s.embedding_cache_dir else None
    return _build(s.embedding_provider, s.embedding_model, cache)
