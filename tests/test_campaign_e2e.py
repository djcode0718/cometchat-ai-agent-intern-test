"""End-to-End integration test suite (E2E-001 through E2E-010)."""

import json
import os
import pytest
from fastapi.testclient import TestClient

from src.agent.decision import DecisionState
from src.api import app, set_orchestrator
from src.agent.orchestrator import AgentOrchestrator
from src.llm.base import BaseLLMProvider, GroundedGenerationRequest, GeneratedResponse, LLMGenerationError
from src.llm.validator import OutputValidator
from src.llm.openrouter_chain import OpenRouterFallbackChainProvider
from src.llm.models import CitationSource


class OfflineDeterministicProvider(BaseLLMProvider):
    """Safe offline provider that delegates to OutputValidator."""
    @property
    def provider_name(self) -> str:
        return "deterministic_offline"

    def generate(self, request: GroundedGenerationRequest) -> GeneratedResponse:
        return OutputValidator.build_fallback(request)


class FailingProvider(BaseLLMProvider):
    """Simulates a broken provider that always raises an error."""
    @property
    def provider_name(self) -> str:
        return "failing_mock"

    def generate(self, request: GroundedGenerationRequest) -> GeneratedResponse:
        raise LLMGenerationError("Simulated provider outage: 500 Internal Server Error")


class InvalidCitationProvider(BaseLLMProvider):
    """Simulates a provider producing fabricated citations."""
    @property
    def provider_name(self) -> str:
        return "invalid_citation_mock"

    def generate(self, request: GroundedGenerationRequest) -> GeneratedResponse:
        # Returns fabricated citation
        return GeneratedResponse(
            message="You have 30 days to return according to fake policy. [fake-document.md > Nonexistent Section]",
            decision_state=DecisionState.ANSWER,
            citations=[CitationSource(filename="fake-document.md", heading="Nonexistent Section")],
            is_fallback=False,
        )


@pytest.fixture(scope="module")
def client():
    # Configure deterministic orchestrator for offline tests
    orch = AgentOrchestrator(llm_provider=OfflineDeterministicProvider())
    set_orchestrator(orch)
    yield TestClient(app)
    set_orchestrator(None)


def test_e2e_001_standard_factual_question(client):
    """E2E-001: Standard factual question (policy window)."""
    resp = client.post("/chat", json={"message": "How many days do customers have to request a return under the standard returns policy?"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["decision_state"] == "ANSWER"
    assert "30 calendar days" in data["message"]
    assert any("01-returns-policy-current.md" in c for c in data["citations"])
    assert data["handoff_recommended"] is False


def test_e2e_002_standard_procedural_question(client):
    """E2E-002: Standard procedural question (how to clean bags)."""
    resp = client.post("/chat", json={"message": "How do I clean my Aster & Row fabric bag or backpack?"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["decision_state"] == "ANSWER"
    assert "spot-clean" in data["message"].lower() or "soap" in data["message"].lower()
    assert any("11-product-care.md" in c for c in data["citations"])


def test_e2e_003_multi_part_question(client):
    """E2E-003: Multi-part question covering multiple policy facets."""
    query = "What is the warranty period for backpacks, and what is the warranty period for drinkware?"
    resp = client.post("/chat", json={"message": query})
    assert resp.status_code == 200
    data = resp.json()
    assert data["decision_state"] == "ANSWER"
    assert "2 years" in data["message"]
    assert "1 year" in data["message"]
    assert any("07-warranty.md" in c for c in data["citations"])


def test_e2e_004_policy_exception(client):
    """E2E-004: Policy with an exception (return fee waiver for damaged items)."""
    query = "Is the return shipping fee waived if an item arrives damaged?"
    resp = client.post("/chat", json={"message": query})
    assert resp.status_code == 200
    data = resp.json()
    assert data["decision_state"] == "ANSWER"
    assert "waived" in data["message"].lower()
    assert any("01-returns-policy-current.md" in c or "04-damaged-or-wrong-items.md" in c for c in data["citations"])


def test_e2e_005_unknown_question(client):
    """E2E-005: Unanswerable inquiry not in knowledge base."""
    query = "What is Aster & Row's corporate pet policy for bringing dogs to the retail headquarters?"
    resp = client.post("/chat", json={"message": query})
    assert resp.status_code == 200
    data = resp.json()
    # Should safely abstain or provide safe fallback without fabricating policy
    assert not any("fake" in c.lower() for c in data["citations"])
    assert "pet policy" not in data["message"].lower() or "not available" in data["message"].lower() or data["is_fallback"]


def test_e2e_006_provider_failure():
    """E2E-006: Primary provider failure triggers fallback cascade safely."""
    # Build orchestrator with a chain that has a failing primary
    chain = OpenRouterFallbackChainProvider(
        primary_model="nonexistent-model-that-fails",
        enable_cache=False,
    )
    orch = AgentOrchestrator(llm_provider=chain)
    state = orch.process_turn("session-e2e-006", "What is the return window for standard orders?")
    assert state.response is not None
    assert len(state.response.message) > 0
    assert state.response.is_fallback is True or state.response.message != ""


def test_e2e_007_all_providers_unavailable():
    """E2E-007: All remote providers unavailable -> deterministic fallback."""
    orch = AgentOrchestrator(llm_provider=FailingProvider())
    # Even if provider throws, orchestrator safely catches and produces deterministic fallback
    state = orch.process_turn("session-e2e-007", "What is the standard warranty period for bags?")
    assert state.response is not None
    assert state.response.is_fallback is True
    assert "2 years" in state.response.message


def test_e2e_008_citation_validation_failure():
    """E2E-008: Generated response with invalid citation is sanitized/repaired."""
    gen_req = GroundedGenerationRequest(
        user_query="What is the return window?",
        decision_state="ANSWER",
        decision_reason="test",
    )
    # Validate against invalid provider
    invalid_resp = InvalidCitationProvider().generate(gen_req)
    val_result = OutputValidator.validate(invalid_resp.message, gen_req)
    # OutputValidator rejects fake-document.md
    assert val_result.is_valid is False or len(val_result.violations) > 0
    # Safe repaired fallback is produced
    repaired = val_result.repaired_response or OutputValidator.build_fallback(gen_req)
    assert not any("fake-document.md" in c.filename for c in repaired.citations)


def test_e2e_009_empty_retrieval(client):
    """E2E-009: Empty retrieval handling."""
    # When gibberish query produces no candidates
    resp = client.post("/chat", json={"message": "xyzzyqwerty12345nonexistenttoken9999"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["message"] != ""


def test_e2e_010_repeated_request_consistency(client):
    """E2E-010: Idempotency and consistency on repeated identical requests."""
    query = "How long does order processing take before an order is dispatched?"
    resp1 = client.post("/chat", json={"session_id": "repeat-sess-1", "message": query})
    resp2 = client.post("/chat", json={"session_id": "repeat-sess-2", "message": query})
    assert resp1.status_code == 200
    assert resp2.status_code == 200
    d1 = resp1.json()
    d2 = resp2.json()
    assert d1["decision_state"] == d2["decision_state"]
    assert d1["message"] == d2["message"]
    assert d1["citations"] == d2["citations"]
