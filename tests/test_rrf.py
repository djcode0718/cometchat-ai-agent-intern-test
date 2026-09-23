"""Tests for Reciprocal Rank Fusion (RRF)."""

from src.core.models import DocumentMetadata, KnowledgeChunk
from src.retrieval.fusion import reciprocal_rank_fusion
from src.retrieval.models import RetrievalResult


def make_chunk(chunk_id: str, doc_id: str = "DOC-1") -> KnowledgeChunk:
    meta = DocumentMetadata(
        document_id=doc_id,
        title="Title",
        status="active",
        effective_date="2026-01-01",
        audience="customer",
        policy_authority="official",
    )
    return KnowledgeChunk(
        chunk_id=chunk_id,
        document_id=doc_id,
        filename=f"{doc_id}.md",
        heading="Heading",
        content="Content",
        metadata=meta,
    )


def test_rrf_both_rankings_boost():
    # Chunk A is rank 1 in list 1 and rank 1 in list 2 -> should have highest combined score
    # Chunk B is rank 2 in list 1, absent in list 2
    # Chunk C is rank 2 in list 2, absent in list 1
    chunk_a = make_chunk("CHUNK-A")
    chunk_b = make_chunk("CHUNK-B")
    chunk_c = make_chunk("CHUNK-C")

    list1 = [
        RetrievalResult(chunk=chunk_a, score=10.0, rank=1, strategy="bm25"),
        RetrievalResult(chunk=chunk_b, score=5.0, rank=2, strategy="bm25"),
    ]
    list2 = [
        RetrievalResult(chunk=chunk_a, score=0.95, rank=1, strategy="dense"),
        RetrievalResult(chunk=chunk_c, score=0.80, rank=2, strategy="dense"),
    ]

    fused = reciprocal_rank_fusion([list1, list2], k=60, top_k=3)
    assert len(fused) == 3
    assert fused[0].chunk_id == "CHUNK-A"
    assert fused[0].strategy == "hybrid"
    assert fused[0].rank == 1

    # Score for A: 1/(60+1) + 1/(60+1) = 2/61 ≈ 0.032786
    expected_score_a = (1.0 / 61.0) + (1.0 / 61.0)
    assert abs(fused[0].score - expected_score_a) < 1e-6


def test_rrf_single_list():
    chunk_a = make_chunk("CHUNK-A")
    chunk_b = make_chunk("CHUNK-B")

    list1 = [
        RetrievalResult(chunk=chunk_a, score=10.0, rank=1, strategy="bm25"),
        RetrievalResult(chunk=chunk_b, score=5.0, rank=2, strategy="bm25"),
    ]

    fused = reciprocal_rank_fusion([list1], k=60)
    assert len(fused) == 2
    assert fused[0].chunk_id == "CHUNK-A"
    assert fused[1].chunk_id == "CHUNK-B"


def test_rrf_empty_lists():
    assert reciprocal_rank_fusion([]) == []
    assert reciprocal_rank_fusion([[], []]) == []


def test_rrf_determinism():
    chunk_a = make_chunk("CHUNK-A", doc_id="DOC-A")
    chunk_b = make_chunk("CHUNK-B", doc_id="DOC-B")

    list1 = [
        RetrievalResult(chunk=chunk_a, score=1.0, rank=1, strategy="bm25"),
        RetrievalResult(chunk=chunk_b, score=1.0, rank=2, strategy="bm25"),
    ]
    res1 = reciprocal_rank_fusion([list1], k=60)
    res2 = reciprocal_rank_fusion([list1], k=60)
    assert [r.chunk_id for r in res1] == [r.chunk_id for r in res2]
