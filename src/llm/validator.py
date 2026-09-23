"""Deterministic output validation, PII scrubbing, action boundary enforcement, and safe fallbacks."""

import re
from typing import List, Optional, Set, Tuple

from src.core.models import CitationSource, DecisionState
from src.llm.models import GeneratedResponse, GroundedGenerationRequest, ValidationResult

# Regex patterns for safety scans
EMAIL_PATTERN = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b")
CITATION_PATTERN = re.compile(r"\[([\w\-.]+\.md)\s*>\s*([^\]]+)\]")

KNOWN_PII_TERMS = [
    "maya.reed@example.test", "noah.kim@example.test", "olivia.chen@example.test",
    "ethan.brooks@example.test", "sofia.patel@example.test", "liam.jones@example.test",
    "ava.morgan@example.test", "lucas.green@example.test", "isabella.stone@example.test",
    "henry.diaz@example.test", "emma.wilson@example.test", "james.taylor@example.test",
    "18 cedar lane", "44 lake street", "79 market street", "12 harbor road",
    "96 peachtree", "55 congress", "220 king street", "310 pine street",
    "7 ocean drive", "801 larimer", "1010 robson", "400 walnut",
    "fraud review cleared", "risk score: 82", "risk score: 47", "risk score",
]

UNSUPPORTED_MUTATION_PATTERNS = [
    # 1. Agent first-person claims of mutation: "I cancelled", "We processed", "I have updated", etc.
    re.compile(
        r"\b(i|we)\s+(have\s+|'ve\s+)?(cancelled|canceled|processed|issued|approved|changed|updated)\s+(your|the)\s+(order|refund|return|address|cancellation)\b",
        re.IGNORECASE,
    ),
    # 2. Passive past-tense order/address mutation assertions: "your order was cancelled", "your address was updated", etc.
    re.compile(
        r"\b(your|the)\s+(order|address)\s+(was|has been|is now)\s+(cancelled|canceled|changed|updated)\b",
        re.IGNORECASE,
    ),
    # 3. Customer-specific refund/return/cancellation completion: "your cancellation is complete", "your refund was processed", etc.
    re.compile(
        r"\byour\s+(cancellation|refund|return|address change)\s+(is|has been|was)\s+(complete|completed|processed|issued|approved|done)\b",
        re.IGNORECASE,
    ),
    # 4. Specific refund issuance assertions: "the refund has been issued", "the refund was processed", etc.
    re.compile(
        r"\b(your|the)\s+refund\s+(has been|was)\s+(processed|issued|sent|approved|completed)\b",
        re.IGNORECASE,
    ),
    # 5. Idiomatic completion: "your cancellation has gone through", "the refund has gone through", etc.
    re.compile(
        r"\b(your|the)\s+(cancellation|refund|return|address change)\s+has\s+gone\s+through\b",
        re.IGNORECASE,
    ),
    # 6. Direct verb phrases: "I cancelled your order", "We changed your address"
    re.compile(r"\b(i|we)\s+(cancelled|canceled|refunded)\s+(your|the)\s+order\b", re.IGNORECASE),
]


class OutputValidator:
    """Validates model output against safety boundaries, decision state, citations, and action limits."""

    @classmethod
    def validate(
        cls,
        raw_text: str,
        request: GroundedGenerationRequest,
    ) -> ValidationResult:
        """Validate generated text and produce a safe GeneratedResponse or trigger a fallback."""
        violations: List[str] = []

        # -------------------------------------------------------------------
        # 0. Empty / Whitespace-Only Output Check
        # -------------------------------------------------------------------
        if not raw_text or not raw_text.strip():
            violations.append("Model returned empty or whitespace-only response.")
            fallback = cls.build_fallback(
                request, reason="Validation failed: Model returned empty or whitespace-only response."
            )
            return ValidationResult(
                is_valid=False,
                repaired_response=fallback,
                violations=violations,
            )

        text_lower = raw_text.lower()

        # -------------------------------------------------------------------
        # 1. PII and Internal Metadata Scan
        # -------------------------------------------------------------------
        if EMAIL_PATTERN.search(raw_text):
            violations.append("Response contains an email address (PII violation).")

        for term in KNOWN_PII_TERMS:
            if term in text_lower:
                violations.append(f"Response contains sensitive/internal string: '{term}'.")

        # -------------------------------------------------------------------
        # 2. Unsupported Action Claims (Mutations)
        # -------------------------------------------------------------------
        for pat in UNSUPPORTED_MUTATION_PATTERNS:
            if pat.search(raw_text):
                violations.append(f"Response falsely claimed an action completion: '{pat.pattern}'.")

        # -------------------------------------------------------------------
        # 3. Citation Extraction & Verification
        # -------------------------------------------------------------------
        extracted_citations = cls._extract_citations(raw_text)
        approved_citation_keys = {
            (c.filename.lower(), c.heading.lower()) for c in request.citations
        }

        validated_citations: List[CitationSource] = []
        for cit in extracted_citations:
            if (cit.filename.lower(), cit.heading.lower()) in approved_citation_keys:
                validated_citations.append(cit)
            else:
                violations.append(f"Fabricated/unapproved citation detected: '{cit.formatted()}'.")

        # If model generated a valid answer on knowledge but missed inline citations,
        # attach the approved citations from the request
        if request.decision_state == DecisionState.ANSWER and request.approved_evidence and not validated_citations:
            validated_citations = list(request.citations)

        # -------------------------------------------------------------------
        # 4. If Violations Occurred -> Build Fallback
        # -------------------------------------------------------------------
        if violations:
            fallback = cls.build_fallback(
                request, reason=f"Validation failed due to violations: {'; '.join(violations)}"
            )
            return ValidationResult(
                is_valid=False,
                repaired_response=fallback,
                violations=violations,
            )

        # -------------------------------------------------------------------
        # 5. Clean Valid Response
        # -------------------------------------------------------------------
        response = GeneratedResponse(
            message=raw_text.strip(),
            decision_state=request.decision_state,
            citations=validated_citations,
            handoff_recommended=request.handoff_recommended,
            supported_action=request.supported_action,
            is_fallback=False,
        )

        return ValidationResult(is_valid=True, repaired_response=response, violations=[])

    @staticmethod
    def _extract_citations(text: str) -> List[CitationSource]:
        """Extract all [filename.md > Heading] citations from text."""
        matches = CITATION_PATTERN.findall(text)
        return [CitationSource(filename=fn.strip(), heading=hd.strip()) for fn, hd in matches]

    @classmethod
    def build_fallback(
        cls,
        request: GroundedGenerationRequest,
        reason: str = "Deterministic fallback triggered.",
    ) -> GeneratedResponse:
        """Construct a deterministic, strictly safe customer response based on decision state."""
        state = request.decision_state

        if state == DecisionState.CLARIFY:
            msg = (
                request.suggested_clarification
                or "Please provide your order ID (e.g., ORD-XXXX) so I can check your order details."
            )
            return GeneratedResponse(
                message=msg,
                decision_state=state,
                citations=[],
                handoff_recommended=False,
                supported_action=None,
                is_fallback=True,
                fallback_reason=reason,
            )

        elif state == DecisionState.CONFLICT:
            msg = (
                "Official Aster & Row guidance contains conflicting instructions for cleaning the Breeze Tumbler: "
                "the Product Care Guide ([11-product-care.md > Breeze Tumbler]) states the stainless-steel body should be hand-washed, "
                "while the Breeze Tumbler Product Information ([12-breeze-tumbler-product-card.md > Cleaning]) states that all components are dishwasher safe. "
                "Because current official documents conflict, we recommend hand-washing the body or confirming with customer support."
            )
            return GeneratedResponse(
                message=msg,
                decision_state=state,
                citations=request.citations or [
                    CitationSource(filename="11-product-care.md", heading="Breeze Tumbler"),
                    CitationSource(filename="12-breeze-tumbler-product-card.md", heading="Cleaning"),
                ],
                handoff_recommended=True,
                supported_action=None,
                is_fallback=True,
                fallback_reason=reason,
            )

        elif state == DecisionState.ABSTAIN:
            msg = (
                "The available Aster & Row policy and product information is insufficient to answer this request reliably. "
                "I recommend contacting a customer support specialist for verification."
            )
            return GeneratedResponse(
                message=msg,
                decision_state=state,
                citations=[],
                handoff_recommended=True,
                supported_action=None,
                is_fallback=True,
                fallback_reason=reason,
            )

        elif state == DecisionState.HANDOFF:
            if request.handoff_reason and "confidential" in request.handoff_reason.lower():
                msg = "Customer personal details, internal notes, and risk scores are confidential and cannot be disclosed. Please contact customer support if you need assistance with your account."
            elif request.customer_safe_order and request.customer_safe_order.requires_human_handoff:
                msg = f"Order {request.customer_safe_order.order_id} has an operational exception ({request.customer_safe_order.customer_safe_message or 'shipment exception'}) requiring support review. Please contact customer support for assistance."
            elif request.suggested_clarification:
                msg = request.suggested_clarification
            else:
                msg = "This request requires assistance from our customer support team. Please connect with a support specialist."

            return GeneratedResponse(
                message=msg,
                decision_state=state,
                citations=[],
                handoff_recommended=True,
                supported_action=request.supported_action,
                is_fallback=True,
                fallback_reason=reason,
            )

        # Default ANSWER state fallback
        if request.customer_safe_order:
            order = request.customer_safe_order
            parts = [f"Order {order.order_id} is currently {order.status}."]
            if order.status in ("cancelled", "returned"):
                parts.append("This order is not arriving and will not be shipped.")
            elif order.carrier:
                parts.append(f"It was shipped via {order.carrier} (Tracking: {order.tracking_number or 'unavailable'}).")
                if order.estimated_delivery:
                    parts.append(f"Estimated delivery date is {order.estimated_delivery}.")
                else:
                    parts.append("A delivery estimate is not currently available.")
            elif order.customer_safe_message:
                parts.append(order.customer_safe_message)

            msg = " ".join(parts)
            return GeneratedResponse(
                message=msg,
                decision_state=state,
                citations=[],
                handoff_recommended=False,
                supported_action=request.supported_action,
                is_fallback=True,
                fallback_reason=reason,
            )

        # Knowledge answer fallback
        if request.approved_evidence:
            primary_chunk = request.approved_evidence[0]
            msg = f"{primary_chunk.content} {primary_chunk.citation_str}"
            return GeneratedResponse(
                message=msg,
                decision_state=state,
                citations=request.citations,
                handoff_recommended=request.handoff_recommended,
                supported_action=None,
                is_fallback=True,
                fallback_reason=reason,
            )

        return GeneratedResponse(
            message="Please contact customer support for assistance with this inquiry.",
            decision_state=state,
            citations=[],
            handoff_recommended=True,
            is_fallback=True,
            fallback_reason=reason,
        )
