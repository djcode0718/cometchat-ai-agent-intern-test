"""Tests for retrieval result models and properties."""

from src.core.models import DocumentMetadata, KnowledgeChunk
from src.retrieval.models import RetrievalResult


def test_retrieval_result_properties():
    meta = DocumentMetadata(
        document_id="RET-2026-01",
        title="Returns Policy",
        status="active",
        effective_date="2026-04-01",
        audience="customer",
        policy_authority="official",
    )
    chunk = KnowledgeChunk(
        chunk_id="RET-2026-01::standard-return-window",
        document_id="RET-2026-01",
        filename="01-returns-policy-current.md",
        heading="Standard return window",
        heading_hierarchy=["Returns Policy", "Standard return window"],
        content="Standard return window is 30 calendar days.",
        metadata=meta,
    )

    result = RetrievalResult(
        chunk=chunk,
        score=1.45,
        rank=1,
        strategy="bm25",
    )

    assert result.chunk_id == "RET-2026-01::standard-return-window"
    assert result.document_id == "RET-2026-01"
    assert result.filename == "01-returns-policy-current.md"
    assert result.heading == "Standard return window"
    assert result.citation_str == "[01-returns-policy-current.md > Standard return window]"
    assert result.metadata.status == "active"
    assert result.strategy == "bm25"
    assert result.rank == 1
    assert result.score == 1.45
