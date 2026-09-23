"""Tests for deterministic retrieval metrics (Hit@K, MRR, Precision@K)."""

from src.core.models import DocumentMetadata, KnowledgeChunk
from src.retrieval.metrics import hit_at_k, is_result_relevant, precision_at_k, reciprocal_rank
from src.retrieval.models import RetrievalResult


def make_result(chunk_id: str, doc_id: str, rank: int) -> RetrievalResult:
    meta = DocumentMetadata(
        document_id=doc_id,
        title="Title",
        status="active",
        effective_date="2026-01-01",
        audience="customer",
        policy_authority="official",
    )
    chunk = KnowledgeChunk(
        chunk_id=chunk_id,
        document_id=doc_id,
        filename=f"{doc_id}.md",
        heading="Heading",
        content="Content",
        metadata=meta,
    )
    return RetrievalResult(chunk=chunk, score=1.0 / rank, rank=rank, strategy="bm25")


def test_hit_at_k():
    results = [
        make_result("DOC-1::sec1", "DOC-1", rank=1),
        make_result("DOC-2::sec1", "DOC-2", rank=2),
        make_result("DOC-3::sec1", "DOC-3", rank=3),
    ]

    # Target is DOC-1 (rank 1)
    assert hit_at_k(results, ["DOC-1"], k=1) == 1.0
    assert hit_at_k(results, ["DOC-1"], k=3) == 1.0

    # Target is DOC-3 (rank 3)
    assert hit_at_k(results, ["DOC-3"], k=2) == 0.0
    assert hit_at_k(results, ["DOC-3"], k=3) == 1.0

    # Target not in results
    assert hit_at_k(results, ["DOC-99"], k=3) == 0.0


def test_reciprocal_rank():
    results = [
        make_result("DOC-1::sec1", "DOC-1", rank=1),
        make_result("DOC-2::sec1", "DOC-2", rank=2),
        make_result("DOC-3::sec1", "DOC-3", rank=3),
        make_result("DOC-4::sec1", "DOC-4", rank=4),
    ]

    # First match at rank 1 -> 1.0
    assert reciprocal_rank(results, ["DOC-1"]) == 1.0

    # First match at rank 2 -> 1/2 = 0.5
    assert reciprocal_rank(results, ["DOC-2"]) == 0.5

    # First match at rank 4 -> 1/4 = 0.25
    assert reciprocal_rank(results, ["DOC-4"]) == 0.25

    # No match -> 0.0
    assert reciprocal_rank(results, ["DOC-99"]) == 0.0


def test_precision_at_k():
    results = [
        make_result("DOC-1::sec1", "DOC-1", rank=1),
        make_result("DOC-2::sec1", "DOC-2", rank=2),
        make_result("DOC-3::sec1", "DOC-3", rank=3),
        make_result("DOC-4::sec1", "DOC-4", rank=4),
    ]

    # Expected: DOC-1 and DOC-3
    # Top-2: contains DOC-1 -> 1/2 = 0.5
    assert precision_at_k(results, ["DOC-1", "DOC-3"], k=2) == 0.5

    # Top-4: contains DOC-1 and DOC-3 -> 2/4 = 0.5
    assert precision_at_k(results, ["DOC-1", "DOC-3"], k=4) == 0.5

    # Top-1: contains DOC-1 -> 1/1 = 1.0
    assert precision_at_k(results, ["DOC-1"], k=1) == 1.0

    # No matches
    assert precision_at_k(results, ["DOC-99"], k=4) == 0.0


def test_metrics_empty_inputs():
    assert hit_at_k([], ["DOC-1"], k=5) == 0.0
    assert reciprocal_rank([], ["DOC-1"]) == 0.0
    assert precision_at_k([], ["DOC-1"], k=5) == 0.0
