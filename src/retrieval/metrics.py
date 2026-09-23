"""Deterministic information retrieval evaluation metrics."""

from typing import List, Sequence, Set, Union
from src.retrieval.models import RetrievalResult


def is_result_relevant(
    result: RetrievalResult, expected_targets: Sequence[str]
) -> bool:
    """Check if a RetrievalResult matches any expected target (doc ID, filename, or chunk ID)."""
    targets_lower = {t.lower().strip() for t in expected_targets}
    chunk = result.chunk
    return (
        chunk.document_id.lower() in targets_lower
        or chunk.filename.lower() in targets_lower
        or chunk.chunk_id.lower() in targets_lower
    )


def hit_at_k(
    results: Sequence[RetrievalResult],
    expected_targets: Sequence[str],
    k: int = 5,
) -> float:
    """Calculate Hit@K (1.0 if at least one relevant chunk appears in top-K, else 0.0)."""
    if not results or not expected_targets or k <= 0:
        return 0.0

    top_k_results = results[:k]
    for res in top_k_results:
        if is_result_relevant(res, expected_targets):
            return 1.0
    return 0.0


def reciprocal_rank(
    results: Sequence[RetrievalResult],
    expected_targets: Sequence[str],
) -> float:
    """Calculate Reciprocal Rank (1/rank of the first relevant result, or 0.0 if none found)."""
    if not results or not expected_targets:
        return 0.0

    for res in results:
        if is_result_relevant(res, expected_targets):
            # res.rank is 1-indexed
            return 1.0 / float(res.rank)
    return 0.0


def precision_at_k(
    results: Sequence[RetrievalResult],
    expected_targets: Sequence[str],
    k: int = 5,
) -> float:
    """Calculate Precision@K (fraction of top-K results that are relevant)."""
    if not results or not expected_targets or k <= 0:
        return 0.0

    top_k_results = results[:k]
    relevant_count = sum(
        1 for res in top_k_results if is_result_relevant(res, expected_targets)
    )
    return float(relevant_count) / float(k)
