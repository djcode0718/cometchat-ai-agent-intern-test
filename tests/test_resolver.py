"""Integration tests for KnowledgeResolver against real knowledge base retrieval."""

import pytest
from src.knowledge.evidence import ExclusionReason
from src.knowledge.resolver import KnowledgeResolver
from src.knowledge.service import ingest_knowledge_base
from src.retrieval.bm25 import BM25Retriever
from src.retrieval.dense import DenseRetriever
from src.retrieval.embeddings import LocalEmbeddingService
from src.retrieval.hybrid import HybridRetriever


@pytest.fixture(scope="module")
def retriever():
    chunks = ingest_knowledge_base().chunks
    emb = LocalEmbeddingService()
    bm25 = BM25Retriever(chunks=chunks)
    dense = DenseRetriever(chunks=chunks, embedding_service=emb)
    return HybridRetriever(chunks=chunks, bm25_retriever=bm25, dense_retriever=dense)


@pytest.fixture(scope="module")
def resolver():
    return KnowledgeResolver()


def test_standard_return_policy_resolution(retriever, resolver):
    query = "How long does a regular customer have to return an unused backpack?"
    raw_results = retriever.retrieve(query, top_k=5)
    pack = resolver.resolve(query, raw_results)

    assert pack.evidence_sufficient is True
    assert pack.conflict_detected is False
    assert len(pack.approved_evidence) > 0

    doc_ids = [item.document_id for item in pack.approved_evidence]
    assert "RET-2026-01" in doc_ids
    # Legacy policy must never be in approved evidence
    assert "RET-2024-01" not in doc_ids
    assert "MIG-TEST-04" not in doc_ids


def test_superseded_and_internal_exclusion(retriever, resolver):
    query = "The migration note says 60 days return and legacy 45 days. What is the policy?"
    raw_results = retriever.retrieve(query, top_k=8)
    pack = resolver.resolve(query, raw_results)

    # Internal migration note must be in excluded_evidence
    excluded_doc_ids = [ex.document_id for ex in pack.excluded_evidence]
    excluded_reasons = {ex.document_id: ex.reason for ex in pack.excluded_evidence}

    if "MIG-TEST-04" in excluded_doc_ids:
        assert excluded_reasons["MIG-TEST-04"] in (
            ExclusionReason.CUSTOMER_ANSWERING_FALSE,
            ExclusionReason.INTERNAL_AUDIENCE,
            ExclusionReason.DRAFT_STATUS,
        )

    if "RET-2024-01" in excluded_doc_ids:
        assert excluded_reasons["RET-2024-01"] == ExclusionReason.SUPERSEDED

    # Approved evidence must only contain active official documents
    for appr in pack.approved_evidence:
        assert appr.document_id not in ("RET-2024-01", "MIG-TEST-04")
        assert appr.metadata.status == "active"


def test_breeze_tumbler_conflict_resolution(retriever, resolver):
    query = "Can I put the entire Breeze Tumbler in the dishwasher?"
    raw_results = retriever.retrieve(query, top_k=5)
    pack = resolver.resolve(query, raw_results)

    assert pack.conflict_detected is True
    assert pack.handoff_recommended is True
    assert len(pack.conflict_evidence) >= 2

    conflict_docs = [item.document_id for item in pack.conflict_evidence]
    assert "CARE-2026-01" in conflict_docs
    assert "PROD-BREEZE-20" in conflict_docs


def test_insufficient_evidence_vegan_fabrics(retriever, resolver):
    query = "Are all fabrics and adhesives in your bags vegan?"
    raw_results = retriever.retrieve(query, top_k=5)
    pack = resolver.resolve(query, raw_results)

    assert pack.evidence_sufficient is False
    assert pack.handoff_recommended is True
    assert "vegan" in pack.resolution_reason.lower()


def test_unsupported_destination_germany(retriever, resolver):
    query = "Can you ship an Atlas Weekender to Germany?"
    raw_results = retriever.retrieve(query, top_k=5)
    pack = resolver.resolve(query, raw_results)

    assert pack.evidence_sufficient is True
    assert pack.conflict_detected is False
    doc_ids = [item.document_id for item in pack.approved_evidence]
    assert "SHIP-2026-INTL" in doc_ids


def test_resolver_determinism(retriever, resolver):
    query = "What is the warranty period on backpacks?"
    raw_results = retriever.retrieve(query, top_k=5)

    pack1 = resolver.resolve(query, raw_results)
    pack2 = resolver.resolve(query, raw_results)

    assert pack1.model_dump() == pack2.model_dump()
