"""API reliability, request validation fuzzing, dependency failures, and concurrency tests."""

import pytest
import concurrent.futures
from fastapi.testclient import TestClient

from src.api import app, set_orchestrator
from src.agent.orchestrator import AgentOrchestrator
from src.llm.base import BaseLLMProvider, GroundedGenerationRequest, GeneratedResponse
from src.llm.validator import OutputValidator


class OfflineProvider(BaseLLMProvider):
    @property
    def provider_name(self) -> str:
        return "offline"

    def generate(self, request: GroundedGenerationRequest) -> GeneratedResponse:
        return OutputValidator.build_fallback(request)


@pytest.fixture(scope="module")
def client():
    orch = AgentOrchestrator(llm_provider=OfflineProvider())
    set_orchestrator(orch)
    yield TestClient(app)
    set_orchestrator(None)


# =============================================================================
# 1. Request Validation Tests
# =============================================================================

def test_api_val_missing_message(client):
    """Missing required 'message' field triggers HTTP 422."""
    resp = client.post("/chat", json={"session_id": "sess-val-1"})
    assert resp.status_code == 422


def test_api_val_empty_message(client):
    """Empty string 'message' triggers HTTP 422 validation error."""
    resp = client.post("/chat", json={"message": ""})
    assert resp.status_code == 422


def test_api_val_whitespace_message(client):
    """Whitespace-only 'message' triggers HTTP 422 validation error."""
    resp = client.post("/chat", json={"message": "    "})
    assert resp.status_code == 422


def test_api_val_null_message(client):
    """Null 'message' triggers HTTP 422."""
    resp = client.post("/chat", json={"message": None})
    assert resp.status_code == 422


def test_api_val_wrong_data_type(client):
    """Wrong data type for message (integer/array) triggers HTTP 422."""
    resp = client.post("/chat", json={"message": 12345})
    assert resp.status_code == 422


def test_api_val_excessively_long_message(client):
    """Message exceeding max_length=4000 triggers HTTP 422."""
    huge_message = "A" * 4005
    resp = client.post("/chat", json={"message": huge_message})
    assert resp.status_code == 422


def test_api_val_invalid_json(client):
    """Malformed JSON string body triggers HTTP 422."""
    resp = client.post(
        "/chat",
        content="not a valid json {",
        headers={"Content-Type": "application/json"},
    )
    assert resp.status_code == 422


def test_api_val_unexpected_fields_ignored(client):
    """Unexpected fields in payload are safely tolerated or ignored without 500."""
    resp = client.post(
        "/chat",
        json={"message": "What is the return policy?", "unexpected_field_123": True},
    )
    assert resp.status_code == 200


def test_api_val_invalid_content_type(client):
    """Unsupported content type (e.g. text/plain) triggers HTTP 422."""
    resp = client.post("/chat", content="hello", headers={"Content-Type": "text/plain"})
    assert resp.status_code == 422


# =============================================================================
# 2. Concurrency & State Isolation Tests
# =============================================================================

def test_api_concurrent_requests_isolation(client):
    """Test 10 concurrent requests to ensure no shared mutable state cross-contamination."""
    queries = [
        ("sess-conc-1", "What is the return window for standard orders?"),
        ("sess-conc-2", "How long is the backpack warranty?"),
        ("sess-conc-3", "How long is drinkware covered under warranty?"),
        ("sess-conc-4", "What is the delivery estimate for Canada?"),
        ("sess-conc-5", "What is the shipping threshold for free domestic shipping?"),
        ("sess-conc-6", "How do I wash Aster & Row packing cubes?"),
        ("sess-conc-7", "Can I return a final sale item?"),
        ("sess-conc-8", "Do Aster & Row gift cards expire?"),
        ("sess-conc-9", "How do I clean my fabric backpack?"),
        ("sess-conc-10", "What proof is required for a warranty claim?"),
    ]

    def send_query(item):
        sid, q = item
        r = client.post("/chat", json={"session_id": sid, "message": q})
        return sid, q, r.status_code, r.json()

    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        results = list(executor.map(send_query, queries))

    for sid, q, status, data in results:
        assert status == 200
        assert data["session_id"] == sid
        assert data["message"] != ""
        assert data["decision_state"] == "ANSWER"


# =============================================================================
# 3. Session Reset and Audit Trace Endpoints
# =============================================================================

def test_api_session_reset_and_trace(client):
    """Test session lifecycle endpoints: /sessions/{id}/trace and /sessions/{id}/reset."""
    sid = "sess-lifecycle-test"
    # 1. Turn
    r1 = client.post("/chat", json={"session_id": sid, "message": "What is the return window?"})
    assert r1.status_code == 200

    # 2. Trace
    r_trace = client.get(f"/sessions/{sid}/trace")
    assert r_trace.status_code == 200
    trace_data = r_trace.json()
    assert trace_data["session_id"] == sid
    assert trace_data["trace"] is not None

    # 3. Reset
    r_reset = client.post(f"/sessions/{sid}/reset")
    assert r_reset.status_code == 200
    assert r_reset.json()["status"] == "reset"

    # 4. Trace after reset is cleared
    r_trace_after = client.get(f"/sessions/{sid}/trace")
    assert r_trace_after.status_code == 200
    assert r_trace_after.json()["trace"] is None
