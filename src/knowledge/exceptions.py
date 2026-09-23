"""Exceptions for knowledge base parsing, chunking, and ingestion."""


class KnowledgeBaseError(Exception):
    """Base exception for all knowledge base errors."""


class DocumentNotFoundError(KnowledgeBaseError):
    """Raised when a specified document or directory cannot be found."""


class FrontmatterParsingError(KnowledgeBaseError):
    """Raised when YAML frontmatter is missing, malformed, or invalid."""


class MissingMetadataError(KnowledgeBaseError):
    """Raised when required frontmatter metadata fields are missing or invalid."""


class ChunkingError(KnowledgeBaseError):
    """Raised when document chunking fails."""
