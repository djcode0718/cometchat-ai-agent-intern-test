"""Hybrid retriever combining BM25 lexical search and Dense semantic search with RRF."""

from typing import List, Optional

from src.core.models import KnowledgeChunk
from src.retrieval.base import BaseRetriever
from src.retrieval.bm25 import BM25Retriever
from src.retrieval.dense import DenseRetriever
from src.retrieval.embeddings import LocalEmbeddingService
from src.retrieval.fusion import reciprocal_rank_fusion
from src.retrieval.models import RetrievalResult


class HybridRetriever(BaseRetriever):
    """Combines BM25 and Dense semantic retrieval via Reciprocal Rank Fusion."""

    def __init__(
        self,
        chunks: List[KnowledgeChunk],
        bm25_retriever: Optional[BM25Retriever] = None,
        dense_retriever: Optional[DenseRetriever] = None,
        embedding_service: Optional[LocalEmbeddingService] = None,
        rrf_k: int = 60,
    ) -> None:
        self.chunks = list(chunks)
        self.rrf_k = rrf_k
        self.bm25 = bm25_retriever or BM25Retriever(chunks=self.chunks)
        self.dense = dense_retriever or DenseRetriever(
            chunks=self.chunks, embedding_service=embedding_service
        )

    @property
    def strategy_name(self) -> str:
        return "hybrid"

    def retrieve(self, query: str, top_k: int = 5) -> List[RetrievalResult]:
        """Execute BM25 and Dense retrievals and fuse results via RRF."""
        # Retrieve candidate pool from both branches
        candidate_k = max(top_k * 2, 10)
        bm25_results = self.bm25.retrieve(query, top_k=candidate_k)
        dense_results = self.dense.retrieve(query, top_k=candidate_k)

        # Reciprocal Rank Fusion
        fused = reciprocal_rank_fusion(
            ranked_lists=[bm25_results, dense_results],
            k=self.rrf_k,
            top_k=top_k,
        )
        return fused
