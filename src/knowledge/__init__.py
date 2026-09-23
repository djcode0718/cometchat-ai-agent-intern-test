"""Knowledge base parsing, chunking, and ingestion services."""

from src.knowledge.chunker import SectionAwareChunker, estimate_token_count, slugify
from src.knowledge.exceptions import (
    ChunkingError,
    DocumentNotFoundError,
    FrontmatterParsingError,
    KnowledgeBaseError,
    MissingMetadataError,
)
from src.knowledge.parser import MarkdownDocumentParser
from src.knowledge.service import (
    IngestionResult,
    KnowledgeIngestionService,
    ingest_knowledge_base,
)

__all__ = [
    "KnowledgeBaseError",
    "DocumentNotFoundError",
    "FrontmatterParsingError",
    "MissingMetadataError",
    "ChunkingError",
    "MarkdownDocumentParser",
    "SectionAwareChunker",
    "slugify",
    "estimate_token_count",
    "IngestionResult",
    "KnowledgeIngestionService",
    "ingest_knowledge_base",
]
