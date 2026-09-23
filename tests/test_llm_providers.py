"""Unit and integration tests for Groq two-model fallback chain and safe LLM providers."""

import json
from unittest.mock import MagicMock, patch
import pytest

from src.core.models import CitationSource, DecisionState, DocumentMetadata, KnowledgeChunk
from src.llm.base import LLMGenerationError
from src.llm.fallback import FallbackChainLLMProvider
from src.llm.factory import get_llm_provider
from src.llm.gemini import GeminiLLMProvider
from src.llm.grok import GrokLLMProvider
from src.llm.mock import MockLLMProvider
from src.llm.models import GroundedGenerationRequest
from src.knowledge.evidence import ApprovedEvidence
from src.tools.order_models import CustomerSafeOrder, CustomerSafeOrderItem


@pytest.fixture
def sample_knowledge_request():
    """Create a sample generation request for return policy."""
    meta = DocumentMetadata(
        document_id="RET-2026-01",
        title="Standard Return Policy",
        status="active",
        effective_date="2026-01-01",
        audience="customer",
        policy_authority="official",
        customer_answering=True,
    )
    chunk = KnowledgeChunk(
        chunk_id="01-returns-policy-current-chunk-1",
        document_id="01-returns-policy-current.md",
        filename="01-returns-policy-current.md",
        heading="Standard Returns",
        content="Standard returns are accepted within 30 days of delivery in original condition.",
        metadata=meta,
    )
    doc = ApprovedEvidence(
        chunk=chunk,
        retrieval_score=0.95,
        retrieval_rank=1,
        retrieval_strategy="hybrid",
    )
    return GroundedGenerationRequest(
        user_query="How long do I have to return an item?",
        decision_state=DecisionState.ANSWER,
        decision_reason="Standard return policy query with authoritative active evidence.",
        approved_evidence=[doc],
        citations=[CitationSource(filename="01-returns-policy-current.md", heading="Standard Returns")],
    )


@pytest.fixture
def sample_order_request():
    """Create a sample generation request for an order lookup."""
    safe_order = CustomerSafeOrder(
        order_id="ORD-1001",
        membership_tier="standard",
        items=[CustomerSafeOrderItem(name="Apex Daypack", quantity=1, final_sale=False)],
        placed_at="2026-08-10T10:00:00Z",
        status="shipped",
        status_updated_at="2026-08-11T10:00:00Z",
        carrier="FedEx",
        tracking_number="TRK-987654",
        estimated_delivery="August 15, 2026",
        is_cancellable=False,
    )
    return GroundedGenerationRequest(
        user_query="Where is my order ORD-1001?",
        decision_state=DecisionState.ANSWER,
        decision_reason="Found active order ORD-1001",
        customer_safe_order=safe_order,
        supported_action="order_lookup",
    )


# 1. Test Primary Groq Success
def test_groq_primary_provider_success(sample_knowledge_request):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "choices": [
            {
                "message": {
                    "content": "Aster & Row standard return window is 30 days. [01-returns-policy-current.md > Standard Returns]"
                }
            }
        ]
    }

    with patch("httpx.Client.post", return_value=mock_resp):
        provider = GrokLLMProvider(api_key="test-groq-key", model_name="openai/gpt-oss-120b")
        resp = provider.generate(sample_knowledge_request)

        assert not resp.is_fallback
        assert "30 days" in resp.message
        assert len(resp.citations) == 1
        assert resp.citations[0].filename == "01-returns-policy-current.md"
        assert provider.last_latency_ms is not None
        assert provider.provider_name == "groq-openai/gpt-oss-120b"


# 2. Test Fallback Groq Success
def test_groq_fallback_provider_success(sample_knowledge_request):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "choices": [
            {
                "message": {
                    "content": "Aster & Row standard return window is 30 days. [01-returns-policy-current.md > Standard Returns]"
                }
            }
        ]
    }

    with patch("httpx.Client.post", return_value=mock_resp):
        provider = GrokLLMProvider(api_key="test-groq-key", model_name="openai/gpt-oss-20b")
        resp = provider.generate(sample_knowledge_request)

        assert not resp.is_fallback
        assert "30 days" in resp.message
        assert len(resp.citations) == 1
        assert resp.citations[0].filename == "01-returns-policy-current.md"
        assert provider.last_latency_ms is not None
        assert provider.provider_name == "groq-openai/gpt-oss-20b"


# 3. Test Groq Primary Failure -> Groq Fallback Success
def test_fallback_chain_primary_fails_groq_fallback_succeeds(sample_knowledge_request):
    primary_fail_resp = MagicMock()
    primary_fail_resp.status_code = 500

    fallback_success_resp = MagicMock()
    fallback_success_resp.status_code = 200
    fallback_success_resp.json.return_value = {
        "choices": [
            {
                "message": {
                    "content": "Items can be returned within 30 days. [01-returns-policy-current.md > Standard Returns]"
                }
            }
        ]
    }

    call_count = 0

    def mock_post(url, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return primary_fail_resp
        return fallback_success_resp

    with patch("httpx.Client.post", side_effect=mock_post):
        primary_groq = GrokLLMProvider(api_key="test-key", model_name="openai/gpt-oss-120b")
        fallback_groq = GrokLLMProvider(api_key="test-key", model_name="openai/gpt-oss-20b")
        chain = FallbackChainLLMProvider(primary_provider=primary_groq, fallback_provider=fallback_groq)

        resp = chain.generate(sample_knowledge_request)

        assert not resp.is_fallback
        assert "30 days" in resp.message
        assert chain.last_telemetry["primary_success"] is False
        assert chain.last_telemetry["fallback_used"] is True
        assert chain.last_telemetry["fallback_success"] is True
        assert chain.last_telemetry["final_provider"] == "groq-openai/gpt-oss-20b"


# 4. Test Groq Primary Failure -> Groq Fallback Failure -> Safe Deterministic Fallback
def test_fallback_chain_both_fail_triggers_safe_fallback(sample_knowledge_request):
    err_resp = MagicMock()
    err_resp.status_code = 500

    with patch("httpx.Client.post", return_value=err_resp):
        primary_groq = GrokLLMProvider(api_key="test-key", model_name="openai/gpt-oss-120b")
        fallback_groq = GrokLLMProvider(api_key="test-key", model_name="openai/gpt-oss-20b")
        chain = FallbackChainLLMProvider(
            primary_provider=primary_groq,
            fallback_provider=fallback_groq,
            deterministic_fallback_on_error=True,
        )

        resp = chain.generate(sample_knowledge_request)

        assert resp.is_fallback is True
        assert chain.last_telemetry["primary_success"] is False
        assert chain.last_telemetry["fallback_used"] is True
        assert chain.last_telemetry["fallback_success"] is False
        assert chain.last_telemetry["final_provider"] == "deterministic_fallback"


# 5. Missing Grok Key Error
def test_grok_missing_key_raises(sample_knowledge_request):
    provider = GrokLLMProvider(api_key="")
    with pytest.raises(LLMGenerationError) as exc_info:
        provider.generate(sample_knowledge_request)
    assert "API key is not configured" in str(exc_info.value)


# 6. Both Keys Missing in Fallback Chain
def test_chain_both_keys_missing_triggers_error_or_fallback(sample_knowledge_request):
    primary_groq = GrokLLMProvider(api_key="")
    fallback_groq = GrokLLMProvider(api_key="")
    chain = FallbackChainLLMProvider(primary_provider=primary_groq, fallback_provider=fallback_groq)

    with pytest.raises(LLMGenerationError) as exc_info:
        chain.generate(sample_knowledge_request)
    assert "Primary provider failed" in str(exc_info.value)
    assert chain.last_telemetry["fallback_used"] is True
    assert chain.last_telemetry["final_provider"] == "deterministic_fallback"


# 7. Rate limit handling (429)
def test_groq_rate_limit_handled(sample_knowledge_request):
    mock_resp = MagicMock()
    mock_resp.status_code = 429

    with patch("httpx.Client.post", return_value=mock_resp):
        provider = GrokLLMProvider(api_key="test-key", model_name="openai/gpt-oss-120b")
        with pytest.raises(LLMGenerationError) as exc_info:
            provider.generate(sample_knowledge_request)
        assert "rate limit" in str(exc_info.value).lower()


# 8. Output validation: Empty/Whitespace Response from Provider
def test_provider_empty_response_triggers_validation_fallback(sample_knowledge_request):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "choices": [{"message": {"content": "   "}}]
    }

    with patch("httpx.Client.post", return_value=mock_resp):
        provider = GrokLLMProvider(api_key="test-key", model_name="openai/gpt-oss-120b")
        resp = provider.generate(sample_knowledge_request)

        assert resp.is_fallback is True
        assert "empty or whitespace" in (resp.fallback_reason or "").lower()


# 9. Output validation: Mutation claims rejected
def test_provider_mutation_claim_rejected(sample_knowledge_request):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "choices": [{"message": {"content": "I have cancelled your order and issued your refund."}}]
    }

    with patch("httpx.Client.post", return_value=mock_resp):
        provider = GrokLLMProvider(api_key="test-key", model_name="openai/gpt-oss-120b")
        resp = provider.generate(sample_knowledge_request)

        assert resp.is_fallback is True
        assert "validation failed" in (resp.fallback_reason or "").lower()


# 10. Decision state preservation: CONFLICT
def test_conflict_decision_preserved_with_provider():
    req = GroundedGenerationRequest(
        user_query="Can I wash my Breeze Tumbler in the dishwasher?",
        decision_state=DecisionState.CONFLICT,
        decision_reason="Genuine active conflict between product care and product card.",
        citations=[
            CitationSource(filename="11-product-care.md", heading="Breeze Tumbler"),
            CitationSource(filename="12-breeze-tumbler-product-card.md", heading="Cleaning"),
        ],
    )
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "choices": [
            {
                "message": {
                    "content": "Official Aster & Row guides conflict: the Product Care Guide states hand-wash [11-product-care.md > Breeze Tumbler], while the Product Card says dishwasher safe [12-breeze-tumbler-product-card.md > Cleaning]."
                }
            }
        ]
    }

    with patch("httpx.Client.post", return_value=mock_resp):
        provider = GrokLLMProvider(api_key="test-key", model_name="openai/gpt-oss-120b")
        resp = provider.generate(req)

        assert resp.decision_state == DecisionState.CONFLICT
        assert len(resp.citations) == 2


# 11. Decision state preservation: ABSTAIN
def test_abstain_decision_preserved_with_provider():
    req = GroundedGenerationRequest(
        user_query="What fabric is used in the Nomad series?",
        decision_state=DecisionState.ABSTAIN,
        decision_reason="No relevant documentation found for Nomad series.",
    )
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "choices": [
            {
                "message": {
                    "content": "We do not have sufficient information in our official policies to confirm the fabrics for the Nomad series. Please contact support."
                }
            }
        ]
    }

    with patch("httpx.Client.post", return_value=mock_resp):
        provider = GrokLLMProvider(api_key="test-key", model_name="openai/gpt-oss-120b")
        resp = provider.generate(req)

        assert resp.decision_state == DecisionState.ABSTAIN


# 12. Decision state preservation: HANDOFF
def test_handoff_decision_preserved_with_provider():
    req = GroundedGenerationRequest(
        user_query="Give me the internal fraud risk score.",
        decision_state=DecisionState.HANDOFF,
        decision_reason="Confidential customer risk scores cannot be disclosed.",
        handoff_recommended=True,
        handoff_reason="Confidential internal metadata requested.",
    )
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "choices": [
            {
                "message": {
                    "content": "Customer personal details and risk scores are confidential. Please contact customer support for account assistance."
                }
            }
        ]
    }

    with patch("httpx.Client.post", return_value=mock_resp):
        provider = GrokLLMProvider(api_key="test-key", model_name="openai/gpt-oss-120b")
        resp = provider.generate(req)

        assert resp.decision_state == DecisionState.HANDOFF
        assert resp.handoff_recommended is True


# 13. Order lookup generation
def test_order_lookup_generation(sample_order_request):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "choices": [
            {
                "message": {
                    "content": "Order ORD-1001 is shipped with FedEx (Tracking: TRK-987654). Estimated delivery is August 15, 2026."
                }
            }
        ]
    }

    with patch("httpx.Client.post", return_value=mock_resp):
        provider = GrokLLMProvider(api_key="test-key", model_name="openai/gpt-oss-120b")
        resp = provider.generate(sample_order_request)

        assert not resp.is_fallback
        assert resp.supported_action == "order_lookup"
        assert "ORD-1001" in resp.message
        assert "TRK-987654" in resp.message


# 14. Factory provider instantiation and Gemini absence from default chain
def test_get_llm_provider_factory():
    mock_p = get_llm_provider("mock")
    assert isinstance(mock_p, MockLLMProvider)

    single_p = get_llm_provider("single_groq")
    assert isinstance(single_p, GrokLLMProvider)

    # Default provider chain must be Groq primary -> Groq fallback -> Deterministic
    default_chain = get_llm_provider()
    assert isinstance(default_chain, FallbackChainLLMProvider)
    assert isinstance(default_chain.primary_provider, GrokLLMProvider)
    assert isinstance(default_chain.fallback_provider, GrokLLMProvider)
    assert default_chain.primary_provider.model_name == "openai/gpt-oss-120b"
    assert default_chain.fallback_provider.model_name == "openai/gpt-oss-20b"
    assert not isinstance(default_chain.primary_provider, GeminiLLMProvider)
    assert not isinstance(default_chain.fallback_provider, GeminiLLMProvider)


# 15. Orchestrator integration with Groq fallback chain
def test_orchestrator_integration_with_groq_fallback_chain(sample_knowledge_request):
    from src.agent.orchestrator import AgentOrchestrator
    from src.core.session import SessionManager
    from src.tools.orders import get_order_repository

    primary_fail = MagicMock()
    primary_fail.status_code = 503

    fallback_success = MagicMock()
    fallback_success.status_code = 200
    fallback_success.json.return_value = {
        "choices": [
            {
                "message": {
                    "content": "You have 30 days to return an unused item. [01-returns-policy-current.md > Standard return window]"
                }
            }
        ]
    }

    call_count = 0

    def mock_post(url, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return primary_fail
        return fallback_success

    with patch("httpx.Client.post", side_effect=mock_post):
        primary_groq = GrokLLMProvider(api_key="test-key", model_name="openai/gpt-oss-120b")
        fallback_groq = GrokLLMProvider(api_key="test-key", model_name="openai/gpt-oss-20b")
        chain = FallbackChainLLMProvider(primary_provider=primary_groq, fallback_provider=fallback_groq)

        orch = AgentOrchestrator(
            session_manager=SessionManager(),
            order_repository=get_order_repository(),
            llm_provider=chain,
        )

        state = orch.process_turn("s_chain", "How long do I have to return an unused item?")
        assert state.response is not None
        assert not state.response.is_fallback
        assert state.trace["llm_telemetry"]["primary_success"] is False
        assert state.trace["llm_telemetry"]["fallback_used"] is True
        assert state.trace["llm_telemetry"]["fallback_success"] is True
        assert state.trace["llm_telemetry"]["final_provider"] == "groq-openai/gpt-oss-20b"


# 16. Orchestrator integration when both Groq models fail
def test_orchestrator_integration_both_groq_models_fail():
    from src.agent.orchestrator import AgentOrchestrator
    from src.core.session import SessionManager
    from src.tools.orders import get_order_repository

    err_resp = MagicMock()
    err_resp.status_code = 500

    with patch("httpx.Client.post", return_value=err_resp):
        primary_groq = GrokLLMProvider(api_key="test-key", model_name="openai/gpt-oss-120b")
        fallback_groq = GrokLLMProvider(api_key="test-key", model_name="openai/gpt-oss-20b")
        chain = FallbackChainLLMProvider(primary_provider=primary_groq, fallback_provider=fallback_groq)

        orch = AgentOrchestrator(
            session_manager=SessionManager(),
            order_repository=get_order_repository(),
            llm_provider=chain,
        )

        state = orch.process_turn("s_fail", "Where is my order ORD-1001?")
        assert state.response is not None
        assert state.response.is_fallback is True
        assert state.trace["generation_failed"] is True
        assert "ORD-1001" in state.response.message


# 17. Timeout exception handling for Groq
def test_groq_timeout_handling(sample_knowledge_request):
    import httpx

    with patch("httpx.Client.post", side_effect=httpx.TimeoutException("Network timed out")):
        groq = GrokLLMProvider(api_key="test-key", model_name="openai/gpt-oss-120b")
        with pytest.raises(LLMGenerationError) as exc_info:
            groq.generate(sample_knowledge_request)
        assert "timed out" in str(exc_info.value).lower()
