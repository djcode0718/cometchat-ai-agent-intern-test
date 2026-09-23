"""Tests for markdown and YAML frontmatter parsing."""

import pytest

from src.knowledge.exceptions import (
    DocumentNotFoundError,
    FrontmatterParsingError,
    MissingMetadataError,
)
from src.knowledge.parser import MarkdownDocumentParser


def test_parse_valid_document(valid_markdown: str):
    doc = MarkdownDocumentParser.parse_string(valid_markdown, filename="test.md")
    assert doc.filename == "test.md"
    assert doc.metadata.document_id == "TEST-2026-01"
    assert doc.metadata.title == "Test Policy"
    assert doc.metadata.status == "active"
    assert doc.metadata.effective_date == "2026-01-01"
    assert doc.metadata.audience == "customer"
    assert doc.metadata.policy_authority == "official"
    assert doc.metadata.supersedes == "TEST-2024-01"

    # Verify sections parsed
    headings = [s.heading for s in doc.sections]
    assert "First Section" in headings
    assert "Second Section" in headings


def test_parse_superseded_document(superseded_markdown: str):
    doc = MarkdownDocumentParser.parse_string(
        superseded_markdown, filename="legacy.md"
    )
    assert doc.metadata.status == "superseded"
    assert doc.metadata.superseded_by == "TEST-2026-01"
    assert doc.metadata.is_authoritative_for_customer is False


def test_parse_internal_draft_document(internal_draft_markdown: str):
    doc = MarkdownDocumentParser.parse_string(
        internal_draft_markdown, filename="internal.md"
    )
    assert doc.metadata.status == "draft"
    assert doc.metadata.audience == "internal"
    assert doc.metadata.policy_authority == "none"
    assert doc.metadata.customer_answering is False
    assert doc.metadata.is_authoritative_for_customer is False


def test_parse_missing_delimiter(missing_delimiter_markdown: str):
    with pytest.raises(FrontmatterParsingError):
        MarkdownDocumentParser.parse_string(missing_delimiter_markdown)


def test_parse_malformed_yaml(malformed_yaml_markdown: str):
    with pytest.raises(FrontmatterParsingError):
        MarkdownDocumentParser.parse_string(malformed_yaml_markdown)


def test_parse_missing_required_fields(missing_required_field_markdown: str):
    with pytest.raises(MissingMetadataError):
        MarkdownDocumentParser.parse_string(missing_required_field_markdown)


def test_parse_nonexistent_file():
    with pytest.raises(DocumentNotFoundError):
        MarkdownDocumentParser.parse_file("nonexistent_path/file.md")
