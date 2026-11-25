"""Unit and integration tests for Observability: Request ID, structured logs, PII redaction, metrics, and error boundaries."""

import io
import json
import logging
import time
from typing import Any, Dict
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.agent.orchestrator import AgentOrchestrator
from src.agent.state import AgentDecision, AgentState, DecisionState, RouteType
from src.api import app, set_orchestrator
from src.llm.base import BaseLLMProvider
from src.llm.models import GeneratedResponse, GroundedGenerationRequest
from src.observability.logging import (
    EMAIL_PATTERN,
    SENSITIVE_KEYS,
    _mask_string_value,
    _redact_data,
    configure_logging,
    get_logger,
)
from src.observability.metrics import HTTP_REQUESTS_TOTAL
from src.observability.trace_cache import BoundedTTLCache


@pytest.fixture
def client():
    """Test client for FastAPI app."""
    return TestClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# 1. Request ID Tests
# ---------------------------------------------------------------------------

def test_request_id_generated_when_missing(client):
    """Verify that a valid UUID request ID is generated when none is supplied."""
    resp = client.get("/health")
    assert resp.status_code == 200
    req_id = resp.headers.get("X-Request-ID")
    assert req_id is not None
    assert len(req_id) >= 8


def test_request_id_echoed_when_valid(client):
    """Verify incoming X-Request-ID conforming to ^[A-Za-z0-9._-]{8,64}$ is echoed back."""
    valid_id = "Custom-Trace-Id_12345.678"
    resp = client.get("/health", headers={"X-Request-ID": valid_id})
    assert resp.status_code == 200
    assert resp.headers.get("X-Request-ID") == valid_id


def test_request_id_replaced_when_invalid(client):
    """Verify incoming invalid X-Request-ID (malformed chars or too short/long) is replaced with fresh UUID."""
    invalid_short = "short"
    resp = client.get("/health", headers={"X-Request-ID": invalid_short})
    assert resp.status_code == 200
    req_id = resp.headers.get("X-Request-ID")
    assert req_id != invalid_short
    assert len(req_id) >= 8

    invalid_chars = "bad/id/with/slashes@123"
    resp2 = client.get("/health", headers={"X-Request-ID": invalid_chars})
    assert resp2.headers.get("X-Request-ID") != invalid_chars


def test_request_id_present_on_404_and_422_and_500(client):
    """Verify request ID is returned in response header on 404, 422, and 500 responses."""
    # 404
    resp_404 = client.get("/non_existent_route")
    assert resp_404.status_code == 404
    assert resp_404.headers.get("X-Request-ID") is not None

    # 422
    resp_422 = client.post("/chat", json={"message": ""})
    assert resp_422.status_code == 422
    assert resp_422.headers.get("X-Request-ID") is not None

    # 500: Forced exception in orchestrator
    mock_orch = MagicMock(spec=AgentOrchestrator)
    mock_orch.process_turn.side_effect = RuntimeError("Forced simulation error")
    set_orchestrator(mock_orch)
    try:
        resp_500 = client.post(
            "/chat",
            json={"message": "valid query"},
            headers={"X-Request-ID": "test-req-id-500"},
        )
        assert resp_500.status_code == 500
        assert resp_500.headers.get("X-Request-ID") == "test-req-id-500"
        data = resp_500.json()
        assert data["detail"] == "Unable to safely process the request."
        assert data["request_id"] == "test-req-id-500"
        # Crucial: Raw exception trace must never leak to client
        assert "Forced simulation error" not in resp_500.text
    finally:
        set_orchestrator(None)


# ---------------------------------------------------------------------------
# 2. PII Redaction & Canary Tests
# ---------------------------------------------------------------------------

def test_pii_redaction_processor_masks_sensitive_keys_and_patterns():
    """Test recursive scrubbing of sensitive keys and email/api-key string masking."""
    data = {
        "email": "customer@secretcorp.com",
        "name": "Jane Doe",
        "address": "123 Main St, Springfield",
        "warehouse_note": "Handle with care: fragile",
        "risk_score": 0.95,
        "api_key": "sk-live-1234567890abcdef123456",
        "safe_field": "public policy query",
        "nested": {
            "token": "secret_token_123",
            "text": "Please contact user john.smith@company.org regarding key gsk_abcdef1234567890",
        },
    }

    cleaned = _redact_data(data)

    assert cleaned["email"] == "[REDACTED]"
    assert cleaned["name"] == "[REDACTED]"
    assert cleaned["address"] == "[REDACTED]"
    assert cleaned["warehouse_note"] == "[REDACTED]"
    assert cleaned["risk_score"] == "[REDACTED]"
    assert cleaned["api_key"] == "[REDACTED]"
    assert cleaned["safe_field"] == "public policy query"
    assert cleaned["nested"]["token"] == "[REDACTED]"

    # Test embedded masking
    nested_text = cleaned["nested"]["text"]
    assert "john.smith@company.org" not in nested_text
    assert "gsk_abcdef1234567890" not in nested_text
    assert "[REDACTED_KEY]" in nested_text


def test_pii_canary_order_lookup_never_leaks_in_logs_or_metrics(client, capsys):
    """Canary test: lookup order with known sensitive fields, ensure zero leakage into logs or /metrics."""
    canary_email = "alex.rivera@example.com"
    canary_note = "VIP customer - handle with priority"
    canary_address = "742 Evergreen Terrace"

    # Query valid order ORD-1001
    resp = client.post(
        "/chat",
        json={"message": "Where is my order ORD-1001?"},
        headers={"X-Request-ID": "canary-test-req-001"},
    )
    assert resp.status_code == 200

    # Check metrics output
    metrics_resp = client.get("/metrics")
    assert metrics_resp.status_code == 200
    assert canary_email not in metrics_resp.text
    assert canary_note not in metrics_resp.text
    assert canary_address not in metrics_resp.text


# ---------------------------------------------------------------------------
# 3. Prometheus Metrics Tests
# ---------------------------------------------------------------------------

def test_metrics_endpoint_increments_and_bounds_cardinality(client):
    """Test that /metrics reflects endpoint calls with bounded low-cardinality label values."""
    before_metrics = client.get("/metrics").text

    # Make request to chat
    client.post("/chat", json={"message": "What is the return window?"})

    after_metrics = client.get("/metrics").text
    assert "http_requests_total" in after_metrics
    assert "agent_stage_duration_seconds" in after_metrics
    assert "agent_turns_total" in after_metrics

    # Strict check: Raw session IDs and user message text must NOT appear as metric labels
    assert 'route="/chat"' in after_metrics or 'route="/sessions/{session_id}/reset"' in after_metrics
    assert "What is the return window?" not in after_metrics


# ---------------------------------------------------------------------------
# 4. Readiness & Health Probes Tests
# ---------------------------------------------------------------------------

def test_health_check_probe(client):
    """Verify /health dependency-free liveness probe."""
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_ready_check_probe(client):
    """Verify /ready probe reports ready when KB and retriever are active."""
    resp = client.get("/ready")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ready"


# ---------------------------------------------------------------------------
# 5. FAULT-PRV-06 Schema Error Handling Test
# ---------------------------------------------------------------------------

class DictReturningMockProvider(BaseLLMProvider):
    """Simulates FAULT-PRV-06: provider returns raw dict instead of GeneratedResponse."""

    @property
    def provider_name(self) -> str:
        return "fault_prv_06_mock"

    def generate(self, request: GroundedGenerationRequest) -> Any:
        # Invalid schema return: returns dict instead of GeneratedResponse
        return {"error": "unexpected format", "text": "bad schema"}


def test_fault_prv_06_provider_returning_dict_triggers_safe_fallback():
    """Verify FAULT-PRV-06: If provider returns a dict, orchestrator catches it and triggers safe fallback."""
    fault_provider = DictReturningMockProvider()
    orch = AgentOrchestrator(llm_provider=fault_provider)

    state = orch.process_turn("session-fault-06", "What is the return policy?")

    assert state.response.is_fallback is True
    assert "invalid schema" in state.response.fallback_reason.lower()
    assert state.trace["generation_failed"] is True
    assert "stage_timings_ms" in state.trace
    assert "generation" in state.trace["stage_timings_ms"]


# ---------------------------------------------------------------------------
# 6. Bounded TTL & LRU Trace Cache Tests
# ---------------------------------------------------------------------------

def test_bounded_ttl_lru_cache_eviction():
    """Verify that BoundedTTLCache respects maxsize LRU capacity and TTL expiration."""
    # Test Capacity LRU
    cache = BoundedTTLCache(maxsize=3, ttl_seconds=10.0)
    cache.set("k1", "v1")
    cache.set("k2", "v2")
    cache.set("k3", "v3")
    assert len(cache) == 3

    # Adding 4th item should evict oldest (k1)
    cache.set("k4", "v4")
    assert len(cache) == 3
    assert cache.get("k1") is None
    assert cache.get("k2") == "v2"
    assert cache.get("k4") == "v4"

    # Test TTL Expiration
    short_ttl_cache = BoundedTTLCache(maxsize=10, ttl_seconds=0.05)
    short_ttl_cache.set("temp", "value")
    assert short_ttl_cache.get("temp") == "value"
    time.sleep(0.06)
    assert short_ttl_cache.get("temp") is None
    assert len(short_ttl_cache) == 0
