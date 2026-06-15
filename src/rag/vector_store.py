"""A minimal in-memory cosine-similarity vector store for RAG retrieval."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Sequence

import numpy as np

from src.rag.embeddings import Embedder


@dataclass
class Document:
    """A retrievable document with provenance metadata."""

    doc_id: str
    text: str
    source: str  # "error_corpus" (corpus-specific) | "system_docs" (sample-specific)


@dataclass
class RetrievedDocument:
    """A document returned from a similarity query."""

    document: Document
    score: float


class VectorStore:
    """In-memory store; embeds documents on ``add`` and ranks by cosine similarity."""

    def __init__(self, embedder: Embedder) -> None:
        self._embedder = embedder
        self._docs: List[Document] = []
        self._matrix: Optional[np.ndarray] = None

    def add(self, documents: Sequence[Document]) -> None:
        """Add documents to the store (embeddings are unit-norm, so cosine = dot)."""
        if not documents:
            return
        self._docs.extend(documents)
        embeddings = self._embedder.embed([d.text for d in documents])
        if self._matrix is None:
            self._matrix = embeddings
        else:
            self._matrix = np.vstack([self._matrix, embeddings])

    def query(self, text: str, top_k: int = 3) -> List[RetrievedDocument]:
        """Return the ``top_k`` most similar documents to ``text``."""
        if self._matrix is None or len(self._docs) == 0:
            return []
        q = self._embedder.embed([text])[0]
        scores = self._matrix @ q  # cosine similarity (vectors are unit-norm)
        order = np.argsort(scores)[::-1][:top_k]
        return [
            RetrievedDocument(document=self._docs[i], score=float(scores[i]))
            for i in order
        ]

    def __len__(self) -> int:
        return len(self._docs)


def load_documents_from_dir(directory: str | Path, source: str) -> List[Document]:
    """Load every ``.md``/``.txt`` file under ``directory`` as a :class:`Document`."""
    path = Path(directory)
    docs: List[Document] = []
    if not path.exists():
        return docs
    for file in sorted(path.glob("**/*")):
        if file.suffix.lower() in {".md", ".txt"} and file.is_file():
            docs.append(
                Document(doc_id=file.name, text=file.read_text(), source=source)
            )
    return docs
