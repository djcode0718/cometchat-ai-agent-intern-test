"""Tests for EvidencePack, ApprovedEvidence, and ExcludedEvidence models."""

from src.core.models import DocumentMetadata, KnowledgeChunk
from src.knowledge.evidence import (
    ApprovedEvidence,
    EvidencePack,
    ExcludedEvidence,
    ExclusionReason,
)


def make_test_chunk(chunk_id: str = "RET-1::sec", doc_id: str = "RET-1") -> KnowledgeChunk:
    meta = DocumentMetadata(
        document_id=doc_id,
        title="Returns Policy",
        status="active",
        effective_date="2026-04-01",
        audience="customer",
        policy_authority="official",
    )
    return KnowledgeChunk(
        chunk_id=chunk_id,
        document_id=doc_id,
        filename="01-returns-policy-current.md",
        heading="Standard return window",
        content="30 calendar days.",
        metadata=meta,
    )


def test_approved_evidence_properties():
    chunk = make_test_chunk()
    appr = ApprovedEvidence(
        chunk=chunk,
        retrieval_score=0.95,
        retrieval_rank=1,
        retrieval_strategy="hybrid",
    )

    assert appr.document_id == "RET-1"
    assert appr.filename == "01-returns-policy-current.md"
    assert appr.heading == "Standard return window"
    assert appr.citation_str == "[01-returns-policy-current.md > Standard return window]"
    assert appr.retrieval_score == 0.95
    assert appr.retrieval_rank == 1


def test_excluded_evidence_properties():
    chunk = make_test_chunk(doc_id="MIG-TEST-04")
    excl = ExcludedEvidence(
        chunk=chunk,
        reason=ExclusionReason.CUSTOMER_ANSWERING_FALSE,
        details="Internal draft migration document.",
        retrieval_score=0.88,
        retrieval_rank=2,
        retrieval_strategy="dense",
    )

    assert excl.document_id == "MIG-TEST-04"
    assert excl.reason == ExclusionReason.CUSTOMER_ANSWERING_FALSE
    assert "Internal draft" in excl.details


def test_evidence_pack_citations():
    chunk1 = make_test_chunk("RET-1::sec1", "RET-1")
    chunk2 = make_test_chunk("RET-1::sec2", "RET-1")
    chunk2.heading = "Item condition"

    appr1 = ApprovedEvidence(chunk=chunk1, retrieval_score=1.0, retrieval_rank=1, retrieval_strategy="hybrid")
    appr2 = ApprovedEvidence(chunk=chunk2, retrieval_score=0.9, retrieval_rank=2, retrieval_strategy="hybrid")

    pack = EvidencePack(
        query="What is the return window?",
        approved_evidence=[appr1, appr2],
        evidence_sufficient=True,
    )

    assert len(pack.citations) == 2
    assert pack.citation_strings == [
        "[01-returns-policy-current.md > Standard return window]",
        "[01-returns-policy-current.md > Item condition]",
    ]
