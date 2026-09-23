"""Reciprocal Rank Fusion (RRF) for combining multiple retrieval rankings."""

from collections import defaultdict
from typing import Dict, List, Optional, Tuple

from src.core.models import KnowledgeChunk
from src.retrieval.models import RetrievalResult


def reciprocal_rank_fusion(
    ranked_lists: List[List[RetrievalResult]],
    k: int = 60,
    top_k: Optional[int] = None,
) -> List[RetrievalResult]:
    """Fuse multiple ranked lists of RetrievalResult using Reciprocal Rank Fusion (RRF).

    For each chunk d:
        RRF_score(d) = sum_{r in rankings} 1 / (k + rank_r(d))

    Args:
        ranked_lists: List of ranked RetrievalResult lists from individual retrievers.
        k: Smoothing constant (default: 60).
        top_k: Maximum number of fused results to return.

    Returns:
        Unified, deterministically ranked list of RetrievalResult with strategy="hybrid".
    """
    if not ranked_lists:
        return []

    # Map chunk_id -> (cumulative_rrf_score, KnowledgeChunk)
    scores: Dict[str, float] = defaultdict(float)
    chunk_map: Dict[str, KnowledgeChunk] = {}

    for ranked_list in ranked_lists:
        for item in ranked_list:
            cid = item.chunk.chunk_id
            chunk_map[cid] = item.chunk
            # item.rank is 1-indexed rank from individual retriever
            scores[cid] += 1.0 / (k + item.rank)

    # Convert to list of (score, KnowledgeChunk)
    scored_items: List[Tuple[float, KnowledgeChunk]] = [
        (score, chunk_map[cid]) for cid, score in scores.items()
    ]

    # Deterministic sorting:
    # 1. RRF score descending
    # 2. document_id ascending (tie-breaker)
    # 3. chunk_id ascending (tie-breaker)
    scored_items.sort(
        key=lambda item: (-item[0], item[1].document_id, item[1].chunk_id)
    )

    if top_k is not None:
        scored_items = scored_items[:top_k]

    fused_results: List[RetrievalResult] = []
    for rank, (score, chunk) in enumerate(scored_items, start=1):
        fused_results.append(
            RetrievalResult(
                chunk=chunk,
                score=score,
                rank=rank,
                strategy="hybrid",
            )
        )

    return fused_results
