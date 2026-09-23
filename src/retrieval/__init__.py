"""Retrieval, embeddings, indexing, fusion, and evaluation module."""

from src.retrieval.base import BaseRetriever
from src.retrieval.benchmark import (
    DEFAULT_BENCHMARK_CASES,
    BenchmarkCase,
    BenchmarkQueryResult,
    StrategyBenchmarkMetrics,
    evaluate_retriever,
    format_benchmark_table,
    run_retrieval_benchmark,
)
from src.retrieval.bm25 import BM25Index, BM25Retriever
from src.retrieval.dense import DenseIndex, DenseRetriever
from src.retrieval.embeddings import LocalEmbeddingService
from src.retrieval.fusion import reciprocal_rank_fusion
from src.retrieval.hybrid import HybridRetriever
from src.retrieval.metrics import hit_at_k, is_result_relevant, precision_at_k, reciprocal_rank
from src.retrieval.models import RetrievalResult, RetrievalStrategy
from src.retrieval.tokenizer import tokenize_text

__all__ = [
    "BaseRetriever",
    "RetrievalStrategy",
    "RetrievalResult",
    "tokenize_text",
    "BM25Index",
    "BM25Retriever",
    "LocalEmbeddingService",
    "DenseIndex",
    "DenseRetriever",
    "reciprocal_rank_fusion",
    "HybridRetriever",
    "hit_at_k",
    "reciprocal_rank",
    "precision_at_k",
    "is_result_relevant",
    "BenchmarkCase",
    "BenchmarkQueryResult",
    "StrategyBenchmarkMetrics",
    "DEFAULT_BENCHMARK_CASES",
    "evaluate_retriever",
    "run_retrieval_benchmark",
    "format_benchmark_table",
]
