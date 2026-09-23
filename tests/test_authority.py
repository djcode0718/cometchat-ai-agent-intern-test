"""Tests for AuthorityResolver, customer-answerability, and internal content exclusion."""

from src.core.models import DocumentMetadata, KnowledgeChunk
from src.knowledge.authority import AuthorityResolver
from src.knowledge.evidence import ExclusionReason
from src.retrieval.models import RetrievalResult


def make_result_with_meta(meta: DocumentMetadata) -> RetrievalResult:
    chunk = KnowledgeChunk(
        chunk_id=f"{meta.document_id}::sec",
        document_id=meta.document_id,
        filename=f"{meta.document_id}.md",
        heading="Section",
        content="Policy text",
        metadata=meta,
    )
    return RetrievalResult(chunk=chunk, score=0.9, rank=1, strategy="hybrid")


def test_customer_answering_false_exclusion():
    meta = DocumentMetadata(
        document_id="MIG-TEST-04",
        title="Migration Notes",
        status="draft",
        effective_date="2026-08-01",
        audience="internal",
        policy_authority="none",
        customer_answering=False,
    )
    res = make_result_with_meta(meta)
    eligible, excluded = AuthorityResolver.filter_eligible_candidates([res])

    assert len(eligible) == 0
    assert len(excluded) == 1
    assert excluded[0].reason == ExclusionReason.CUSTOMER_ANSWERING_FALSE
    assert excluded[0].document_id == "MIG-TEST-04"


def test_internal_audience_exclusion():
    meta = DocumentMetadata(
        document_id="SUP-2026-01",
        title="Support Escalation",
        status="active",
        effective_date="2026-04-01",
        audience="internal",
        policy_authority="official",
        customer_answering=True,
    )
    res = make_result_with_meta(meta)
    eligible, excluded = AuthorityResolver.filter_eligible_candidates([res])

    assert len(eligible) == 0
    assert len(excluded) == 1
    assert excluded[0].reason == ExclusionReason.INTERNAL_AUDIENCE


def test_policy_authority_none_exclusion():
    meta = DocumentMetadata(
        document_id="TEST-NONE",
        title="Unapproved Draft",
        status="active",
        effective_date="2026-04-01",
        audience="customer",
        policy_authority="none",
        customer_answering=True,
    )
    res = make_result_with_meta(meta)
    eligible, excluded = AuthorityResolver.filter_eligible_candidates([res])

    assert len(eligible) == 0
    assert len(excluded) == 1
    assert excluded[0].reason == ExclusionReason.POLICY_AUTHORITY_NONE


def test_draft_status_exclusion():
    meta = DocumentMetadata(
        document_id="TEST-DRAFT",
        title="Draft Policy",
        status="draft",
        effective_date="2026-04-01",
        audience="customer",
        policy_authority="official",
        customer_answering=True,
    )
    res = make_result_with_meta(meta)
    eligible, excluded = AuthorityResolver.filter_eligible_candidates([res])

    assert len(eligible) == 0
    assert len(excluded) == 1
    assert excluded[0].reason == ExclusionReason.DRAFT_STATUS


def test_active_official_customer_eligible():
    meta = DocumentMetadata(
        document_id="RET-2026-01",
        title="Returns Policy",
        status="active",
        effective_date="2026-04-01",
        audience="customer",
        policy_authority="official",
        customer_answering=True,
    )
    res = make_result_with_meta(meta)
    eligible, excluded = AuthorityResolver.filter_eligible_candidates([res])

    assert len(eligible) == 1
    assert len(excluded) == 0
    assert eligible[0].document_id == "RET-2026-01"
