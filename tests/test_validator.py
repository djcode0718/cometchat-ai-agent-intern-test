"""Tests for deterministic output validation, PII scrubbing, mutation claim rejection, and fallbacks."""

from src.agent.state import DecisionState
from src.core.models import CitationSource, DocumentMetadata, KnowledgeChunk
from src.knowledge.evidence import ApprovedEvidence
from src.llm.models import GroundedGenerationRequest
from src.llm.validator import OutputValidator
from src.tools.order_models import CustomerSafeOrder, CustomerSafeOrderItem


def _make_request(
    state: DecisionState = DecisionState.ANSWER,
    citations: list = None,
    order: CustomerSafeOrder = None,
    evidence: list = None,
    handoff_recommended: bool = False,
    handoff_reason: str = None,
    suggested_clarification: str = None,
    supported_action: str = None,
) -> GroundedGenerationRequest:
    return GroundedGenerationRequest(
        user_query="Sample query",
        decision_state=state,
        decision_reason="Test reason",
        approved_evidence=evidence or [],
        citations=citations or [],
        customer_safe_order=order,
        handoff_recommended=handoff_recommended,
        handoff_reason=handoff_reason,
        suggested_clarification=suggested_clarification,
        supported_action=supported_action,
    )


def test_validator_valid_response_with_approved_citation():
    """Verify clean response with approved citation passes validation without fallback."""
    citation = CitationSource(filename="01-returns-policy-current.md", heading="Return Window")
    request = _make_request(
        state=DecisionState.ANSWER,
        citations=[citation],
    )

    raw_text = "You can return items within 30 days of delivery [01-returns-policy-current.md > Return Window]."
    result = OutputValidator.validate(raw_text, request)

    assert result.is_valid is True
    assert len(result.violations) == 0
    assert result.repaired_response is not None
    assert result.repaired_response.is_fallback is False
    assert len(result.repaired_response.citations) == 1
    assert result.repaired_response.citations[0].filename == "01-returns-policy-current.md"


def test_validator_fabricated_citation_rejected():
    """Verify fabricated or unapproved citation is rejected and triggers safe fallback."""
    approved_citation = CitationSource(filename="01-returns-policy-current.md", heading="Return Window")
    request = _make_request(
        state=DecisionState.ANSWER,
        citations=[approved_citation],
    )

    # Hallucinated citation
    raw_text = "You can return items forever [99-fake-policy.md > Lifetime Returns]."
    result = OutputValidator.validate(raw_text, request)

    assert result.is_valid is False
    assert any("Fabricated/unapproved citation" in v for v in result.violations)
    assert result.repaired_response.is_fallback is True


def test_validator_pii_email_leakage_rejected():
    """Verify response containing email address is rejected as PII violation."""
    request = _make_request(state=DecisionState.ANSWER)
    raw_text = "Your confirmation was sent to maya.reed@example.test with full details."

    result = OutputValidator.validate(raw_text, request)

    assert result.is_valid is False
    assert any("email address (PII violation)" in v for v in result.violations)
    assert result.repaired_response.is_fallback is True
    assert "maya.reed@example.test" not in result.repaired_response.message


def test_validator_pii_address_and_internal_metadata_rejected():
    """Verify sensitive physical address and internal risk score are rejected."""
    request = _make_request(state=DecisionState.ANSWER)
    raw_text = "Delivering to 18 Cedar Lane. Internal risk score: 82 cleared."

    result = OutputValidator.validate(raw_text, request)

    assert result.is_valid is False
    assert any("sensitive/internal string" in v for v in result.violations)
    assert result.repaired_response.is_fallback is True


def test_validator_unsupported_cancellation_action_rejected():
    """Verify response falsely claiming order was cancelled is rejected."""
    request = _make_request(
        state=DecisionState.ANSWER,
        supported_action="order_lookup",
    )
    raw_text = "I have cancelled your order ORD-1001 and your refund is on the way."

    result = OutputValidator.validate(raw_text, request)

    assert result.is_valid is False
    assert any("falsely claimed an action completion" in v for v in result.violations)
    assert result.repaired_response.is_fallback is True


def test_validator_unsupported_refund_action_rejected():
    """Verify response claiming refund processed is rejected."""
    request = _make_request(state=DecisionState.ANSWER)
    raw_text = "We have processed your refund to your original payment method."

    result = OutputValidator.validate(raw_text, request)

    assert result.is_valid is False
    assert any("falsely claimed an action completion" in v for v in result.violations)
    assert result.repaired_response.is_fallback is True


def test_validator_fallback_clarify():
    """Verify fallback for CLARIFY state returns polite clarification question."""
    request = _make_request(
        state=DecisionState.CLARIFY,
        suggested_clarification="Please provide your order ID (e.g. ORD-1001).",
    )
    fallback = OutputValidator.build_fallback(request)

    assert fallback.decision_state == DecisionState.CLARIFY
    assert fallback.is_fallback is True
    assert "Please provide your order ID" in fallback.message


def test_validator_fallback_conflict():
    """Verify fallback for CONFLICT state includes both official citations and perspectives."""
    request = _make_request(
        state=DecisionState.CONFLICT,
        citations=[
            CitationSource(filename="11-product-care.md", heading="Breeze Tumbler"),
            CitationSource(filename="12-breeze-tumbler-product-card.md", heading="Cleaning"),
        ],
        handoff_recommended=True,
    )
    fallback = OutputValidator.build_fallback(request)

    assert fallback.decision_state == DecisionState.CONFLICT
    assert fallback.handoff_recommended is True
    assert "11-product-care.md" in fallback.message
    assert "12-breeze-tumbler-product-card.md" in fallback.message
    assert "conflicting" in fallback.message.lower()


def test_validator_fallback_abstain():
    """Verify fallback for ABSTAIN state explains insufficient information and recommends support."""
    request = _make_request(
        state=DecisionState.ABSTAIN,
        handoff_recommended=True,
    )
    fallback = OutputValidator.build_fallback(request)

    assert fallback.decision_state == DecisionState.ABSTAIN
    assert fallback.handoff_recommended is True
    assert "insufficient" in fallback.message.lower()


def test_validator_fallback_handoff_security():
    """Verify fallback for HANDOFF state with security/confidentiality preserves privacy boundary."""
    request = _make_request(
        state=DecisionState.HANDOFF,
        handoff_recommended=True,
        handoff_reason="Customer PII and internal risk scores are confidential and not disclosed.",
    )
    fallback = OutputValidator.build_fallback(request)

    assert fallback.decision_state == DecisionState.HANDOFF
    assert fallback.handoff_recommended is True
    assert "confidential" in fallback.message.lower()
