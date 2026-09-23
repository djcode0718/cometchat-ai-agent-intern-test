"""Dense semantic vector index and retriever implementation."""

from typing import List, Optional
import numpy as np

from src.core.models import KnowledgeChunk
from src.retrieval.base import BaseRetriever
from src.retrieval.embeddings import LocalEmbeddingService
from src.retrieval.models import RetrievalResult


class DenseIndex:
    """In-memory dense vector index over KnowledgeChunk instances."""

    def __init__(
        self,
        chunks: List[KnowledgeChunk],
        embedding_service: Optional[LocalEmbeddingService] = None,
    ) -> None:
        self.chunks = list(chunks)
        self.embedding_service = embedding_service or LocalEmbeddingService()
        self._vectors: Optional[np.ndarray] = None
        self._build_index()

    def _build_index(self) -> None:
        """Encode all chunks and cache the normalized vector matrix."""
        if not self.chunks:
            self._vectors = np.empty((0, 384), dtype=np.float32)
            return

        texts = [f"{chunk.heading}\n{chunk.content}" for chunk in self.chunks]
        self._vectors = self.embedding_service.encode(texts)

    def query(self, query: str, top_k: int = 5) -> List[RetrievalResult]:
        """Search dense index by cosine similarity and return deterministic top_k results."""
        if self._vectors is None or len(self.chunks) == 0:
            return []

        if not query.strip():
            return []

        query_vec = self.embedding_service.encode_query(query)
        # Cosine similarity via dot product (both vectors and query_vec are L2-normalized)
        similarities = np.dot(self._vectors, query_vec)

        scored_pairs = [
            (float(sim), chunk)
            for sim, chunk in zip(similarities, self.chunks)
        ]

        # Deterministic sort: score desc, doc_id asc, chunk_id asc
        scored_pairs.sort(
            key=lambda item: (-item[0], item[1].document_id, item[1].chunk_id)
        )

        results: List[RetrievalResult] = []
        for rank, (score, chunk) in enumerate(scored_pairs[:top_k], start=1):
            results.append(
                RetrievalResult(
                    chunk=chunk,
                    score=score,
                    rank=rank,
                    strategy="dense",
                )
            )

        return results


class DenseRetriever(BaseRetriever):
    """Retriever adapter wrapping the dense semantic index."""

    def __init__(
        self,
        chunks: List[KnowledgeChunk],
        embedding_service: Optional[LocalEmbeddingService] = None,
    ) -> None:
        self.index = DenseIndex(chunks=chunks, embedding_service=embedding_service)

    @property
    def strategy_name(self) -> str:
        return "dense"

    def retrieve(self, query: str, top_k: int = 5) -> List[RetrievalResult]:
        return self.index.query(query=query, top_k=top_k)
