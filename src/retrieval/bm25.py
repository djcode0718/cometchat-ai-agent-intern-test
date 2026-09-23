"""BM25 lexical retrieval implementation."""

from typing import List, Optional
from rank_bm25 import BM25Okapi

from src.core.models import KnowledgeChunk
from src.retrieval.base import BaseRetriever
from src.retrieval.models import RetrievalResult
from src.retrieval.tokenizer import tokenize_text


class BM25Index:
    """Manages an in-memory BM25 index over KnowledgeChunk instances."""

    def __init__(
        self,
        chunks: List[KnowledgeChunk],
        k1: float = 1.5,
        b: float = 0.75,
    ) -> None:
        self.chunks = list(chunks)
        self.k1 = k1
        self.b = b
        self._corpus_tokens: List[List[str]] = []
        self._build_index()

    def _build_index(self) -> None:
        """Tokenize chunk titles and content to construct the BM25 index."""
        self._corpus_tokens = [
            tokenize_text(f"{chunk.heading}\n{chunk.content}")
            for chunk in self.chunks
        ]
        if self._corpus_tokens:
            self._bm25 = BM25Okapi(self._corpus_tokens, k1=self.k1, b=self.b)
        else:
            self._bm25 = None

    def query(self, query: str, top_k: int = 5) -> List[RetrievalResult]:
        """Search the BM25 index and return sorted, deterministic top_k RetrievalResults."""
        if not self._bm25 or not self.chunks:
            return []

        query_tokens = tokenize_text(query)
        if not query_tokens:
            return []

        scores = self._bm25.get_scores(query_tokens)

        # Pair scores with chunks and sort deterministically:
        # 1. descending score
        # 2. document_id ascending (tie-breaker)
        # 3. chunk_id ascending (tie-breaker)
        scored_pairs = [
            (float(score), chunk)
            for score, chunk in zip(scores, self.chunks)
            if score > 0.0
        ]

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
                    strategy="bm25",
                )
            )

        return results


class BM25Retriever(BaseRetriever):
    """Retriever adapter wrapping the BM25 index."""

    def __init__(
        self,
        chunks: List[KnowledgeChunk],
        k1: float = 1.5,
        b: float = 0.75,
    ) -> None:
        self.index = BM25Index(chunks=chunks, k1=k1, b=b)

    @property
    def strategy_name(self) -> str:
        return "bm25"

    def retrieve(self, query: str, top_k: int = 5) -> List[RetrievalResult]:
        return self.index.query(query=query, top_k=top_k)
