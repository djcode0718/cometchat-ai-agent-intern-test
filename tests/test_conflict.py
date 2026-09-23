"""Tests for ConflictDetector and conflict isolation."""

from src.core.models import DocumentMetadata, KnowledgeChunk
from src.knowledge.conflict import ConflictDetector
from src.knowledge.evidence import ApprovedEvidence


def make_approved_evidence(doc_id: str, filename: str, heading: str, content: str) -> ApprovedEvidence:
    meta = DocumentMetadata(
        document_id=doc_id,
        title="Title",
        status="active",
        effective_date="2026-03-01",
        audience="customer",
        policy_authority="official",
    )
    chunk = KnowledgeChunk(
        chunk_id=f"{doc_id}::{heading.lower().replace(' ', '-')}",
        document_id=doc_id,
        filename=filename,
        heading=heading,
        content=content,
        metadata=meta,
    )
    return ApprovedEvidence(
        chunk=chunk,
        retrieval_score=0.9,
        retrieval_rank=1,
        retrieval_strategy="hybrid",
    )


def test_genuine_breeze_tumbler_dishwasher_conflict():
    care_item = make_approved_evidence(
        doc_id="CARE-2026-01",
        filename="11-product-care.md",
        heading="Breeze Tumbler",
        content="The stainless-steel body of the Breeze Tumbler should be hand-washed. The lid may be placed on the top rack of a dishwasher.",
    )
    card_item = make_approved_evidence(
        doc_id="PROD-BREEZE-20",
        filename="12-breeze-tumbler-product-card.md",
        heading="Cleaning",
        content="The product card states that all components are dishwasher safe, with the top rack recommended.",
    )

    detector = ConflictDetector()
    conflict_detected, conflict_items, desc = detector.detect_conflicts(
        query="Can I put the entire Breeze Tumbler in the dishwasher?",
        approved_evidence=[care_item, card_item],
    )

    assert conflict_detected is True
    assert len(conflict_items) == 2
    assert "CARE-2026-01" in desc
    assert "PROD-BREEZE-20" in desc
    assert "hand-washed" in desc
    assert "dishwasher safe" in desc


def test_non_conflicting_distinct_scopes():
    # General return window (30 days) vs TrailPlus member return window (45 days)
    gen_return = make_approved_evidence(
        doc_id="RET-2026-01",
        filename="01-returns-policy-current.md",
        heading="Standard return window",
        content="Customers on the standard plan may request a return within 30 calendar days.",
    )
    tp_return = make_approved_evidence(
        doc_id="MEM-2026-01",
        filename="09-trailplus-membership.md",
        heading="Return window",
        content="TrailPlus members receive a 45-calendar-day return window.",
    )

    detector = ConflictDetector()
    conflict_detected, conflict_items, _ = detector.detect_conflicts(
        query="How long is the return window?",
        approved_evidence=[gen_return, tp_return],
    )

    # Scoped tier differences are not conflicting
    assert conflict_detected is False
    assert len(conflict_items) == 0
