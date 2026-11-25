"""Provider resilience and fault matrix tests (20 response cases + fallback cascade + opt-in live suite)."""

import os
import json
import time
import pytest
from unittest.mock import patch, MagicMock
import httpx

from src.agent.decision import DecisionState
from src.llm.openrouter import OpenRouterLLMProvider
from src.llm.openrouter_chain import OpenRouterFallbackChainProvider
from src.llm.base import GroundedGenerationRequest, GeneratedResponse, LLMGenerationError
from src.llm.validator import OutputValidator
from src.core.config import get_settings
from src.core.models import CitationSource
from src.llm.factory import get_llm_provider
from src.llm.ollama import OllamaLLMProvider


@pytest.fixture
def base_request():
    return GroundedGenerationRequest(
        user_query="How many days do I have to return an item?",
        decision_state="ANSWER",
        decision_reason="Standard returns inquiry",
        citations=[CitationSource(filename="01-returns-policy-current.md", heading="Standard return window")],
    )


# =============================================================================
# The 20 Provider Response Tests
# =============================================================================

def test_pr_01_valid_json_response(base_request):
    """1. Valid JSON response with standard completion choices."""
    provider = OpenRouterLLMProvider(api_key="test-key", enable_cache=False)
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "choices": [{"message": {"content": "Standard returns are accepted within 30 days. [01-returns-policy-current.md > Standard return window]"}}],
        "usage": {"prompt_tokens": 50, "completion_tokens": 20},
    }
    with patch("httpx.Client.post", return_value=mock_resp):
        res = provider.generate(base_request)
        assert res.is_fallback is False
        assert "30 days" in res.message


def test_pr_02_valid_plain_text_response(base_request):
    """2. Valid plain text response (extracted from choices message content)."""
    provider = OpenRouterLLMProvider(api_key="test-key", enable_cache=False)
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "choices": [{"message": {"content": "You can return your item within 30 days of delivery."}}],
        "usage": {"prompt_tokens": 40, "completion_tokens": 15},
    }
    with patch("httpx.Client.post", return_value=mock_resp):
        res = provider.generate(base_request)
        assert len(res.message) > 0


def test_pr_03_empty_response(base_request):
    """3. Empty response content raises LLMGenerationError."""
    provider = OpenRouterLLMProvider(api_key="test-key", enable_cache=False, max_retries=0)
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "choices": [{"message": {"content": "   "}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 0},
    }
    with patch("httpx.Client.post", return_value=mock_resp):
        with pytest.raises(LLMGenerationError) as exc_info:
            provider.generate(base_request)
        assert "empty content" in str(exc_info.value).lower()


def test_pr_04_missing_content_field(base_request):
    """4. Missing content field in choices dictionary raises LLMGenerationError."""
    provider = OpenRouterLLMProvider(api_key="test-key", enable_cache=False, max_retries=0)
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "choices": [{"message": {}}],
    }
    with patch("httpx.Client.post", return_value=mock_resp):
        with pytest.raises(LLMGenerationError):
            provider.generate(base_request)


def test_pr_05_malformed_json_response(base_request):
    """5. Malformed JSON payload raises error."""
    provider = OpenRouterLLMProvider(api_key="test-key", enable_cache=False, max_retries=0)
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.side_effect = json.JSONDecodeError("Expecting value", "doc", 0)
    with patch("httpx.Client.post", return_value=mock_resp):
        with pytest.raises((LLMGenerationError, json.JSONDecodeError)):
            provider.generate(base_request)


def test_pr_06_unexpected_response_schema(base_request):
    """6. Unexpected schema (missing choices key)."""
    provider = OpenRouterLLMProvider(api_key="test-key", enable_cache=False, max_retries=0)
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"error": "unexpected format", "data": []}
    with patch("httpx.Client.post", return_value=mock_resp):
        with pytest.raises(LLMGenerationError) as exc:
            provider.generate(base_request)
        assert "zero choice completions" in str(exc.value)


def test_pr_07_http_400_bad_request(base_request):
    """7. HTTP 400 Bad Request triggers non-retryable LLMGenerationError."""
    provider = OpenRouterLLMProvider(api_key="test-key", enable_cache=False, max_retries=2)
    mock_resp = MagicMock()
    mock_resp.status_code = 400
    mock_resp.text = "Bad Request: context length exceeded"
    with patch("httpx.Client.post", return_value=mock_resp) as mock_post:
        with pytest.raises(LLMGenerationError) as exc:
            provider.generate(base_request)
        assert "HTTP 400" in str(exc.value)
        # Should not retry 400
        assert mock_post.call_count == 1


def test_pr_08_http_401_unauthorized(base_request):
    """8. HTTP 401 Unauthorized fails immediately without retrying."""
    provider = OpenRouterLLMProvider(api_key="invalid-key", enable_cache=False, max_retries=3)
    mock_resp = MagicMock()
    mock_resp.status_code = 401
    mock_resp.text = "Unauthorized"
    with patch("httpx.Client.post", return_value=mock_resp) as mock_post:
        with pytest.raises(LLMGenerationError) as exc:
            provider.generate(base_request)
        assert "401" in str(exc.value)
        assert mock_post.call_count == 1


def test_pr_09_http_402_payment_required(base_request):
    """9. HTTP 402 Credits Exhausted fails immediately without infinite retry loop."""
    provider = OpenRouterLLMProvider(api_key="depleted-key", enable_cache=False, max_retries=3)
    mock_resp = MagicMock()
    mock_resp.status_code = 402
    mock_resp.text = "Insufficient credits"
    with patch("httpx.Client.post", return_value=mock_resp) as mock_post:
        with pytest.raises(LLMGenerationError) as exc:
            provider.generate(base_request)
        assert "402" in str(exc.value)
        assert mock_post.call_count == 1


def test_pr_10_http_429_rate_limit(base_request):
    """10. HTTP 429 Rate Limit triggers backoff up to max_retries."""
    provider = OpenRouterLLMProvider(api_key="test-key", enable_cache=False, max_retries=1)
    mock_resp = MagicMock()
    mock_resp.status_code = 429
    with patch("httpx.Client.post", return_value=mock_resp) as mock_post, patch("time.sleep"):
        with pytest.raises(LLMGenerationError) as exc:
            provider.generate(base_request)
        assert "429" in str(exc.value)
        assert mock_post.call_count == 2  # initial + 1 retry


def test_pr_11_http_500_internal_server_error(base_request):
    """11. HTTP 500 triggers retry backoff."""
    provider = OpenRouterLLMProvider(api_key="test-key", enable_cache=False, max_retries=1)
    mock_resp = MagicMock()
    mock_resp.status_code = 500
    with patch("httpx.Client.post", return_value=mock_resp) as mock_post, patch("time.sleep"):
        with pytest.raises(LLMGenerationError) as exc:
            provider.generate(base_request)
        assert "500" in str(exc.value)
        assert mock_post.call_count == 2


def test_pr_12_http_502_bad_gateway(base_request):
    """12. HTTP 502 Bad Gateway triggers retry backoff."""
    provider = OpenRouterLLMProvider(api_key="test-key", enable_cache=False, max_retries=1)
    mock_resp = MagicMock()
    mock_resp.status_code = 502
    with patch("httpx.Client.post", return_value=mock_resp) as mock_post, patch("time.sleep"):
        with pytest.raises(LLMGenerationError):
            provider.generate(base_request)
        assert mock_post.call_count == 2


def test_pr_13_http_503_service_unavailable(base_request):
    """13. HTTP 503 Service Unavailable triggers retry backoff."""
    provider = OpenRouterLLMProvider(api_key="test-key", enable_cache=False, max_retries=1)
    mock_resp = MagicMock()
    mock_resp.status_code = 503
    with patch("httpx.Client.post", return_value=mock_resp) as mock_post, patch("time.sleep"):
        with pytest.raises(LLMGenerationError):
            provider.generate(base_request)
        assert mock_post.call_count == 2


def test_pr_14_connection_timeout(base_request):
    """14. ConnectTimeout exception handling and retry."""
    provider = OpenRouterLLMProvider(api_key="test-key", enable_cache=False, max_retries=1)
    with patch("httpx.Client.post", side_effect=httpx.ConnectTimeout("Connect timeout")) as mock_post, patch("time.sleep"):
        with pytest.raises(LLMGenerationError) as exc:
            provider.generate(base_request)
        assert "timeout" in str(exc.value).lower()
        assert mock_post.call_count == 2


def test_pr_15_read_timeout(base_request):
    """15. ReadTimeout exception handling."""
    provider = OpenRouterLLMProvider(api_key="test-key", enable_cache=False, max_retries=1)
    with patch("httpx.Client.post", side_effect=httpx.ReadTimeout("Read timeout")) as mock_post, patch("time.sleep"):
        with pytest.raises(LLMGenerationError) as exc:
            provider.generate(base_request)
        assert "timeout" in str(exc.value).lower()
        assert mock_post.call_count == 2


def test_pr_16_connection_reset(base_request):
    """16. ConnectionReset / Network error."""
    provider = OpenRouterLLMProvider(api_key="test-key", enable_cache=False, max_retries=1)
    with patch("httpx.Client.post", side_effect=httpx.NetworkError("Connection reset by peer")) as mock_post, patch("time.sleep"):
        with pytest.raises(LLMGenerationError) as exc:
            provider.generate(base_request)
        assert "network" in str(exc.value).lower()
        assert mock_post.call_count == 2


def test_pr_17_invalid_model_response(base_request):
    """17. Provider returns error for unknown/unsupported model."""
    provider = OpenRouterLLMProvider(model_name="nonexistent/fake-model", api_key="test-key", enable_cache=False, max_retries=0)
    mock_resp = MagicMock()
    mock_resp.status_code = 400
    mock_resp.text = '{"error": {"message": "Model not found"}}'
    with patch("httpx.Client.post", return_value=mock_resp):
        with pytest.raises(LLMGenerationError) as exc:
            provider.generate(base_request)
        assert "rejected request" in str(exc.value).lower()


def test_pr_18_excessively_long_response(base_request):
    """18. Truncation / handling of response exceeding normal length limits."""
    provider = OpenRouterLLMProvider(api_key="test-key", enable_cache=False)
    huge_text = "Return window is 30 days. " + ("Policy word " * 2000)
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "choices": [{"message": {"content": huge_text}}],
        "usage": {"prompt_tokens": 100, "completion_tokens": 2000},
    }
    with patch("httpx.Client.post", return_value=mock_resp):
        res = provider.generate(base_request)
        assert len(res.message) > 0


def test_pr_19_response_containing_unsupported_claims(base_request):
    """19. Response with unsupported claims is audited by OutputValidator."""
    # LLM hallucinates 100 days return window
    hallucinated_text = "Aster & Row allows returns within 100 days of purchase for full cash refund."
    val = OutputValidator.validate(hallucinated_text, base_request)
    # OutputValidator flags or repairs
    assert val.repaired_response is not None or not val.is_valid


def test_pr_20_response_containing_malformed_citations(base_request):
    """20. Response with malformed citations syntax is sanitized/corrected."""
    bad_citation_text = "You have 30 days to return. [[invalid-citation>>bad]]"
    val = OutputValidator.validate(bad_citation_text, base_request)
    assert val.repaired_response is not None or not val.is_valid


# =============================================================================
# Provider Fallback Cascade Tests
# =============================================================================

def test_fallback_cascade_primary_succeeds(base_request):
    """Cascade: Primary succeeds without triggering secondary."""
    chain = OpenRouterFallbackChainProvider(
        primary_model="primary-mock",
        secondary_model="secondary-mock",
        enable_cache=False,
    )
    mock_resp = GeneratedResponse(message="Primary model answer.", decision_state=DecisionState.ANSWER, is_fallback=False)
    with patch.object(chain.primary_provider, "generate", return_value=mock_resp) as p_mock:
        res = chain.generate(base_request)
        assert res.message == "Primary model answer."
        assert p_mock.call_count == 1
        assert chain.last_telemetry["final_model"] == "primary-mock"
        assert chain.last_telemetry["fallback_occurred"] is False


def test_fallback_cascade_primary_fails_secondary_succeeds(base_request):
    """Cascade: Primary fails -> secondary succeeds."""
    chain = OpenRouterFallbackChainProvider(
        primary_model="primary-mock",
        secondary_model="secondary-mock",
        enable_cache=False,
    )
    mock_resp = GeneratedResponse(message="Secondary model answer.", decision_state=DecisionState.ANSWER, is_fallback=False)
    with patch.object(chain.primary_provider, "generate", side_effect=LLMGenerationError("Primary 500")), \
         patch.object(chain.secondary_provider, "generate", return_value=mock_resp) as s_mock:
        res = chain.generate(base_request)
        assert res.message == "Secondary model answer."
        assert s_mock.call_count == 1
        assert chain.last_telemetry["final_model"] == "secondary-mock"
        assert chain.last_telemetry["fallback_occurred"] is True


def test_fallback_cascade_all_fail_deterministic_succeeds(base_request):
    """Cascade: All remote providers fail -> deterministic fallback builder succeeds."""
    chain = OpenRouterFallbackChainProvider(
        primary_model="primary-mock",
        secondary_model="secondary-mock",
        tertiary_model="tertiary-mock",
        enable_cache=False,
    )
    patches = [
        patch.object(chain.primary_provider, "generate", side_effect=LLMGenerationError("402")),
        patch.object(chain.secondary_provider, "generate", side_effect=LLMGenerationError("402")),
        patch.object(chain.tertiary_provider, "generate", side_effect=LLMGenerationError("402")),
    ]
    if chain.groq_provider is not None:
        patches.append(patch.object(chain.groq_provider, "generate", side_effect=LLMGenerationError("Groq 500")))

    for p in patches:
        p.start()
    try:
        res = chain.generate(base_request)
        assert res.is_fallback is True
        assert chain.last_telemetry["final_model"] == "deterministic_evidence_builder"
        assert chain.last_telemetry["fallback_occurred"] is True
    finally:
        for p in patches:
            p.stop()


# =============================================================================
# Opt-In Live / Local LLM Test Suite (Gated by LIVE_LLM_TESTS=1)
# =============================================================================

@pytest.mark.skipif(
    os.getenv("LIVE_LLM_TESTS", "0") != "1" or int(os.getenv("LIVE_LLM_MAX_REQUESTS", "0")) <= 0,
    reason="Live LLM tests are strictly opt-in and require LIVE_LLM_TESTS=1 and positive LIVE_LLM_MAX_REQUESTS budget."
)
def test_live_opt_in_provider_probe():
    """Live LLM test probe supporting both online providers and local offline Ollama."""
    settings = get_settings()
    if settings.offline_mode or os.getenv("LLM_PROVIDER") == "ollama":
        provider = OllamaLLMProvider()
    else:
        # If openrouter API key is available or online provider configured, use factory
        provider = get_llm_provider()

    req = GroundedGenerationRequest(
        user_query="Hello! What is your return window?",
        decision_state=DecisionState.ANSWER,
        decision_reason="Testing opt-in provider generation probe",
    )
    resp = provider.generate(req)
    assert resp is not None
    assert len(resp.message) > 0
    assert resp.decision_state == DecisionState.ANSWER
