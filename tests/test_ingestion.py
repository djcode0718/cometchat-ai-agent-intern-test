"""Integration tests for ingesting repository knowledge base."""

from pathlib import Path

from src.core.config import get_settings
from src.knowledge.service import KnowledgeIngestionService, ingest_knowledge_base


def test_ingest_repository_knowledge_base():
    settings = get_settings()
    service = KnowledgeIngestionService(kb_path=settings.knowledge_base_path)
    result = service.ingest()

    # Aster & Row repository has exactly 14 markdown files
    assert result.document_count == 14
    assert result.chunk_count > 14  # Multiple sections per document

    # Verify specific documents are parsed and preserved
    ret_curr = result.get_document_by_id("RET-2026-01")
    assert ret_curr is not None
    assert ret_curr.filename == "01-returns-policy-current.md"
    assert ret_curr.metadata.status == "active"
    assert ret_curr.metadata.policy_authority == "official"
    assert ret_curr.metadata.supersedes == "RET-2024-01"

    ret_legacy = result.get_document_by_id("RET-2024-01")
    assert ret_legacy is not None
    assert ret_legacy.metadata.status == "superseded"
    assert ret_legacy.metadata.superseded_by == "RET-2026-01"

    scratchpad = result.get_document_by_id("MIG-TEST-04")
    assert scratchpad is not None
    assert scratchpad.metadata.status == "draft"
    assert scratchpad.metadata.customer_answering is False
    assert scratchpad.metadata.policy_authority == "none"

    tumbler_care = result.get_document_by_id("CARE-2026-01")
    assert tumbler_care is not None
    assert tumbler_care.metadata.status == "active"

    tumbler_card = result.get_document_by_id("PROD-BREEZE-20")
    assert tumbler_card is not None
    assert tumbler_card.metadata.status == "active"


def test_ingestion_determinism():
    result1 = ingest_knowledge_base()
    result2 = ingest_knowledge_base()

    assert result1.document_count == result2.document_count
    assert result1.chunk_count == result2.chunk_count

    for d1, d2 in zip(result1.documents, result2.documents):
        assert d1.filename == d2.filename
        assert d1.metadata.document_id == d2.metadata.document_id
        assert len(d1.sections) == len(d2.sections)

    for c1, c2 in zip(result1.chunks, result2.chunks):
        assert c1.chunk_id == c2.chunk_id
        assert c1.heading == c2.heading
        assert c1.citation_str == c2.citation_str
        assert c1.content == c2.content
