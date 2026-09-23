"""Tests for section-aware document chunking."""

from src.knowledge.chunker import SectionAwareChunker, slugify
from src.knowledge.parser import MarkdownDocumentParser


def test_slugify():
    assert slugify("Standard return window") == "standard-return-window"
    assert slugify("Breeze Tumbler — Product Information") == "breeze-tumbler-product-information"
    assert slugify("What is covered?") == "what-is-covered"


def test_chunker_section_preservation(valid_markdown: str):
    doc = MarkdownDocumentParser.parse_string(valid_markdown, filename="test.md")
    chunker = SectionAwareChunker()
    chunks = chunker.chunk_document(doc)

    assert len(chunks) >= 2
    headings = [c.heading for c in chunks]
    assert "First Section" in headings
    assert "Second Section" in headings

    first_chunk = next(c for c in chunks if c.heading == "First Section")
    assert first_chunk.chunk_id == "TEST-2026-01::first-section"
    assert first_chunk.citation_str == "[test.md > First Section]"
    assert first_chunk.metadata.document_id == "TEST-2026-01"
    assert "content of the first section" in first_chunk.content


def test_chunker_deterministic_output(valid_markdown: str):
    doc = MarkdownDocumentParser.parse_string(valid_markdown, filename="test.md")
    chunker = SectionAwareChunker()
    chunks_run1 = chunker.chunk_document(doc)
    chunks_run2 = chunker.chunk_document(doc)

    assert len(chunks_run1) == len(chunks_run2)
    for c1, c2 in zip(chunks_run1, chunks_run2):
        assert c1.chunk_id == c2.chunk_id
        assert c1.content == c2.content
        assert c1.citation_str == c2.citation_str
