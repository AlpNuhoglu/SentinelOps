"""Embedding backends for the RAG vector store.

Two implementations share a common :class:`Embedder` protocol:

* :class:`HashEmbedder` -- deterministic, offline, dependency-free. Hashes token
  n-grams into a fixed-dimension bag-of-words vector. Default for tests/CI.
* :class:`HFEmbedder` -- wraps a real HuggingFace sentence-transformer (e.g.
  ``bge-large-en``). Imported lazily so the heavy dependency is optional.
"""

from __future__ import annotations

import hashlib
import re
from typing import List, Protocol, Sequence

import numpy as np

_TOKEN_RE = re.compile(r"[a-z0-9_]+")


class Embedder(Protocol):
    """Common interface for embedding backends."""

    def embed(self, texts: Sequence[str]) -> np.ndarray:
        """Return an ``(len(texts), dim)`` float32 matrix of unit-norm vectors."""
        ...


def _tokenize(text: str) -> List[str]:
    return _TOKEN_RE.findall(text.lower())


class HashEmbedder:
    """Deterministic hashing embedder (the hashing trick) with L2 normalisation."""

    def __init__(self, dim: int = 256) -> None:
        self.dim = dim

    def _embed_one(self, text: str) -> np.ndarray:
        vec = np.zeros(self.dim, dtype=np.float32)
        tokens = _tokenize(text)
        # Unigrams + bigrams give a little word-order sensitivity.
        grams = tokens + [
            f"{a}_{b}" for a, b in zip(tokens, tokens[1:])
        ]
        for gram in grams:
            digest = hashlib.md5(gram.encode("utf-8")).digest()
            bucket = int.from_bytes(digest[:4], "little") % self.dim
            sign = 1.0 if digest[4] & 1 else -1.0
            vec[bucket] += sign
        norm = float(np.linalg.norm(vec))
        if norm > 0.0:
            vec /= norm
        return vec

    def embed(self, texts: Sequence[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, self.dim), dtype=np.float32)
        return np.vstack([self._embed_one(t) for t in texts])


class HFEmbedder:
    """Real HuggingFace embedder. Requires ``sentence-transformers`` installed."""

    def __init__(self, model_name: str = "BAAI/bge-large-en-v1.5") -> None:
        from sentence_transformers import SentenceTransformer  # lazy import

        self._model = SentenceTransformer(model_name)

    def embed(self, texts: Sequence[str]) -> np.ndarray:
        if not texts:
            dim = int(self._model.get_sentence_embedding_dimension())
            return np.zeros((0, dim), dtype=np.float32)
        arr = self._model.encode(
            list(texts), normalize_embeddings=True, convert_to_numpy=True
        )
        return np.asarray(arr, dtype=np.float32)


def build_embedder(mode: str, hash_dim: int, hf_model_name: str) -> Embedder:
    """Factory: return a :class:`HashEmbedder` (``mode='hash'``) or :class:`HFEmbedder`."""
    if mode == "real":
        return HFEmbedder(hf_model_name)
    return HashEmbedder(dim=hash_dim)
