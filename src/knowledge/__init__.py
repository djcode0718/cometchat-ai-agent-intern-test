"""Knowledge base parsing, chunking, authority, supersession, conflict detection, and evidence resolution."""

from src.knowledge.authority import AuthorityResolver
from src.knowledge.chunker import SectionAwareChunker, estimate_token_count, slugify
from src.knowledge.conflict import ConflictDetector, ConflictRule
from src.knowledge.evidence import (
    ApprovedEvidence,
    EvidencePack,
    ExcludedEvidence,
    ExclusionReason,
)
from src.knowledge.exceptions import (
    ChunkingError,
    DocumentNotFoundError,
    FrontmatterParsingError,
    KnowledgeBaseError,
    MissingMetadataError,
)
from src.knowledge.parser import MarkdownDocumentParser
from src.knowledge.resolver import KnowledgeResolver
from src.knowledge.service import (
    IngestionResult,
    KnowledgeIngestionService,
    ingest_knowledge_base,
)
from src.knowledge.supersession import SupersessionResolver

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
    "ExclusionReason",
    "ApprovedEvidence",
    "ExcludedEvidence",
    "EvidencePack",
    "SupersessionResolver",
    "AuthorityResolver",
    "ConflictRule",
    "ConflictDetector",
    "KnowledgeResolver",
]
