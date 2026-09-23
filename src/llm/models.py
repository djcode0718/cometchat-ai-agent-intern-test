"""Domain models for grounded generation requests, outputs, and validation."""

from typing import List, Optional
from pydantic import BaseModel, Field

from src.core.models import CitationSource, DecisionState
from src.knowledge.evidence import ApprovedEvidence
from src.tools.order_models import CustomerSafeOrder


class GroundedGenerationRequest(BaseModel):
    """Encapsulates all sanitized evidence and decision state required for grounded generation."""

    user_query: str = Field(..., description="The user's query text")
    decision_state: DecisionState = Field(..., description="Deterministic decision state")
    decision_reason: str = Field(..., description="Deterministic rationale for this decision")
    approved_evidence: List[ApprovedEvidence] = Field(
        default_factory=list, description="Approved customer-facing knowledge chunks"
    )
    conflict_evidence: List[ApprovedEvidence] = Field(
        default_factory=list, description="Approved chunks exhibiting genuine policy conflict"
    )
    customer_safe_order: Optional[CustomerSafeOrder] = Field(
        default=None, description="Sanitized and reconciled customer-safe order evidence"
    )
    suggested_clarification: Optional[str] = Field(
        default=None, description="Suggested question if state is CLARIFY"
    )
    handoff_recommended: bool = Field(
        default=False, description="Whether human support is recommended"
    )
    handoff_reason: Optional[str] = Field(
        default=None, description="Explanation for human handoff"
    )
    supported_action: Optional[str] = Field(
        default=None, description="Read-only action performed (e.g. 'order_lookup'). Never a mutation."
    )
    citations: List[CitationSource] = Field(
        default_factory=list, description="Approved list of citation sources"
    )

    @property
    def approved_citation_strings(self) -> List[str]:
        return [c.formatted() for c in self.citations]


class GeneratedResponse(BaseModel):
    """The validated final response produced for the customer."""

    message: str = Field(..., description="The natural-language message for the customer")
    decision_state: DecisionState = Field(..., description="Decision state corresponding to this response")
    citations: List[CitationSource] = Field(
        default_factory=list, description="Validated citations associated with factual claims"
    )
    handoff_recommended: bool = Field(
        default=False, description="Whether the response recommends human handoff"
    )
    supported_action: Optional[str] = Field(
        default=None, description="Action performed, if any (strictly read-only)"
    )
    is_fallback: bool = Field(
        default=False, description="True if response was generated via deterministic fallback"
    )
    fallback_reason: Optional[str] = Field(
        default=None, description="Reason why fallback was triggered"
    )

    @property
    def citation_strings(self) -> List[str]:
        return [c.formatted() for c in self.citations]


class ValidationResult(BaseModel):
    """Outcome of validating a model-generated response against safety boundaries."""

    is_valid: bool = Field(..., description="True if generated response passed all safety checks")
    repaired_response: Optional[GeneratedResponse] = Field(
        default=None, description="Repaired or validated response object"
    )
    violations: List[str] = Field(
        default_factory=list, description="List of detected safety or citation violations"
    )
