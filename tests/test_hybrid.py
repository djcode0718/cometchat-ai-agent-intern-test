"""Tests for HybridRetriever combining BM25 and Dense with RRF."""

import pytest
from src.core.models import DocumentMetadata, KnowledgeChunk
from src.retrieval.embeddings import LocalEmbeddingService
from src.retrieval.hybrid import HybridRetriever


def create_hybrid_sample_chunks():
    meta = DocumentMetadata(
        document_id="DOC-1",
        title="Sample",
        status="active",
        effective_date="2026-01-01",
        audience="customer",
        policy_authority="official",
    )
    return [
        KnowledgeChunk(
            chunk_id="DOC-1::shipping",
            document_id="DOC-1",
            filename="shipping.md",
            heading="Domestic Shipping",
            content="Standard shipping takes 3-5 business days and is free over $75.",
            metadata=meta,
        ),
        KnowledgeChunk(
            chunk_id="DOC-1::returns",
            document_id="DOC-1",
            filename="returns.md",
            heading="Standard Returns",
            content="Customers have 30 calendar days from delivery to request a return.",
            metadata=meta,
        ),
        KnowledgeChunk(
            chunk_id="DOC-1::warranty",
            document_id="DOC-1",
            filename="warranty.md",
            heading="Product Warranty",
            content="Bags are covered by a 2-year warranty against manufacturing defects.",
            metadata=meta,
        ),
    ]


@pytest.fixture(scope="module")
def embedding_service():
    return LocalEmbeddingService()


def test_hybrid_retrieval_execution(embedding_service):
    chunks = create_hybrid_sample_chunks()
    retriever = HybridRetriever(chunks=chunks, embedding_service=embedding_service)

    assert retriever.strategy_name == "hybrid"
    results = retriever.retrieve("What is the return period?", top_k=2)

    assert len(results) > 0
    assert results[0].strategy == "hybrid"
    assert results[0].chunk_id == "DOC-1::returns"
    assert results[0].rank == 1


def test_hybrid_retrieval_determinism(embedding_service):
    chunks = create_hybrid_sample_chunks()
    retriever = HybridRetriever(chunks=chunks, embedding_service=embedding_service)

    res1 = retriever.retrieve("how long does domestic shipping take?", top_k=3)
    res2 = retriever.retrieve("how long does domestic shipping take?", top_k=3)

    assert len(res1) == len(res2)
    for r1, r2 in zip(res1, res2):
        assert r1.chunk_id == r2.chunk_id
        assert abs(r1.score - r2.score) < 1e-6
