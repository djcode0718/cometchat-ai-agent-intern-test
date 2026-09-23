"""Domain models for Aster & Row support agent."""

from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, Field, field_validator


class DocumentMetadata(BaseModel):
    """Structured frontmatter metadata for a knowledge-base document."""

    document_id: str = Field(..., description="Unique document ID (e.g., RET-2026-01)")
    title: str = Field(..., description="Document title")
    status: Literal["active", "superseded", "draft"] = Field(
        ..., description="Document lifecycle status"
    )
    effective_date: Union[date, str] = Field(
        ..., description="Date document became effective"
    )
    last_reviewed: Optional[Union[date, str]] = Field(
        default=None, description="Date document was last reviewed"
    )
    superseded_date: Optional[Union[date, str]] = Field(
        default=None, description="Date document was superseded"
    )
    audience: Literal["customer", "internal"] = Field(
        ..., description="Target audience"
    )
    policy_authority: Literal["official", "none"] = Field(
        ..., description="Authority level of the policy"
    )
    supersedes: Optional[str] = Field(
        default=None, description="Document ID this replaces"
    )
    superseded_by: Optional[str] = Field(
        default=None, description="Document ID that replaces this"
    )
    customer_answering: bool = Field(
        default=True,
        description="Whether this document can be used to answer customer questions",
    )

    @field_validator("effective_date", "last_reviewed", "superseded_date", mode="before")
    @classmethod
    def normalize_dates(cls, v: Any) -> Optional[str]:
        if v is None:
            return None
        if isinstance(v, (date, datetime)):
            return v.strftime("%Y-%m-%d")
        return str(v).strip()

    @property
    def is_authoritative_for_customer(self) -> bool:
        """Check if document is official, active, and customer-facing."""
        return (
            self.status == "active"
            and self.policy_authority == "official"
            and self.customer_answering is True
        )


class Section(BaseModel):
    """A structured markdown section."""

    heading: str = Field(..., description="Section heading text without leading hashes")
    level: int = Field(default=2, description="Heading level (1 for #, 2 for ##, etc.)")
    content: str = Field(..., description="Clean markdown content of the section")
    start_line: int = Field(default=1, description="1-indexed starting line in raw document")
    end_line: int = Field(default=1, description="1-indexed ending line in raw document")


class CitationSource(BaseModel):
    """Citation reference pointing to a source document and heading."""

    filename: str = Field(..., description="Source filename (e.g. 01-returns-policy-current.md)")
    heading: str = Field(..., description="Section heading")

    def formatted(self) -> str:
        """Produce the standard citation string: [filename.md > Heading]."""
        return f"[{self.filename} > {self.heading}]"

    def __str__(self) -> str:
        return self.formatted()


class KnowledgeDocument(BaseModel):
    """Full representation of a parsed knowledge-base document."""

    file_path: Path = Field(..., description="Absolute path to markdown source")
    filename: str = Field(..., description="Base filename (e.g., 01-returns-policy-current.md)")
    metadata: DocumentMetadata = Field(..., description="Parsed and validated metadata")
    raw_content: str = Field(..., description="Original raw file content including frontmatter")
    body: str = Field(..., description="Markdown body excluding YAML frontmatter")
    sections: List[Section] = Field(default_factory=list, description="Extracted sections")


class KnowledgeChunk(BaseModel):
    """Deterministic section-aware chunk designed for indexing and retrieval."""

    chunk_id: str = Field(..., description="Deterministic unique chunk identifier")
    document_id: str = Field(..., description="Parent document ID (e.g., RET-2026-01)")
    filename: str = Field(..., description="Source filename (e.g., 01-returns-policy-current.md)")
    heading: str = Field(..., description="Section heading")
    heading_hierarchy: List[str] = Field(
        default_factory=list, description="Breadcrumb hierarchy (e.g. [Document Title, Section])"
    )
    content: str = Field(..., description="Text content of the chunk")
    metadata: DocumentMetadata = Field(..., description="Inherited document metadata")
    token_count_estimate: Optional[int] = Field(
        default=None, description="Rough word/token count estimate for retrieval context sizing"
    )

    @property
    def citation_source(self) -> CitationSource:
        """Return structured citation source for this chunk."""
        return CitationSource(filename=self.filename, heading=self.heading)

    @property
    def citation_str(self) -> str:
        """Return formatted citation string."""
        return self.citation_source.formatted()


MessageRole = Literal["user", "assistant", "system", "tool"]


class Message(BaseModel):
    """Individual conversation message within a session."""

    role: MessageRole = Field(..., description="Sender role")
    content: str = Field(..., description="Message text content")
    timestamp: datetime = Field(
        default_factory=datetime.utcnow, description="Message creation timestamp"
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict, description="Optional message-level metadata"
    )


class Session(BaseModel):
    """In-memory multi-turn conversation session."""

    session_id: str = Field(..., description="Unique session identifier")
    messages: List[Message] = Field(
        default_factory=list, description="Ordered conversation history"
    )
    active_order_id: Optional[str] = Field(
        default=None, description="Active order ID referenced in session"
    )
    current_topic: Optional[str] = Field(
        default=None, description="Active policy topic or context"
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict, description="Session-level metadata"
    )

    def add_message(
        self,
        role: MessageRole,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Message:
        """Append a message to the conversation history."""
        msg = Message(role=role, content=content, metadata=metadata or {})
        self.messages.append(msg)
        return msg

    def clear(self) -> None:
        """Clear conversation history and session state."""
        self.messages.clear()
        self.active_order_id = None
        self.current_topic = None
        self.metadata.clear()
