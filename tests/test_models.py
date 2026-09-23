"""Tests for core domain models."""

from datetime import date
import pytest
from pydantic import ValidationError

from src.core.models import (
    CitationSource,
    DocumentMetadata,
    KnowledgeChunk,
    Message,
    Session,
)


def test_document_metadata_valid():
    meta = DocumentMetadata(
        document_id="RET-2026-01",
        title="Returns Policy",
        status="active",
        effective_date=date(2026, 4, 1),
        audience="customer",
        policy_authority="official",
        supersedes="RET-2024-01",
    )
    assert meta.document_id == "RET-2026-01"
    assert meta.effective_date == "2026-04-01"
    assert meta.is_authoritative_for_customer is True
    assert meta.customer_answering is True


def test_document_metadata_invalid_status():
    with pytest.raises(ValidationError):
        DocumentMetadata(
            document_id="RET-2026-01",
            title="Returns Policy",
            status="invalid_status",  # type: ignore
            effective_date="2026-04-01",
            audience="customer",
            policy_authority="official",
        )


def test_citation_source_formatting():
    citation = CitationSource(
        filename="01-returns-policy-current.md",
        heading="Standard return window",
    )
    assert citation.formatted() == "[01-returns-policy-current.md > Standard return window]"
    assert str(citation) == "[01-returns-policy-current.md > Standard return window]"


def test_knowledge_chunk_citation_source():
    meta = DocumentMetadata(
        document_id="RET-2026-01",
        title="Returns Policy",
        status="active",
        effective_date="2026-04-01",
        audience="customer",
        policy_authority="official",
    )
    chunk = KnowledgeChunk(
        chunk_id="RET-2026-01::standard-return-window",
        document_id="RET-2026-01",
        filename="01-returns-policy-current.md",
        heading="Standard return window",
        heading_hierarchy=["Returns Policy", "Standard return window"],
        content="Return window is 30 days.",
        metadata=meta,
    )
    assert chunk.citation_str == "[01-returns-policy-current.md > Standard return window]"
    assert chunk.metadata.is_authoritative_for_customer is True
