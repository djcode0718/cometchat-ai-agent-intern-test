"""Domain models for retrieval results and strategy definitions."""

from typing import List, Literal, Optional
from pydantic import BaseModel, Field

from src.core.models import CitationSource, DocumentMetadata, KnowledgeChunk

RetrievalStrategy = Literal["bm25", "dense", "hybrid"]


class RetrievalResult(BaseModel):
    """Encapsulates a single retrieved chunk with score, rank, and strategy metadata."""

    chunk: KnowledgeChunk = Field(..., description="The underlying KnowledgeChunk")
    score: float = Field(..., description="Retrieval or fusion score")
    rank: int = Field(..., description="1-indexed rank position in results")
    strategy: RetrievalStrategy = Field(..., description="Retrieval strategy that produced this result")

    @property
    def chunk_id(self) -> str:
        return self.chunk.chunk_id

    @property
    def document_id(self) -> str:
        return self.chunk.document_id

    @property
    def filename(self) -> str:
        return self.chunk.filename

    @property
    def heading(self) -> str:
        return self.chunk.heading

    @property
    def content(self) -> str:
        return self.chunk.content

    @property
    def metadata(self) -> DocumentMetadata:
        return self.chunk.metadata

    @property
    def citation_source(self) -> CitationSource:
        return self.chunk.citation_source

    @property
    def citation_str(self) -> str:
        return self.chunk.citation_str
