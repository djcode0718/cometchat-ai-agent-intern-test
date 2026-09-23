"""Unit and integration tests for Gemini, Grok, and FallbackChain LLM providers."""

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


# 1. Test Gemini Success
def test_gemini_provider_success(sample_knowledge_request):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "candidates": [
            {
                "content": {
                    "parts": [
                        {
                            "text": "You have 30 days to return items in original condition. [01-returns-policy-current.md > Standard Returns]"
                        }
                    ]
                }
            }
        ]
    }

    with patch("httpx.Client.post", return_value=mock_resp):
        provider = GeminiLLMProvider(api_key="test-gemini-key")
        resp = provider.generate(sample_knowledge_request)

        assert not resp.is_fallback
        assert "30 days" in resp.message
        assert len(resp.citations) == 1
        assert resp.citations[0].filename == "01-returns-policy-current.md"
        assert provider.last_latency_ms is not None
        assert provider.provider_name.startswith("gemini-")


# 2. Test Grok Success
def test_grok_provider_success(sample_knowledge_request):
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
        provider = GrokLLMProvider(api_key="test-grok-key")
        resp = provider.generate(sample_knowledge_request)

        assert not resp.is_fallback
        assert "30 days" in resp.message
        assert len(resp.citations) == 1
        assert resp.citations[0].filename == "01-returns-policy-current.md"
        assert provider.last_latency_ms is not None
        assert provider.provider_name.startswith(("groq-", "grok-"))


# 3. Test Gemini Failure -> Grok Success Fallback
def test_fallback_chain_gemini_fails_grok_succeeds(sample_knowledge_request):
    gemini_resp = MagicMock()
    gemini_resp.status_code = 500

    grok_resp = MagicMock()
    grok_resp.status_code = 200
    grok_resp.json.return_value = {
        "choices": [
            {
                "message": {
                    "content": "Items can be returned within 30 days. [01-returns-policy-current.md > Standard Returns]"
                }
            }
        ]
    }

    def mock_post(url, **kwargs):
        if "generativelanguage.googleapis.com" in url:
            return gemini_resp
        return grok_resp

    with patch("httpx.Client.post", side_effect=mock_post):
        gemini = GeminiLLMProvider(api_key="test-gemini-key")
        grok = GrokLLMProvider(api_key="test-grok-key")
        chain = FallbackChainLLMProvider(primary_provider=gemini, fallback_provider=grok)

        resp = chain.generate(sample_knowledge_request)

        assert not resp.is_fallback
        assert "30 days" in resp.message
        assert chain.last_telemetry["primary_success"] is False
        assert chain.last_telemetry["fallback_used"] is True
        assert chain.last_telemetry["fallback_success"] is True
        assert chain.last_telemetry["final_provider"].startswith(("groq-", "grok-"))


# 4. Test Gemini Failure -> Grok Failure -> Safe Fallback
def test_fallback_chain_both_fail_triggers_safe_fallback(sample_knowledge_request):
    err_resp = MagicMock()
    err_resp.status_code = 500

    with patch("httpx.Client.post", return_value=err_resp):
        gemini = GeminiLLMProvider(api_key="test-gemini-key")
        grok = GrokLLMProvider(api_key="test-grok-key")
        chain = FallbackChainLLMProvider(
            primary_provider=gemini,
            fallback_provider=grok,
            deterministic_fallback_on_error=True,
        )

        resp = chain.generate(sample_knowledge_request)

        assert resp.is_fallback is True
        assert chain.last_telemetry["primary_success"] is False
        assert chain.last_telemetry["fallback_used"] is True
        assert chain.last_telemetry["fallback_success"] is False
        assert chain.last_telemetry["final_provider"] == "deterministic_fallback"


# 5. Missing Gemini Key Error
def test_gemini_missing_key_raises(sample_knowledge_request):
    provider = GeminiLLMProvider(api_key="")
    with pytest.raises(LLMGenerationError) as exc_info:
        provider.generate(sample_knowledge_request)
    assert "Gemini API key is not configured" in str(exc_info.value)


# 6. Missing Grok Key Error
def test_grok_missing_key_raises(sample_knowledge_request):
    provider = GrokLLMProvider(api_key="")
    with pytest.raises(LLMGenerationError) as exc_info:
        provider.generate(sample_knowledge_request)
    assert "API key is not configured" in str(exc_info.value)


# 7. Both Keys Missing in Fallback Chain
def test_chain_both_keys_missing_triggers_error_or_fallback(sample_knowledge_request):
    gemini = GeminiLLMProvider(api_key="")
    grok = GrokLLMProvider(api_key="")
    chain = FallbackChainLLMProvider(primary_provider=gemini, fallback_provider=grok)

    with pytest.raises(LLMGenerationError) as exc_info:
        chain.generate(sample_knowledge_request)
    assert "Primary provider failed" in str(exc_info.value)
    assert chain.last_telemetry["fallback_used"] is True
    assert chain.last_telemetry["final_provider"] == "deterministic_fallback"


# 8. Rate limit handling
def test_gemini_rate_limit_handled(sample_knowledge_request):
    mock_resp = MagicMock()
    mock_resp.status_code = 429

    with patch("httpx.Client.post", return_value=mock_resp):
        provider = GeminiLLMProvider(api_key="test-key")
        with pytest.raises(LLMGenerationError) as exc_info:
            provider.generate(sample_knowledge_request)
        assert "rate limit" in str(exc_info.value).lower()


# 9. Output validation: Empty/Whitespace Response from Provider
def test_provider_empty_response_triggers_validation_fallback(sample_knowledge_request):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "candidates": [{"content": {"parts": [{"text": "   "}]}}]
    }

    with patch("httpx.Client.post", return_value=mock_resp):
        provider = GeminiLLMProvider(api_key="test-key")
        resp = provider.generate(sample_knowledge_request)

        assert resp.is_fallback is True
        assert "empty or whitespace" in (resp.fallback_reason or "").lower()


# 10. Output validation: Mutation claims rejected
def test_provider_mutation_claim_rejected(sample_knowledge_request):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "candidates": [{"content": {"parts": [{"text": "I have cancelled your order and issued your refund."}]}}]
    }

    with patch("httpx.Client.post", return_value=mock_resp):
        provider = GeminiLLMProvider(api_key="test-key")
        resp = provider.generate(sample_knowledge_request)

        assert resp.is_fallback is True
        assert "validation failed" in (resp.fallback_reason or "").lower()


# 11. Decision state preservation: CONFLICT
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
        "candidates": [
            {
                "content": {
                    "parts": [
                        {
                            "text": "Official Aster & Row guides conflict: the Product Care Guide states hand-wash [11-product-care.md > Breeze Tumbler], while the Product Card says dishwasher safe [12-breeze-tumbler-product-card.md > Cleaning]."
                        }
                    ]
                }
            }
        ]
    }

    with patch("httpx.Client.post", return_value=mock_resp):
        provider = GeminiLLMProvider(api_key="test-key")
        resp = provider.generate(req)

        assert resp.decision_state == DecisionState.CONFLICT
        assert len(resp.citations) == 2


# 12. Decision state preservation: ABSTAIN
def test_abstain_decision_preserved_with_provider():
    req = GroundedGenerationRequest(
        user_query="What fabric is used in the Nomad series?",
        decision_state=DecisionState.ABSTAIN,
        decision_reason="No relevant documentation found for Nomad series.",
    )
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "candidates": [
            {
                "content": {
                    "parts": [
                        {
                            "text": "We do not have sufficient information in our official policies to confirm the fabrics for the Nomad series. Please contact support."
                        }
                    ]
                }
            }
        ]
    }

    with patch("httpx.Client.post", return_value=mock_resp):
        provider = GeminiLLMProvider(api_key="test-key")
        resp = provider.generate(req)

        assert resp.decision_state == DecisionState.ABSTAIN


# 13. Decision state preservation: HANDOFF
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
        "candidates": [
            {
                "content": {
                    "parts": [
                        {
                            "text": "Customer personal details and risk scores are confidential. Please contact customer support for account assistance."
                        }
                    ]
                }
            }
        ]
    }

    with patch("httpx.Client.post", return_value=mock_resp):
        provider = GeminiLLMProvider(api_key="test-key")
        resp = provider.generate(req)

        assert resp.decision_state == DecisionState.HANDOFF
        assert resp.handoff_recommended is True


# 14. Order lookup generation
def test_order_lookup_generation(sample_order_request):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "candidates": [
            {
                "content": {
                    "parts": [
                        {
                            "text": "Order ORD-1001 is shipped with FedEx (Tracking: TRK-987654). Estimated delivery is August 15, 2026."
                        }
                    ]
                }
            }
        ]
    }

    with patch("httpx.Client.post", return_value=mock_resp):
        provider = GeminiLLMProvider(api_key="test-key")
        resp = provider.generate(sample_order_request)

        assert not resp.is_fallback
        assert resp.supported_action == "order_lookup"
        assert "ORD-1001" in resp.message
        assert "TRK-987654" in resp.message


# 15. Factory provider instantiation
def test_get_llm_provider_factory():
    mock_p = get_llm_provider("mock")
    assert isinstance(mock_p, MockLLMProvider)

    grok_p = get_llm_provider("grok")
    assert isinstance(grok_p, GrokLLMProvider)

    chain_p = get_llm_provider("gemini")
    assert isinstance(chain_p, FallbackChainLLMProvider)
    assert isinstance(chain_p.primary_provider, GeminiLLMProvider)
    assert isinstance(chain_p.fallback_provider, GrokLLMProvider)


# 16. Orchestrator integration with fallback chain
def test_orchestrator_integration_with_fallback_chain(sample_knowledge_request):
    from src.agent.orchestrator import AgentOrchestrator
    from src.core.session import SessionManager
    from src.tools.orders import get_order_repository

    grok_resp = MagicMock()
    grok_resp.status_code = 200
    grok_resp.json.return_value = {
        "choices": [
            {
                "message": {
                    "content": "You have 30 days to return an unused item. [01-returns-policy-current.md > Standard return window]"
                }
            }
        ]
    }

    gemini_resp = MagicMock()
    gemini_resp.status_code = 503

    def mock_post(url, **kwargs):
        if "generativelanguage.googleapis.com" in url:
            return gemini_resp
        return grok_resp

    with patch("httpx.Client.post", side_effect=mock_post):
        gemini = GeminiLLMProvider(api_key="test-gemini")
        grok = GrokLLMProvider(api_key="test-grok")
        chain = FallbackChainLLMProvider(primary_provider=gemini, fallback_provider=grok)

        orch = AgentOrchestrator(
            session_manager=SessionManager(),
            order_repository=get_order_repository(),
            llm_provider=chain,
        )

        state = orch.process_turn("s_chain", "How long do I have to return an unused item?")
        assert state.response is not None
        assert not state.response.is_fallback
        assert state.trace["llm_telemetry"]["fallback_used"] is True
        assert state.trace["llm_telemetry"]["final_provider"].startswith(("groq-", "grok-"))


# 17. Orchestrator integration when both providers fail
def test_orchestrator_integration_both_providers_fail():
    from src.agent.orchestrator import AgentOrchestrator
    from src.core.session import SessionManager
    from src.tools.orders import get_order_repository

    err_resp = MagicMock()
    err_resp.status_code = 500

    with patch("httpx.Client.post", return_value=err_resp):
        gemini = GeminiLLMProvider(api_key="test-gemini")
        grok = GrokLLMProvider(api_key="test-grok")
        chain = FallbackChainLLMProvider(primary_provider=gemini, fallback_provider=grok)

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


# 18. Timeout exception handling
def test_gemini_and_grok_timeout_handling(sample_knowledge_request):
    import httpx

    with patch("httpx.Client.post", side_effect=httpx.TimeoutException("Network timed out")):
        gemini = GeminiLLMProvider(api_key="test-key")
        with pytest.raises(LLMGenerationError) as exc_info:
            gemini.generate(sample_knowledge_request)
        assert "timed out" in str(exc_info.value).lower()

        grok = GrokLLMProvider(api_key="test-key")
        with pytest.raises(LLMGenerationError) as exc_info2:
            grok.generate(sample_knowledge_request)
        assert "timed out" in str(exc_info2.value).lower()

