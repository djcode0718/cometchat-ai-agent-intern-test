"""Tests for LLM provider abstraction and MockLLMProvider."""

from src.agent.state import DecisionState
from src.core.models import CitationSource, DocumentMetadata, KnowledgeChunk
from src.knowledge.evidence import ApprovedEvidence
from src.llm.mock import MockLLMProvider
from src.llm.models import GroundedGenerationRequest
from src.tools.order_models import CustomerSafeOrder, CustomerSafeOrderItem


def make_sample_request(
    decision_state: DecisionState = DecisionState.ANSWER,
    query: str = "How long do I have to return an item?",
) -> GroundedGenerationRequest:
    meta = DocumentMetadata(
        document_id="RET-2026-01",
        title="Returns Policy",
        status="active",
        effective_date="2026-04-01",
        audience="customer",
        policy_authority="official",
    )
    chunk = KnowledgeChunk(
        chunk_id="RET-2026-01::window",
        document_id="RET-2026-01",
        filename="01-returns-policy-current.md",
        heading="Standard return window",
        content="Standard return window is 30 calendar days from delivery.",
        metadata=meta,
    )
    appr = ApprovedEvidence(chunk=chunk, retrieval_score=1.0, retrieval_rank=1, retrieval_strategy="hybrid")

    return GroundedGenerationRequest(
        user_query=query,
        decision_state=decision_state,
        decision_reason="Sufficient approved evidence found.",
        approved_evidence=[appr],
        citations=[CitationSource(filename="01-returns-policy-current.md", heading="Standard return window")],
    )


def test_mock_provider_answer_generation():
    provider = MockLLMProvider()
    req = make_sample_request(DecisionState.ANSWER)
    resp = provider.generate(req)

    assert resp.decision_state == DecisionState.ANSWER
    assert "30 calendar days" in resp.message
    assert len(resp.citations) == 1
    assert resp.citations[0].filename == "01-returns-policy-current.md"
    assert resp.is_fallback is False


def test_mock_provider_clarify_generation():
    provider = MockLLMProvider()
    req = GroundedGenerationRequest(
        user_query="Where is my order?",
        decision_state=DecisionState.CLARIFY,
        decision_reason="Order ID missing.",
        suggested_clarification="Please provide your order ID (e.g., ORD-XXXX).",
    )
    resp = provider.generate(req)

    assert resp.decision_state == DecisionState.CLARIFY
    assert "order id" in resp.message.lower()
    assert resp.handoff_recommended is False


def test_mock_provider_conflict_generation():
    provider = MockLLMProvider()
    req = GroundedGenerationRequest(
        user_query="Can I wash Breeze Tumbler in dishwasher?",
        decision_state=DecisionState.CONFLICT,
        decision_reason="Official sources conflict.",
        citations=[
            CitationSource(filename="11-product-care.md", heading="Breeze Tumbler"),
            CitationSource(filename="12-breeze-tumbler-product-card.md", heading="Cleaning"),
        ],
        handoff_recommended=True,
    )
    resp = provider.generate(req)

    assert resp.decision_state == DecisionState.CONFLICT
    assert resp.handoff_recommended is True
    assert "11-product-care.md" in resp.message
    assert "12-breeze-tumbler-product-card.md" in resp.message


def test_mock_provider_custom_response_injection():
    provider = MockLLMProvider(
        custom_responses={"Custom query": "This is an injected mock response [01-returns-policy-current.md > Standard return window]."}
    )
    req = make_sample_request(DecisionState.ANSWER, query="Custom query")
    resp = provider.generate(req)

    assert "injected mock response" in resp.message


def test_flexible_provider_missing_api_key_raises_error():
    """Verify FlexibleLLMProvider raises LLMGenerationError when no API key is set (no silent mock fallback)."""
    import pytest
    from src.llm.base import LLMGenerationError
    from src.llm.provider import FlexibleLLMProvider

    provider = FlexibleLLMProvider(api_key="")
    req = make_sample_request(DecisionState.ANSWER)

    with pytest.raises(LLMGenerationError) as exc_info:
        provider.generate(req)

    assert "No API key configured" in str(exc_info.value)


def test_flexible_provider_api_failure_raises_error(monkeypatch):
    """Verify FlexibleLLMProvider raises LLMGenerationError on network/API failure without silent mock."""
    import pytest
    from src.llm.base import LLMGenerationError
    from src.llm.provider import FlexibleLLMProvider

    provider = FlexibleLLMProvider(api_key="sk-test-key", base_url="http://invalid-url-for-testing.internal")
    req = make_sample_request(DecisionState.ANSWER)

    with pytest.raises(LLMGenerationError) as exc_info:
        provider.generate(req)

    assert "LLM API generation failed" in str(exc_info.value)


def test_orchestrator_handles_provider_failure_with_safe_fallback_and_trace():
    """Verify AgentOrchestrator catches provider error, triggers safe fallback, and logs generation_failed trace."""
    from src.agent.orchestrator import AgentOrchestrator
    from src.llm.base import BaseLLMProvider, LLMGenerationError

    class FailingProvider(BaseLLMProvider):
        @property
        def provider_name(self) -> str:
            return "failing-cloud-llm"

        def generate(self, request):
            raise LLMGenerationError("Simulated provider outage / timeout.")

    orchestrator = AgentOrchestrator(llm_provider=FailingProvider())
    state = orchestrator.process_turn("session_fail_1", "What is your standard return policy?")

    assert state.response is not None
    assert state.response.is_fallback is True
    assert "Provider generation failed: LLMGenerationError" in state.response.fallback_reason
    assert state.trace["generation_failed"] is True
    assert state.trace["provider"] == "failing-cloud-llm"
    assert state.trace["is_fallback"] is True
    assert len(state.response.message.strip()) > 0
