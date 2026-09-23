"""Tests for BM25 lexical retriever."""

from src.core.models import DocumentMetadata, KnowledgeChunk
from src.retrieval.bm25 import BM25Index, BM25Retriever


def create_sample_chunks():
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


def test_bm25_exact_lexical_match():
    chunks = create_sample_chunks()
    retriever = BM25Retriever(chunks=chunks)

    results = retriever.retrieve("how long is the return window?", top_k=2)
    assert len(results) > 0
    assert results[0].chunk_id == "DOC-1::returns"
    assert results[0].strategy == "bm25"
    assert results[0].rank == 1


def test_bm25_ranking_and_top_k():
    chunks = create_sample_chunks()
    retriever = BM25Retriever(chunks=chunks)

    results = retriever.retrieve("warranty on bags", top_k=1)
    assert len(results) == 1
    assert results[0].chunk_id == "DOC-1::warranty"


def test_bm25_empty_query():
    chunks = create_sample_chunks()
    retriever = BM25Retriever(chunks=chunks)
    assert retriever.retrieve("") == []
    assert retriever.retrieve("   ") == []


def test_bm25_no_match_query():
    chunks = create_sample_chunks()
    retriever = BM25Retriever(chunks=chunks)
    results = retriever.retrieve("completely unrelated astronaut spacecraft")
    assert len(results) == 0


def test_bm25_determinism():
    chunks = create_sample_chunks()
    retriever = BM25Retriever(chunks=chunks)
    res1 = retriever.retrieve("free shipping", top_k=3)
    res2 = retriever.retrieve("free shipping", top_k=3)
    assert len(res1) == len(res2)
    for r1, r2 in zip(res1, res2):
        assert r1.chunk_id == r2.chunk_id
        assert r1.score == r2.score
