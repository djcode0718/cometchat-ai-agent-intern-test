"""Section-aware chunking strategy for knowledge-base documents."""

import re
from typing import List

from src.core.models import KnowledgeChunk, KnowledgeDocument, Section


def slugify(text: str) -> str:
    """Convert text into a deterministic, URL-friendly slug."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    return text.strip("-") or "section"


def estimate_token_count(text: str) -> int:
    """Rough estimate of token count (approximated as words * 1.3)."""
    words = len(text.split())
    return max(1, int(words * 1.3))


class SectionAwareChunker:
    """Splits KnowledgeDocument into deterministic section-aware KnowledgeChunk objects."""

    def __init__(self, include_h1_overview_chunks: bool = True) -> None:
        self.include_h1_overview_chunks = include_h1_overview_chunks

    def chunk_document(self, doc: KnowledgeDocument) -> List[KnowledgeChunk]:
        """Split a KnowledgeDocument into granular, section-aware KnowledgeChunk instances."""
        chunks: List[KnowledgeChunk] = []
        seen_slugs: dict[str, int] = {}
        doc_title = doc.metadata.title

        # Identify H1 title if present in sections
        h1_heading = doc_title
        for sec in doc.sections:
            if sec.level == 1 and sec.heading:
                h1_heading = sec.heading
                break

        for sec in doc.sections:
            clean_content = sec.content.strip()

            # Skip sections with no content unless it's a critical top-level container with text
            if not clean_content:
                continue

            heading_name = sec.heading
            hierarchy = [h1_heading]
            if sec.level > 1 and heading_name != h1_heading:
                hierarchy.append(heading_name)

            # Generate unique deterministic chunk_id
            base_slug = slugify(heading_name)
            seen_slugs[base_slug] = seen_slugs.get(base_slug, 0) + 1
            if seen_slugs[base_slug] == 1:
                chunk_id = f"{doc.metadata.document_id}::{base_slug}"
            else:
                chunk_id = f"{doc.metadata.document_id}::{base_slug}-{seen_slugs[base_slug]}"

            chunk = KnowledgeChunk(
                chunk_id=chunk_id,
                document_id=doc.metadata.document_id,
                filename=doc.filename,
                heading=heading_name,
                heading_hierarchy=hierarchy,
                content=clean_content,
                metadata=doc.metadata,
                token_count_estimate=estimate_token_count(clean_content),
            )
            chunks.append(chunk)

        # Fallback: if document has no headings at all, create a single chunk
        if not chunks and doc.body.strip():
            chunk = KnowledgeChunk(
                chunk_id=f"{doc.metadata.document_id}::full-document",
                document_id=doc.metadata.document_id,
                filename=doc.filename,
                heading=doc.metadata.title,
                heading_hierarchy=[doc.metadata.title],
                content=doc.body.strip(),
                metadata=doc.metadata,
                token_count_estimate=estimate_token_count(doc.body.strip()),
            )
            chunks.append(chunk)

        return chunks
