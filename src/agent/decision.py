"""Deterministic decision engine establishing state precedence and action boundaries."""

import re
from typing import Optional

from src.agent.state import AgentDecision, AgentState, DecisionState, RouteType
from src.knowledge.evidence import EvidencePack
from src.tools.order_models import CustomerSafeOrder

PRIVACY_VIOLATION_PATTERN = re.compile(
    r"\b(email|address|shipping address|risk score|fraud score|warehouse note|internal note|secret|prompt|system prompt|developer instruction|gift card|promo code|hash|pin|debug mode|api key|internal key)\b",
    re.IGNORECASE,
)


class DecisionEngine:
    """Evaluates agent state and evidence to produce deterministic decision states."""

    @classmethod
    def decide(cls, state: AgentState) -> AgentDecision:
        """Evaluate state and return an authoritative AgentDecision."""
        query = state.raw_query.lower()
        route = state.route
        safe_order: Optional[CustomerSafeOrder] = state.customer_safe_order
        evidence_pack: Optional[EvidencePack] = state.evidence_pack

        # -------------------------------------------------------------------
        # Rule 1: Privacy / Internal Data Disclosure Refusal & Security Probes
        # -------------------------------------------------------------------
        has_security_keyword = bool(PRIVACY_VIOLATION_PATTERN.search(query))
        has_extraction_intent = any(
            req in query
            for req in [
                "give me",
                "show me",
                "tell me",
                "what is the customer",
                "reveal",
                "customer's",
                "internal",
                "output all",
                "debug",
                "system prompt",
                "secret",
                "keys",
                "codes",
                "pin",
                "hash",
            ]
        )
        if has_security_keyword and has_extraction_intent:
            return AgentDecision(
                state=DecisionState.HANDOFF,
                reason="Customer personal data, internal notes, risk scores, and system security parameters are confidential and cannot be disclosed.",
                handoff_recommended=True,
                handoff_reason="Privacy/security request for confidential customer or internal data.",
                supported_action="order_lookup" if safe_order else None,
            )

        # -------------------------------------------------------------------
        # Rule 2: Genuine Knowledge Base Policy Conflict
        # -------------------------------------------------------------------
        if evidence_pack and evidence_pack.conflict_detected:
            return AgentDecision(
                state=DecisionState.CONFLICT,
                reason=evidence_pack.resolution_reason,
                handoff_recommended=True,
                handoff_reason="Authoritative sources contain conflicting policy guidance requiring human confirmation.",
            )

        # -------------------------------------------------------------------
        # Rule 3: Explicit Order Operational Exception
        # -------------------------------------------------------------------
        if safe_order and safe_order.requires_human_handoff:
            return AgentDecision(
                state=DecisionState.HANDOFF,
                reason=safe_order.handoff_reason or "Order has an exception requiring human support review.",
                handoff_recommended=True,
                handoff_reason=safe_order.handoff_reason,
                supported_action="order_lookup",
            )

        # -------------------------------------------------------------------
        # Rule 4: Missing Order ID on Order Request
        # -------------------------------------------------------------------
        if route == RouteType.ORDER and not state.active_order_id:
            return AgentDecision(
                state=DecisionState.CLARIFY,
                reason="Order-related inquiry requires an order ID for lookup.",
                suggested_clarification="Please provide your order ID (e.g., ORD-XXXX) so I can look up your order details.",
                handoff_recommended=False,
                supported_action=None,
            )

        # -------------------------------------------------------------------
        # Rule 5: Unknown Order ID (Supplied but not found)
        # -------------------------------------------------------------------
        if route == RouteType.ORDER and state.active_order_id and safe_order is None:
            return AgentDecision(
                state=DecisionState.HANDOFF,
                reason=f"Order {state.active_order_id} was not found in our records.",
                suggested_clarification="Please verify your order ID or contact customer support for further assistance.",
                handoff_recommended=True,
                handoff_reason=f"Order ID {state.active_order_id} could not be located in the operational system.",
                supported_action="order_lookup",
            )

        # -------------------------------------------------------------------
        # Rule 6: Valid Customer-Safe Order Lookup
        # -------------------------------------------------------------------
        if route == RouteType.ORDER and safe_order is not None:
            return AgentDecision(
                state=DecisionState.ANSWER,
                reason=f"Order {safe_order.order_id} retrieved successfully with authoritative status '{safe_order.status}'.",
                handoff_recommended=False,
                supported_action="order_lookup",
            )

        # -------------------------------------------------------------------
        # Rule 7: Insufficient Knowledge Evidence
        # -------------------------------------------------------------------
        if evidence_pack and not evidence_pack.evidence_sufficient:
            return AgentDecision(
                state=DecisionState.ABSTAIN,
                reason=evidence_pack.resolution_reason or "Insufficient customer-facing evidence in knowledge base.",
                handoff_recommended=True,
                handoff_reason="Knowledge base lacks sufficient information to answer the question reliably.",
            )

        # -------------------------------------------------------------------
        # Rule 8: Sufficient Approved Knowledge Evidence
        # -------------------------------------------------------------------
        if evidence_pack and evidence_pack.evidence_sufficient:
            return AgentDecision(
                state=DecisionState.ANSWER,
                reason="Sufficient authoritative evidence found in knowledge base.",
                handoff_recommended=evidence_pack.handoff_recommended,
                handoff_reason="Human assistance recommended by policy guidance." if evidence_pack.handoff_recommended else None,
            )

        # -------------------------------------------------------------------
        # Rule 9: Unsupported / Fallback
        # -------------------------------------------------------------------
        return AgentDecision(
            state=DecisionState.ABSTAIN,
            reason="Request could not be resolved from available data or policies.",
            handoff_recommended=True,
            handoff_reason="Query is outside the scope of available support capabilities.",
        )
