"""Pydantic data models for evaluation cases, turn expectations, and suite reporting."""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from src.agent.state import DecisionState


class Message(BaseModel):
    """Single user or system message in an evaluation case."""

    role: str = "user"
    content: str


class CaseExpectation(BaseModel):
    """Assertion expectations for an evaluation case."""

    must_include: List[str] = Field(default_factory=list)
    must_not_include: List[str] = Field(default_factory=list)
    must_include_concepts: List[str] = Field(default_factory=list)
    must_not_follow: List[str] = Field(default_factory=list)
    must_not_invent: List[str] = Field(default_factory=list)
    must_refuse_to_disclose: List[str] = Field(default_factory=list)
    must_ask_for: List[str] = Field(default_factory=list)
    must_not_silently_choose_one: bool = False
    required_sources: List[str] = Field(default_factory=list)
    forbidden_sources_as_authority: List[str] = Field(default_factory=list)
    tool: Optional[str] = None
    tool_arguments: Optional[Dict[str, Any]] = None
    handoff: Optional[bool] = None
    expected_decision_state: Optional[DecisionState] = None


class EvaluationCase(BaseModel):
    """Structured specification of an evaluation scenario."""

    id: str
    category: str
    description: Optional[str] = None
    messages: List[Message]
    expect: CaseExpectation


class AssertionFailure(BaseModel):
    """Details of an assertion failure."""

    assertion_type: str
    expected: Any
    actual: Any
    message: str


class TurnResult(BaseModel):
    """Result of a single turn in a multi-turn case."""

    turn_id: int
    user_query: str
    decision_state: str
    handoff_recommended: bool
    handoff_reason: Optional[str] = None
    supported_action: Optional[str] = None
    citations: List[str] = Field(default_factory=list)
    message: str
    is_fallback: bool
    fallback_reason: Optional[str] = None
    trace: Dict[str, Any] = Field(default_factory=dict)


class CaseResult(BaseModel):
    """Evaluation result for a single case."""

    case_id: str
    category: str
    passed: bool
    decision_state: str
    handoff_recommended: bool
    citations: List[str] = Field(default_factory=list)
    failures: List[AssertionFailure] = Field(default_factory=list)
    turns: List[TurnResult] = Field(default_factory=list)
    failure_category: Optional[str] = None
    notes: Optional[str] = None


class SuiteResult(BaseModel):
    """Summary of evaluation run across all cases."""

    suite_name: str
    total_cases: int
    passed_cases: int
    failed_cases: int
    pass_rate: float
    category_breakdown: Dict[str, Dict[str, int]]
    results: List[CaseResult]
