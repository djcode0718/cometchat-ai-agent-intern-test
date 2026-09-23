"""Unit and integration tests for the FastAPI backend API."""

from unittest.mock import MagicMock
import pytest
from fastapi.testclient import TestClient

from src.agent.orchestrator import AgentOrchestrator
from src.agent.state import AgentDecision, AgentState, DecisionState, RouteType
from src.api import app, set_orchestrator
from src.core.models import CitationSource
from src.llm.models import GeneratedResponse


@pytest.fixture(autouse=True)
def reset_api_orchestrator():
    """Reset orchestrator fixture before and after each test."""
    set_orchestrator(None)
    yield
    set_orchestrator(None)


@pytest.fixture
def client():
    """Create FastAPI TestClient."""
    return TestClient(app)


# 1. Health check endpoint
def test_health_check(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


# 2. Chat with generated session ID
def test_chat_generated_session_id(client):
    mock_orch = MagicMock(spec=AgentOrchestrator)
    set_orchestrator(mock_orch)

    def side_effect(session_id, query):
        return AgentState(
            session_id=session_id,
            turn_id=1,
            raw_query=query,
            normalized_query=query,
            route=RouteType.KNOWLEDGE,
            decision=AgentDecision(state=DecisionState.ANSWER, reason="Standard return window"),
            response=GeneratedResponse(message="Return window is 30 days.", decision_state=DecisionState.ANSWER),
            trace={"session_id": session_id, "turn_id": 1, "query": query},
        )

    mock_orch.process_turn.side_effect = side_effect

    response = client.post("/chat", json={"message": "What is your return policy?"})
    assert response.status_code == 200
    data = response.json()

    assert data["session_id"].startswith("session-")
    assert data["turn_id"] == 1
    assert data["message"] == "Return window is 30 days."
    assert data["decision_state"] == "ANSWER"
    assert data["handoff_recommended"] is False
    assert data["is_fallback"] is False


# 3. Chat with supplied session ID
def test_chat_supplied_session_id(client):
    mock_orch = MagicMock(spec=AgentOrchestrator)
    set_orchestrator(mock_orch)

    mock_orch.process_turn.return_value = AgentState(
        session_id="custom-session-123",
        turn_id=1,
        raw_query="Where is ORD-1001?",
        normalized_query="Where is ORD-1001?",
        route=RouteType.ORDER,
        decision=AgentDecision(state=DecisionState.ANSWER, reason="Order found"),
        response=GeneratedResponse(message="Order is shipped.", decision_state=DecisionState.ANSWER),
        trace={
            "session_id": "custom-session-123",
            "safe_order": {
                "order_id": "ORD-1001",
                "status": "shipped",
                "carrier": "FedEx",
                "tracking_number": "12345",
                "estimated_delivery": "2026-09-01",
                "is_cancellable": False,
            },
        },
    )

    response = client.post(
        "/chat",
        json={"session_id": "custom-session-123", "message": "Where is ORD-1001?"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["session_id"] == "custom-session-123"
    assert data["safe_order"]["order_id"] == "ORD-1001"
    assert data["safe_order"]["status"] == "shipped"
    mock_orch.process_turn.assert_called_once_with("custom-session-123", "Where is ORD-1001?")


# 4. Multi-turn same session conversation
def test_chat_multi_turn_same_session(client):
    mock_orch = MagicMock(spec=AgentOrchestrator)
    set_orchestrator(mock_orch)

    state1 = AgentState(
        session_id="session-multi",
        turn_id=1,
        raw_query="Where is ORD-1007?",
        normalized_query="Where is ORD-1007?",
        route=RouteType.ORDER,
        decision=AgentDecision(state=DecisionState.ANSWER, reason="Order found"),
        response=GeneratedResponse(message="ORD-1007 is shipped.", decision_state=DecisionState.ANSWER),
        trace={"session_id": "session-multi", "turn_id": 1},
    )
    state2 = AgentState(
        session_id="session-multi",
        turn_id=2,
        raw_query="Can I cancel it?",
        normalized_query="Can I cancel it?",
        route=RouteType.ORDER,
        decision=AgentDecision(state=DecisionState.ANSWER, reason="Cancellation check"),
        response=GeneratedResponse(message="It cannot be cancelled.", decision_state=DecisionState.ANSWER),
        trace={"session_id": "session-multi", "turn_id": 2},
    )
    mock_orch.process_turn.side_effect = [state1, state2]

    res1 = client.post("/chat", json={"session_id": "session-multi", "message": "Where is ORD-1007?"})
    assert res1.status_code == 200
    assert res1.json()["turn_id"] == 1

    res2 = client.post("/chat", json={"session_id": "session-multi", "message": "Can I cancel it?"})
    assert res2.status_code == 200
    assert res2.json()["turn_id"] == 2
    assert res2.json()["message"] == "It cannot be cancelled."


# 5. Session reset clears session
def test_session_reset(client):
    mock_orch = MagicMock(spec=AgentOrchestrator)
    mock_session_manager = MagicMock()
    mock_orch.session_manager = mock_session_manager
    set_orchestrator(mock_orch)

    response = client.post("/sessions/test-session-456/reset")
    assert response.status_code == 200
    assert response.json() == {"session_id": "test-session-456", "status": "reset"}
    mock_session_manager.clear_session.assert_called_once_with("test-session-456")


# 6. Session trace retrieval
def test_session_trace_retrieval(client):
    mock_orch = MagicMock(spec=AgentOrchestrator)
    set_orchestrator(mock_orch)

    mock_orch.process_turn.return_value = AgentState(
        session_id="trace-session",
        turn_id=1,
        raw_query="Return window?",
        normalized_query="Return window?",
        route=RouteType.KNOWLEDGE,
        decision=AgentDecision(state=DecisionState.ANSWER, reason="Standard return window"),
        response=GeneratedResponse(message="30 days.", decision_state=DecisionState.ANSWER),
        trace={"session_id": "trace-session", "turn_id": 1, "route": "KNOWLEDGE", "latency_ms": 120},
    )

    # 1. Process turn to populate trace
    client.post("/chat", json={"session_id": "trace-session", "message": "Return window?"})

    # 2. Fetch trace
    trace_res = client.get("/sessions/trace-session/trace")
    assert trace_res.status_code == 200
    trace_data = trace_res.json()
    assert trace_data["session_id"] == "trace-session"
    assert trace_data["trace"]["route"] == "KNOWLEDGE"
    assert trace_data["trace"]["latency_ms"] == 120


# 7. Validation: Empty or whitespace-only message rejected (422)
def test_chat_empty_message_rejected(client):
    res1 = client.post("/chat", json={"message": ""})
    assert res1.status_code == 422

    res2 = client.post("/chat", json={"message": "   "})
    assert res2.status_code == 422


# 8. Validation: Oversized message rejected (422)
def test_chat_oversized_message_rejected(client):
    oversized = "A" * 4001
    res = client.post("/chat", json={"message": oversized})
    assert res.status_code == 422


# 9. Orchestrator exception returns safe 500 without stack trace
def test_orchestrator_error_handling(client):
    mock_orch = MagicMock(spec=AgentOrchestrator)
    mock_orch.process_turn.side_effect = RuntimeError("Fatal internal database explosion with secret key xyz")
    set_orchestrator(mock_orch)

    res = client.post("/chat", json={"message": "Hello"})
    assert res.status_code == 500
    assert res.json() == {"detail": "Unable to safely process the request."}
    assert "secret key" not in res.text
    assert "database explosion" not in res.text


# 10. Domain decisions HANDOFF and CONFLICT return 200 OK
def test_chat_handoff_and_conflict_return_200(client):
    mock_orch = MagicMock(spec=AgentOrchestrator)
    set_orchestrator(mock_orch)

    # Handoff response
    mock_orch.process_turn.return_value = AgentState(
        session_id="handoff-session",
        turn_id=1,
        raw_query="Secret internal fraud score",
        normalized_query="Secret internal fraud score",
        route=RouteType.ORDER,
        decision=AgentDecision(
            state=DecisionState.HANDOFF,
            reason="Confidential customer data requested.",
            handoff_recommended=True,
            handoff_reason="Internal security policy",
        ),
        response=GeneratedResponse(
            message="Internal notes are confidential.",
            decision_state=DecisionState.HANDOFF,
            handoff_recommended=True,
            handoff_reason="Internal security policy",
        ),
        handoff_recommended=True,
        handoff_reason="Internal security policy",
        trace={},
    )

    res_handoff = client.post("/chat", json={"message": "Secret internal fraud score"})
    assert res_handoff.status_code == 200
    assert res_handoff.json()["decision_state"] == "HANDOFF"
    assert res_handoff.json()["handoff_recommended"] is True
    assert res_handoff.json()["handoff_reason"] == "Internal security policy"

    # Conflict response
    mock_orch.process_turn.return_value = AgentState(
        session_id="conflict-session",
        turn_id=1,
        raw_query="Dishwasher breeze tumbler",
        normalized_query="Dishwasher breeze tumbler",
        route=RouteType.KNOWLEDGE,
        decision=AgentDecision(
            state=DecisionState.CONFLICT,
            reason="Contradictory product care instructions.",
            handoff_recommended=True,
            handoff_reason="Conflicting official policies",
        ),
        response=GeneratedResponse(
            message="Conflicting instructions exist for cleaning Breeze Tumbler.",
            decision_state=DecisionState.CONFLICT,
            citations=[
                CitationSource(filename="11-product-care.md", heading="Breeze Tumbler"),
                CitationSource(filename="12-breeze-tumbler-product-card.md", heading="Cleaning"),
            ],
            handoff_recommended=True,
            handoff_reason="Conflicting official policies",
        ),
        handoff_recommended=True,
        handoff_reason="Conflicting official policies",
        trace={},
    )

    res_conflict = client.post("/chat", json={"message": "Dishwasher breeze tumbler"})
    assert res_conflict.status_code == 200
    assert res_conflict.json()["decision_state"] == "CONFLICT"
    assert res_conflict.json()["citations"] == [
        "[11-product-care.md > Breeze Tumbler]",
        "[12-breeze-tumbler-product-card.md > Cleaning]",
    ]


# 11. Fallback response serialization
def test_chat_fallback_serialization(client):
    mock_orch = MagicMock(spec=AgentOrchestrator)
    set_orchestrator(mock_orch)

    mock_orch.process_turn.return_value = AgentState(
        session_id="fallback-session",
        turn_id=1,
        raw_query="Can I return my item?",
        normalized_query="Can I return my item?",
        route=RouteType.KNOWLEDGE,
        decision=AgentDecision(state=DecisionState.ANSWER, reason="Standard return"),
        response=GeneratedResponse(
            message="Standard return window is 30 days.",
            decision_state=DecisionState.ANSWER,
            is_fallback=True,
            fallback_reason="Gemini timeout",
        ),
        trace={},
    )

    res = client.post("/chat", json={"message": "Can I return my item?"})
    assert res.status_code == 200
    data = res.json()
    assert data["is_fallback"] is True
    assert data["fallback_reason"] == "Gemini timeout"


# 12. Response contains only public fields (strict schema verification)
def test_response_contains_only_public_fields(client):
    mock_orch = MagicMock(spec=AgentOrchestrator)
    set_orchestrator(mock_orch)

    mock_orch.process_turn.return_value = AgentState(
        session_id="public-only",
        turn_id=1,
        raw_query="Hello",
        normalized_query="Hello",
        route=RouteType.KNOWLEDGE,
        decision=AgentDecision(state=DecisionState.ANSWER, reason="Greeting"),
        response=GeneratedResponse(message="How can I help you?", decision_state=DecisionState.ANSWER),
        trace={"internal_secret": "do_not_expose"},
    )

    res = client.post("/chat", json={"message": "Hello"})
    assert res.status_code == 200
    data = res.json()
    allowed_keys = {
        "session_id",
        "turn_id",
        "message",
        "decision_state",
        "citations",
        "handoff_recommended",
        "handoff_reason",
        "supported_action",
        "is_fallback",
        "fallback_reason",
        "safe_order",
    }
    assert set(data.keys()).issubset(allowed_keys)
    assert "internal_secret" not in data


# 13. CORS headers are returned for allowed origins
def test_cors_headers(client):
    response = client.options(
        "/chat",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "Content-Type",
        },
    )
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "http://localhost:5173"
