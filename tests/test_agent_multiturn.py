"""Tests for multi-turn conversation tracking and session isolation."""

from src.agent.orchestrator import AgentOrchestrator
from src.agent.state import DecisionState, RouteType


def test_multiturn_order_flow():
    orchestrator = AgentOrchestrator()
    session_id = "test-multiturn-session"

    # Turn 1: Initial order lookup with explicit ID
    state1 = orchestrator.process_turn(session_id, "Where is ORD-1007?")
    assert state1.route == RouteType.ORDER
    assert state1.active_order_id == "ORD-1007"
    assert state1.decision.state == DecisionState.ANSWER
    assert state1.customer_safe_order is not None
    assert state1.customer_safe_order.carrier == "UPS"

    # Turn 2: Follow-up question referencing "it"
    state2 = orchestrator.process_turn(session_id, "When will it arrive?")
    assert state2.route == RouteType.ORDER
    assert state2.active_order_id == "ORD-1007"
    assert state2.decision.state == DecisionState.ANSWER
    assert state2.customer_safe_order.order_id == "ORD-1007"

    # Turn 3: New explicit order ID overriding previous active order
    state3 = orchestrator.process_turn(session_id, "What about ORD-1003?")
    assert state3.route == RouteType.ORDER
    assert state3.active_order_id == "ORD-1003"
    assert state3.decision.state == DecisionState.ANSWER
    assert state3.customer_safe_order.order_id == "ORD-1003"
    assert state3.customer_safe_order.carrier == "USPS"

    # Turn 4: Follow-up cancellation query on new active order
    state4 = orchestrator.process_turn(session_id, "Can I cancel that?")
    assert state4.route == RouteType.ORDER
    assert state4.active_order_id == "ORD-1003"
    assert state4.decision.state == DecisionState.ANSWER
    assert state4.customer_safe_order.is_cancellable is False


def test_session_isolation_no_leakage():
    orchestrator = AgentOrchestrator()

    # Session A accesses ORD-1007
    state_a = orchestrator.process_turn("session-a", "Where is ORD-1007?")
    assert state_a.active_order_id == "ORD-1007"

    # Session B asks about an order without an ID
    state_b = orchestrator.process_turn("session-b", "Where is my order?")
    assert state_b.route == RouteType.ORDER
    assert state_b.active_order_id is None
    assert state_b.customer_safe_order is None
    assert state_b.decision.state == DecisionState.CLARIFY


def test_multiturn_policy_inquiry():
    orchestrator = AgentOrchestrator()
    session_id = "test-policy-session"

    state1 = orchestrator.process_turn(session_id, "Do you ship internationally?")
    assert state1.route == RouteType.KNOWLEDGE
    assert state1.decision.state == DecisionState.ANSWER
    assert state1.evidence_pack is not None

    state2 = orchestrator.process_turn(session_id, "What about Canada, and how long does it take?")
    assert state2.route == RouteType.KNOWLEDGE
    assert state2.decision.state == DecisionState.ANSWER
    assert any("06-international-shipping.md" in c for c in state2.evidence_pack.citation_strings)
