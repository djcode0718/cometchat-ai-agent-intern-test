"""Integration tests for the retrieval benchmark runner over the real knowledge base."""

import pytest
from src.knowledge.service import ingest_knowledge_base
from src.retrieval.benchmark import (
    DEFAULT_BENCHMARK_CASES,
    format_benchmark_table,
    run_retrieval_benchmark,
)
from src.retrieval.bm25 import BM25Retriever
from src.retrieval.dense import DenseRetriever
from src.retrieval.embeddings import LocalEmbeddingService
from src.retrieval.hybrid import HybridRetriever


@pytest.fixture(scope="module")
def knowledge_base_chunks():
    ingestion_result = ingest_knowledge_base()
    return ingestion_result.chunks


@pytest.fixture(scope="module")
def embedding_service():
    return LocalEmbeddingService()


def test_run_benchmark_across_all_strategies(knowledge_base_chunks, embedding_service):
    bm25 = BM25Retriever(chunks=knowledge_base_chunks)
    dense = DenseRetriever(chunks=knowledge_base_chunks, embedding_service=embedding_service)
    hybrid = HybridRetriever(
        chunks=knowledge_base_chunks,
        bm25_retriever=bm25,
        dense_retriever=dense,
    )

    retrievers = {
        "bm25": bm25,
        "dense": dense,
        "hybrid": hybrid,
    }

    metrics = run_retrieval_benchmark(retrievers=retrievers, cases=DEFAULT_BENCHMARK_CASES, top_k=5)

    assert "bm25" in metrics
    assert "dense" in metrics
    assert "hybrid" in metrics

    for name, metric in metrics.items():
        assert metric.total_queries == len(DEFAULT_BENCHMARK_CASES)
        assert 0.0 <= metric.hit_at_k <= 1.0
        assert 0.0 <= metric.mrr <= 1.0
        assert 0.0 <= metric.precision_at_k <= 1.0
        assert len(metric.query_results) == len(DEFAULT_BENCHMARK_CASES)

    table = format_benchmark_table(metrics)
    assert "| Strategy | Queries |" in table
    assert "BM25" in table
    assert "DENSE" in table
    assert "HYBRID" in table
