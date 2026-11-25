"""Tests for deterministic output validation, PII scrubbing, mutation claim rejection, and fallbacks."""

from typing import Optional

from src.core.models import CitationSource, DecisionState, DocumentMetadata, KnowledgeChunk
from src.knowledge.evidence import ApprovedEvidence
from src.llm.models import GroundedGenerationRequest
from src.llm.validator import OutputValidator
from src.tools.order_models import CustomerSafeOrder, CustomerSafeOrderItem


def _make_request(
    state: DecisionState = DecisionState.ANSWER,
    citations: Optional[list] = None,
    order: Optional[CustomerSafeOrder] = None,
    evidence: Optional[list] = None,
    handoff_recommended: bool = False,
    handoff_reason: Optional[str] = None,
    suggested_clarification: Optional[str] = None,
    supported_action: Optional[str] = None,
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


def test_validator_empty_and_whitespace_output_rejected():
    """Verify empty and whitespace-only outputs fail validation and trigger safe fallbacks."""
    citation = CitationSource(filename="01-returns-policy-current.md", heading="Return Window")
    request = _make_request(
        state=DecisionState.ANSWER,
        citations=[citation],
    )

    empty_inputs = ["", " ", "   ", "\n", "\t", "\n\t  \n"]
    for empty_text in empty_inputs:
        result = OutputValidator.validate(empty_text, request)
        assert result.is_valid is False, f"Failed to reject empty input: {repr(empty_text)}"
        assert any("empty or whitespace" in v for v in result.violations)
        assert result.repaired_response is not None
        assert result.repaired_response.is_fallback is True
        assert len(result.repaired_response.message.strip()) > 0


def test_validator_strengthened_mutation_claims_rejected():
    """Verify all direct past tense and noun-phrase mutation claims are rejected."""
    request = _make_request(
        state=DecisionState.ANSWER,
        supported_action="order_lookup",
    )

    rejected_claims = [
        # Cancellation
        "I cancelled your order.",
        "We cancelled your order.",
        "I canceled your order.",
        "We canceled your order.",
        "Your order was cancelled.",
        "Your order was canceled.",
        "Your cancellation has gone through.",
        "Your cancellation is complete.",
        "Your cancellation has been processed.",
        # Refund
        "I processed your refund.",
        "We processed your refund.",
        "I issued your refund.",
        "We issued your refund.",
        "Your refund was processed.",
        "Your refund has been issued.",
        "Your refund is complete.",
        "Your refund has been completed.",
        # Return
        "I processed your return.",
        "We processed your return.",
        "Your return was processed.",
        "Your return is complete.",
        "Your return has been completed.",
        # Address
        "I changed your address.",
        "We changed your address.",
        "I updated your address.",
        "We updated your address.",
        "Your address was updated.",
        "Your address change is complete.",
    ]

    for claim in rejected_claims:
        result = OutputValidator.validate(claim, request)
        assert result.is_valid is False, f"Failed to reject mutation claim: '{claim}'"
        assert any("falsely claimed an action completion" in v for v in result.violations)
        assert result.repaired_response.is_fallback is True


def test_validator_informational_policy_statements_remain_valid():
    """Verify general informational and policy statements are NOT falsely flagged as mutations."""
    citation = CitationSource(filename="01-returns-policy-current.md", heading="Return Window")
    request = _make_request(
        state=DecisionState.ANSWER,
        citations=[citation],
    )

    valid_policy_statements = [
        "Your order can be cancelled within 30 minutes [01-returns-policy-current.md > Return Window].",
        "Refunds are generally processed after the return is approved [01-returns-policy-current.md > Return Window].",
        "Returns can be completed within the applicable return window [01-returns-policy-current.md > Return Window].",
        "Customers can update their address before shipment [01-returns-policy-current.md > Return Window].",
    ]

    for statement in valid_policy_statements:
        result = OutputValidator.validate(statement, request)
        assert result.is_valid is True, f"Incorrectly rejected valid statement: '{statement}'. Violations: {result.violations}"
        assert result.repaired_response.is_false is False if hasattr(result.repaired_response, "is_false") else (result.repaired_response.is_fallback is False)


def _make_test_approved_chunk(doc_id: str, filename: str, heading: str, content: str) -> ApprovedEvidence:
    meta = DocumentMetadata(
        document_id=doc_id,
        title=filename,
        status="active",
        effective_date="2026-03-01",
        audience="customer",
        policy_authority="official",
        customer_answering=True,
    )
    chunk = KnowledgeChunk(
        chunk_id=f"{doc_id}::{heading}",
        document_id=doc_id,
        filename=filename,
        heading=heading,
        content=content,
        metadata=meta,
        token_count=len(content.split()),
        character_count=len(content),
    )
    return ApprovedEvidence(
        chunk=chunk,
        retrieval_score=0.9,
        retrieval_rank=1,
        retrieval_strategy="hybrid",
    )


def test_fallback_empty_evidence():
    """Verify fallback with empty evidence returns safe fallback without citations."""
    request = _make_request(
        state=DecisionState.ANSWER,
        evidence=[],
        citations=[],
    )
    fallback = OutputValidator.build_fallback(request)
    assert fallback.is_fallback is True
    assert "Please contact customer support" in fallback.message
    assert len(fallback.citations) == 0


def test_fallback_single_chunk():
    """Verify fallback with a single chunk formats heading, content, and citation correctly."""
    chunk = _make_test_approved_chunk(
        "DOC-RET", "01-returns-policy-current.md", "Return Window", "Standard returns accepted within 30 days."
    )
    request = _make_request(
        state=DecisionState.ANSWER,
        evidence=[chunk],
        citations=[chunk.citation_source],
    )
    fallback = OutputValidator.build_fallback(request)
    assert fallback.is_fallback is True
    assert "### Return Window" in fallback.message
    assert "Standard returns accepted within 30 days." in fallback.message
    assert "[01-returns-policy-current.md > Return Window]" in fallback.message
    assert len(fallback.citations) == 1
    assert fallback.citations[0].filename == "01-returns-policy-current.md"


def test_fallback_multiple_chunks_included():
    """Verify fallback includes multiple approved chunks separated by headings up to budget."""
    chunk1 = _make_test_approved_chunk(
        "DOC-RET", "01-returns-policy-current.md", "Standard Returns", "Returns are accepted within 30 days."
    )
    chunk2 = _make_test_approved_chunk(
        "DOC-RET", "01-returns-policy-current.md", "TrailPlus Extended Window", "TrailPlus members receive 45 days."
    )
    chunk3 = _make_test_approved_chunk(
        "DOC-SHIP", "02-shipping-policy.md", "Expedited Shipping", "Expedited shipping delivers in 2 business days."
    )
    request = _make_request(
        state=DecisionState.ANSWER,
        evidence=[chunk1, chunk2, chunk3],
        citations=[chunk1.citation_source, chunk2.citation_source, chunk3.citation_source],
    )
    fallback = OutputValidator.build_fallback(request)

    assert fallback.is_fallback is True
    assert "### Standard Returns" in fallback.message
    assert "### TrailPlus Extended Window" in fallback.message
    assert "### Expedited Shipping" in fallback.message
    assert len(fallback.citations) == 3
    assert {c.heading for c in fallback.citations} == {
        "Standard Returns", "TrailPlus Extended Window", "Expedited Shipping"
    }


def test_fallback_deduplication():
    """Verify duplicate chunks by chunk_id and content hash are emitted only once."""
    chunk1 = _make_test_approved_chunk(
        "DOC-RET", "01-returns-policy-current.md", "Return Window", "Standard returns accepted within 30 days."
    )
    chunk1_dup = _make_test_approved_chunk(
        "DOC-RET", "01-returns-policy-current.md", "Return Window", "Standard returns accepted within 30 days."
    )
    chunk2 = _make_test_approved_chunk(
        "DOC-RET", "01-returns-policy-current.md", "Condition", "Items must be unworn."
    )
    # Different chunk id but identical content
    chunk2_dup_content = _make_test_approved_chunk(
        "DOC-RET-COPY", "01-returns-policy-current.md", "Condition Copy", "Items must be unworn."
    )

    request = _make_request(
        state=DecisionState.ANSWER,
        evidence=[chunk1, chunk1_dup, chunk2, chunk2_dup_content],
        citations=[chunk1.citation_source, chunk2.citation_source],
    )
    fallback = OutputValidator.build_fallback(request)

    assert fallback.message.count("Standard returns accepted within 30 days.") == 1
    assert fallback.message.count("Items must be unworn.") == 1
    assert len(fallback.citations) == 2


def test_fallback_1500_char_boundary_and_citation_alignment():
    """Verify fallback never exceeds 1500 chars and citations match only emitted chunks."""
    content_chunk1 = "A" * 600
    content_chunk2 = "B" * 600
    content_chunk3 = "C" * 500  # Will not fit within 1500 limit with headers and citations

    chunk1 = _make_test_approved_chunk("DOC-1", "doc1.md", "Section 1", content_chunk1)
    chunk2 = _make_test_approved_chunk("DOC-2", "doc2.md", "Section 2", content_chunk2)
    chunk3 = _make_test_approved_chunk("DOC-3", "doc3.md", "Section 3", content_chunk3)

    request = _make_request(
        state=DecisionState.ANSWER,
        evidence=[chunk1, chunk2, chunk3],
        citations=[chunk1.citation_source, chunk2.citation_source, chunk3.citation_source],
    )
    fallback = OutputValidator.build_fallback(request)

    assert len(fallback.message) <= 1500
    assert "Section 1" in fallback.message
    assert "Section 2" in fallback.message
    assert "Section 3" not in fallback.message

    # Crucial: citation alignment - only chunk1 and chunk2 should be in citations
    emitted_headings = [c.heading for c in fallback.citations]
    assert "Section 1" in emitted_headings
    assert "Section 2" in emitted_headings
    assert "Section 3" not in emitted_headings
    assert len(fallback.citations) == 2


def test_fallback_single_oversized_chunk_safely_truncated():
    """Verify single chunk exceeding 1500 chars is cleanly truncated with citation intact."""
    oversized_content = "X" * 2000
    chunk = _make_test_approved_chunk("DOC-BIG", "big.md", "Long Policy", oversized_content)

    request = _make_request(
        state=DecisionState.ANSWER,
        evidence=[chunk],
        citations=[chunk.citation_source],
    )
    fallback = OutputValidator.build_fallback(request)

    assert len(fallback.message) <= 1500
    assert fallback.message.startswith("### Long Policy\n")
    assert fallback.message.endswith("... [big.md > Long Policy]")
    assert len(fallback.citations) == 1
    assert fallback.citations[0].filename == "big.md"

