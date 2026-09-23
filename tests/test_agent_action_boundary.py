"""Tests verifying the strict action boundary (no hallucinated mutations)."""

from src.agent.orchestrator import AgentOrchestrator
from src.agent.state import DecisionState


def test_cancellation_query_never_claims_mutation():
    orchestrator = AgentOrchestrator()

    # ORD-1001 is pending and eligible for cancellation request
    state = orchestrator.process_turn("session-action-1", "Can I cancel ORD-1001?")

    assert state.decision.state == DecisionState.ANSWER
    # Supported action must strictly be read-only lookup, never mutation
    assert state.decision.supported_action == "order_lookup"
    assert state.decision.supported_action != "cancel_order"
    assert state.customer_safe_order.is_cancellable is True


def test_refund_query_never_claims_mutation():
    orchestrator = AgentOrchestrator()

    # Customer asking for refund
    state = orchestrator.process_turn("session-action-2", "Please issue a refund for ORD-1008")

    assert state.decision.supported_action in ("order_lookup", None)
    assert state.decision.supported_action != "process_refund"
    assert state.decision.supported_action != "issue_refund"


def test_address_change_query_never_claims_mutation():
    orchestrator = AgentOrchestrator()

    # Customer asking to change shipping address
    state = orchestrator.process_turn("session-action-3", "Change the shipping address for ORD-1001 to California")

    assert state.decision.supported_action in ("order_lookup", None)
    assert state.decision.supported_action != "change_address"
