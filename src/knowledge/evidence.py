"""Domain models for knowledge authority, evidence filtering, and EvidencePack packaging."""

from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from src.core.models import CitationSource, DocumentMetadata, KnowledgeChunk
from src.retrieval.models import RetrievalResult, RetrievalStrategy


class ExclusionReason(str, Enum):
    """Explicit reasons why a retrieved chunk is excluded from approved customer evidence."""

    SUPERSEDED = "superseded"
    INTERNAL_AUDIENCE = "internal_audience"
    CUSTOMER_ANSWERING_FALSE = "customer_answering_false"
    DRAFT_STATUS = "draft_status"
    POLICY_AUTHORITY_NONE = "policy_authority_none"
    INACTIVE_STATUS = "inactive_status"
    LOW_RELEVANCE = "low_relevance"
    DUPLICATE = "duplicate"


class ApprovedEvidence(BaseModel):
    """A retrieved chunk that has passed authority, supersession, and safety resolution."""

    chunk: KnowledgeChunk = Field(..., description="The approved knowledge chunk")
    retrieval_score: float = Field(..., description="Score assigned by the retriever")
    retrieval_rank: int = Field(..., description="Original rank from the retriever")
    retrieval_strategy: str = Field(..., description="Strategy that retrieved this chunk")

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


class ExcludedEvidence(BaseModel):
    """A retrieved chunk that was excluded from customer-facing evidence with an explicit reason."""

    chunk: KnowledgeChunk = Field(..., description="The excluded knowledge chunk")
    reason: ExclusionReason = Field(..., description="Deterministic reason for exclusion")
    details: Optional[str] = Field(default=None, description="Additional explanatory context")
    retrieval_score: float = Field(..., description="Score assigned by the retriever")
    retrieval_rank: int = Field(..., description="Original rank from the retriever")
    retrieval_strategy: str = Field(..., description="Strategy that retrieved this chunk")

    @property
    def chunk_id(self) -> str:
        return self.chunk.chunk_id

    @property
    def document_id(self) -> str:
        return self.chunk.document_id

    @property
    def filename(self) -> str:
        return self.chunk.filename


class EvidencePack(BaseModel):
    """The authoritative evidence pack produced after knowledge resolution."""

    query: str = Field(..., description="User query evaluated")
    approved_evidence: List[ApprovedEvidence] = Field(
        default_factory=list, description="Authoritative customer-facing evidence items"
    )
    excluded_evidence: List[ExcludedEvidence] = Field(
        default_factory=list, description="Retrieved chunks excluded during authority resolution"
    )
    conflict_detected: bool = Field(
        default=False, description="True if genuine contradiction exists between active official sources"
    )
    conflict_evidence: List[ApprovedEvidence] = Field(
        default_factory=list, description="Conflicting evidence items preserved for explanation"
    )
    evidence_sufficient: bool = Field(
        default=False, description="True if evidence is sufficient to ground an answer"
    )
    resolution_reason: str = Field(
        default="", description="Human-readable explanation of the resolution outcome"
    )
    handoff_recommended: bool = Field(
        default=False, description="Whether resolution recommends human support assistance"
    )

    @property
    def citations(self) -> List[CitationSource]:
        """Unique ordered list of citation sources from approved and conflict evidence."""
        seen = set()
        cits: List[CitationSource] = []
        for item in self.approved_evidence + self.conflict_evidence:
            key = (item.filename, item.heading)
            if key not in seen:
                seen.add(key)
                cits.append(item.citation_source)
        return cits

    @property
    def citation_strings(self) -> List[str]:
        """List of formatted citation strings [filename > heading]."""
        return [c.formatted() for c in self.citations]
