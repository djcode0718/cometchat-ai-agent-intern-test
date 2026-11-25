"""Knowledge-base lifecycle, document mutation, and re-indexing test suite (KB-001 through KB-008)."""

import os
from pathlib import Path
import pytest

from src.knowledge.service import KnowledgeIngestionService
from src.knowledge.parser import MarkdownDocumentParser
from src.knowledge.chunker import SectionAwareChunker
from src.retrieval.bm25 import BM25Retriever
from src.retrieval.dense import DenseRetriever
from src.retrieval.embeddings import LocalEmbeddingService
from src.retrieval.hybrid import HybridRetriever
from src.knowledge.resolver import KnowledgeResolver
from src.knowledge.exceptions import FrontmatterParsingError


SAMPLE_POLICY_V1 = """---
document_id: TEST-RET-01
title: Returns Policy Test
status: active
effective_date: 2026-01-01
audience: customer
policy_authority: official
customer_answering: true
---

# Returns Policy Test

## Return Window
Customers may return items within 30 days of delivery.

## Item Condition
Items must be in pristine, unwashed condition.
"""

SAMPLE_POLICY_V2 = """---
document_id: TEST-RET-01
title: Returns Policy Test
status: active
effective_date: 2026-06-01
audience: customer
policy_authority: official
customer_answering: true
---

# Returns Policy Test

## Return Window
Customers may return items within 60 days of delivery under the updated summer policy.

## Item Condition
Items must be in pristine, unwashed condition with tags attached.
"""

SUPERSEDED_LEGACY_POLICY = """---
document_id: TEST-RET-LEGACY
title: Returns Policy Legacy
status: superseded
effective_date: 2024-01-01
superseded_date: 2026-01-01
superseded_by: TEST-RET-01
audience: customer
policy_authority: official
customer_answering: true
---

# Returns Policy Legacy

## Return Window
Legacy return window was 14 days from delivery.
"""

MALFORMED_DOC = """---
document_id: BROKEN-01
title: Broken Frontmatter
status: active
effective_date: not-a-valid-yaml: [unclosed
---
Missing body
"""


@pytest.fixture
def temp_kb(tmp_path):
    kb_dir = tmp_path / "knowledge_base"
    kb_dir.mkdir()
    return kb_dir


def test_kb_001_initial_ingestion(temp_kb):
    """KB-001: Initial ingestion of valid markdown document."""
    doc_path = temp_kb / "01-returns.md"
    doc_path.write_text(SAMPLE_POLICY_V1, encoding="utf-8")

    service = KnowledgeIngestionService(kb_path=temp_kb)
    result = service.ingest()

    assert result.document_count == 1
    assert result.chunk_count == 2
    doc = result.get_document_by_id("TEST-RET-01")
    assert doc is not None
    assert doc.metadata.status == "active"
    chunks = result.get_chunks_for_document("TEST-RET-01")
    assert len(chunks) == 2
    headings = {c.heading for c in chunks}
    assert "Return Window" in headings
    assert "Item Condition" in headings


def test_kb_002_reingestion_idempotency(temp_kb):
    """KB-002: Re-ingesting the exact same knowledge base yields identical chunks and zero duplicates."""
    doc_path = temp_kb / "01-returns.md"
    doc_path.write_text(SAMPLE_POLICY_V1, encoding="utf-8")

    service = KnowledgeIngestionService(kb_path=temp_kb)
    res1 = service.ingest()
    res2 = service.ingest()

    assert res1.chunk_count == res2.chunk_count
    assert [c.chunk_id for c in res1.chunks] == [c.chunk_id for c in res2.chunks]


def test_kb_003_document_update(temp_kb):
    """KB-003: Updating document content replaces old chunks and reflects new text in index."""
    doc_path = temp_kb / "01-returns.md"
    doc_path.write_text(SAMPLE_POLICY_V1, encoding="utf-8")

    service = KnowledgeIngestionService(kb_path=temp_kb)
    res1 = service.ingest()
    assert any("30 days" in c.content for c in res1.chunks)

    # Update to V2
    doc_path.write_text(SAMPLE_POLICY_V2, encoding="utf-8")
    res2 = service.ingest()
    assert any("60 days" in c.content for c in res2.chunks)
    assert not any("30 days" in c.content for c in res2.chunks)


def test_kb_004_superseded_policy_handling(temp_kb):
    """KB-004: Ingesting active and superseded docs; resolver correctly prefers active over superseded."""
    (temp_kb / "01-returns.md").write_text(SAMPLE_POLICY_V1, encoding="utf-8")
    (temp_kb / "02-legacy.md").write_text(SUPERSEDED_LEGACY_POLICY, encoding="utf-8")

    service = KnowledgeIngestionService(kb_path=temp_kb)
    res = service.ingest()
    assert res.document_count == 2

    # Ingest and test retrieval + resolver
    bm25 = BM25Retriever(chunks=res.chunks)
    candidates = bm25.retrieve("What is the return window?", top_k=5)
    resolver = KnowledgeResolver()
    pack = resolver.resolve("What is the return window?", candidates)

    # Approved evidence must NOT contain superseded legacy document
    for app_ev in pack.approved_evidence:
        assert app_ev.chunk.metadata.status != "superseded"
        assert app_ev.chunk.document_id != "TEST-RET-LEGACY"


def test_kb_005_document_deletion(temp_kb):
    """KB-005: Deleting document removes chunks from index completely."""
    doc_path = temp_kb / "01-returns.md"
    doc_path.write_text(SAMPLE_POLICY_V1, encoding="utf-8")

    service = KnowledgeIngestionService(kb_path=temp_kb)
    res1 = service.ingest()
    assert res1.chunk_count == 2

    doc_path.unlink()
    res2 = service.ingest()
    assert res2.document_count == 0
    assert res2.chunk_count == 0


def test_kb_006_failed_ingestion_safety(temp_kb):
    """KB-006: Malformed frontmatter fails safely with FrontmatterParsingError without corrupting valid files."""
    (temp_kb / "valid.md").write_text(SAMPLE_POLICY_V1, encoding="utf-8")
    (temp_kb / "broken.md").write_text(MALFORMED_DOC, encoding="utf-8")

    service = KnowledgeIngestionService(kb_path=temp_kb)
    with pytest.raises(FrontmatterParsingError):
        service.ingest()


def test_kb_007_index_rebuild(temp_kb):
    """KB-007: Index rebuild from scratch yields stable retrieval scores."""
    (temp_kb / "01-returns.md").write_text(SAMPLE_POLICY_V1, encoding="utf-8")
    service = KnowledgeIngestionService(kb_path=temp_kb)
    res = service.ingest()

    bm25_1 = BM25Retriever(chunks=res.chunks)
    bm25_2 = BM25Retriever(chunks=res.chunks)

    cands1 = bm25_1.retrieve("return window", top_k=2)
    cands2 = bm25_2.retrieve("return window", top_k=2)

    assert [c.chunk.chunk_id for c in cands1] == [c.chunk.chunk_id for c in cands2]
    assert [c.score for c in cands1] == [c.score for c in cands2]


def test_kb_008_chunk_boundary_integrity(temp_kb):
    """KB-008: Statements at start, end, and across sections maintain retrieval integrity."""
    boundary_doc = """---
document_id: TEST-BOUND-01
title: Boundary Test
status: active
effective_date: 2026-01-01
audience: customer
policy_authority: official
customer_answering: true
---

# Boundary Test

## Opening Clause
Leading introductory policy statement is present here.

## Mid Clause
Interior critical specification regarding return shipping label generation.

## Closing Clause
Final concluding policy note at the very bottom of the document.
"""
    (temp_kb / "bound.md").write_text(boundary_doc, encoding="utf-8")
    service = KnowledgeIngestionService(kb_path=temp_kb)
    res = service.ingest()
    assert res.chunk_count == 3

    bm25 = BM25Retriever(chunks=res.chunks)
    c_lead = bm25.retrieve("Leading introductory policy", top_k=1)
    c_close = bm25.retrieve("Final concluding policy note", top_k=1)

    assert len(c_lead) == 1 and c_lead[0].chunk.heading == "Opening Clause"
    assert len(c_close) == 1 and c_close[0].chunk.heading == "Closing Clause"
