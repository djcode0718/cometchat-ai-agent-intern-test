"""Unit tests verifying query-relevant sentence extraction and citation retention in fallback."""

import pytest
from src.core.models import DecisionState, DocumentMetadata, KnowledgeChunk
from src.knowledge.evidence import ApprovedEvidence
from src.llm.models import GroundedGenerationRequest
from src.llm.validator import OutputValidator


def test_fallback_extracts_query_relevant_sentences():
    meta = DocumentMetadata(
        document_id="DOC-01",
        title="Returns",
        status="active",
        effective_date="2026-01-01",
        audience="customer",
        policy_authority="official",
    )
    kc1 = KnowledgeChunk(
        chunk_id="RET-01",
        document_id="DOC-01",
        filename="01-returns-policy.md",
        heading="Overview",
        content="General introductory information about our outdoor brand Aster & Row. We take pride in craftsmanship.",
        metadata=meta,
    )
    kc2 = KnowledgeChunk(
        chunk_id="RET-02",
        document_id="DOC-01",
        filename="01-returns-policy.md",
        heading="Return Window",
        content="Standard customers have 30 calendar days from delivery to request a return. TrailPlus members receive a 45-day window.",
        metadata=meta,
    )

    chunk1 = ApprovedEvidence(
        chunk=kc1,
        retrieval_score=0.7,
        retrieval_rank=2,
        retrieval_strategy="hybrid",
    )
    chunk2 = ApprovedEvidence(
        chunk=kc2,
        retrieval_score=0.95,
        retrieval_rank=1,
        retrieval_strategy="hybrid",
    )

    req = GroundedGenerationRequest(
        user_query="How long is the standard return window?",
        decision_state=DecisionState.ANSWER,
        decision_reason="Sufficient approved evidence found.",
        approved_evidence=[chunk1, chunk2],
        customer_safe_order=None,
    )

    resp = OutputValidator.build_fallback(req)
    assert resp.is_fallback is True
    # Verify relevant sentence was extracted with its citation
    assert "30 calendar days" in resp.message
    assert "[01-returns-policy.md > Return Window]" in resp.message
    assert any(c.heading == "Return Window" for c in resp.citations)


def test_fallback_citation_integrity():
    meta = DocumentMetadata(
        document_id="DOC-11",
        title="Product Care",
        status="active",
        effective_date="2026-01-01",
        audience="customer",
        policy_authority="official",
    )
    kc = KnowledgeChunk(
        chunk_id="CARE-01",
        document_id="DOC-11",
        filename="11-product-care.md",
        heading="Breeze Tumbler",
        content="The Breeze Tumbler stainless-steel body must be hand-washed with mild soap.",
        metadata=meta,
    )
    chunk = ApprovedEvidence(
        chunk=kc,
        retrieval_score=0.9,
        retrieval_rank=1,
        retrieval_strategy="hybrid",
    )
    req = GroundedGenerationRequest(
        user_query="Can I wash the tumbler body in the dishwasher?",
        decision_state=DecisionState.ANSWER,
        decision_reason="Sufficient approved evidence found.",
        approved_evidence=[chunk],
        customer_safe_order=None,
    )

    resp = OutputValidator.build_fallback(req)
    assert "hand-washed with mild soap" in resp.message
    assert "[11-product-care.md > Breeze Tumbler]" in resp.message
    assert len(resp.citations) >= 1
