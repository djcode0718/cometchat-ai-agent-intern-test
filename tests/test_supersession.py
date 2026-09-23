"""Tests for supersession resolution and legacy document handling."""

from src.core.models import DocumentMetadata, KnowledgeChunk
from src.knowledge.evidence import ExclusionReason
from src.knowledge.supersession import SupersessionResolver
from src.retrieval.models import RetrievalResult


def create_current_and_legacy_results():
    current_meta = DocumentMetadata(
        document_id="RET-2026-01",
        title="Returns Policy",
        status="active",
        effective_date="2026-04-01",
        audience="customer",
        policy_authority="official",
        supersedes="RET-2024-01",
    )
    legacy_meta = DocumentMetadata(
        document_id="RET-2024-01",
        title="Returns Policy — Legacy Version",
        status="superseded",
        effective_date="2024-01-01",
        superseded_date="2026-04-01",
        audience="customer",
        policy_authority="official",
        superseded_by="RET-2026-01",
    )

    current_chunk = KnowledgeChunk(
        chunk_id="RET-2026-01::window",
        document_id="RET-2026-01",
        filename="01-returns-policy-current.md",
        heading="Standard return window",
        content="Return window is 30 calendar days.",
        metadata=current_meta,
    )
    legacy_chunk = KnowledgeChunk(
        chunk_id="RET-2024-01::window",
        document_id="RET-2024-01",
        filename="02-returns-policy-legacy.md",
        heading="Return window",
        content="Return window was 45 calendar days.",
        metadata=legacy_meta,
    )

    res_current = RetrievalResult(chunk=current_chunk, score=0.95, rank=1, strategy="hybrid")
    res_legacy = RetrievalResult(chunk=legacy_chunk, score=0.90, rank=2, strategy="hybrid")

    return res_current, res_legacy


def test_supersession_resolution_both_retrieved():
    res_current, res_legacy = create_current_and_legacy_results()
    kept, excluded = SupersessionResolver.resolve([res_current, res_legacy])

    assert len(kept) == 1
    assert kept[0].document_id == "RET-2026-01"

    assert len(excluded) == 1
    assert excluded[0].document_id == "RET-2024-01"
    assert excluded[0].reason == ExclusionReason.SUPERSEDED
    assert "RET-2026-01" in excluded[0].details


def test_supersession_resolution_only_legacy_retrieved():
    _, res_legacy = create_current_and_legacy_results()
    kept, excluded = SupersessionResolver.resolve([res_legacy])

    assert len(kept) == 0
    assert len(excluded) == 1
    assert excluded[0].document_id == "RET-2024-01"
    assert excluded[0].reason == ExclusionReason.SUPERSEDED
