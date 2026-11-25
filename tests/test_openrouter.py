"""Unit tests for OpenRouter provider, fallback chain, cost guard, caching, and error resilience."""

import json
from unittest.mock import MagicMock, patch
import httpx
import pytest

from src.core.models import CitationSource, DecisionState
from src.llm.base import LLMGenerationError
from src.llm.models import GroundedGenerationRequest
from src.llm.openrouter import OpenRouterCostCapExceededError, OpenRouterLLMProvider
from src.llm.openrouter_chain import OpenRouterFallbackChainProvider


@pytest.fixture
def sample_request():
    return GroundedGenerationRequest(
        user_query="How long is the return window?",
        decision_state=DecisionState.ANSWER,
        decision_reason="Sufficient approved evidence found.",
        approved_evidence=[],
        citations=[CitationSource(filename="01-returns-policy-current.md", heading="Standard return window")],
    )


def test_openrouter_missing_api_key_raises_error(sample_request):
    """Verify missing API key raises LLMGenerationError."""
    provider = OpenRouterLLMProvider(api_key="")
    with pytest.raises(LLMGenerationError) as exc_info:
        provider.generate(sample_request)
    assert "OpenRouter API key is not configured" in str(exc_info.value)


def test_openrouter_successful_generation(sample_request):
    """Verify standard successful generation with valid choices and usage."""
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "choices": [
            {
                "message": {
                    "content": "You can return items within 30 days [01-returns-policy-current.md > Standard return window]."
                }
            }
        ],
        "usage": {"prompt_tokens": 50, "completion_tokens": 20, "cost": 0.00004},
    }

    provider = OpenRouterLLMProvider(api_key="sk-or-test-mock-key", enable_cache=False)
    with patch("httpx.Client.post", return_value=mock_response):
        response = provider.generate(sample_request)

    assert response.is_fallback is False
    assert "within 30 days" in response.message
    assert len(response.citations) == 1
    assert provider.last_telemetry["model"] == provider.model_name
    assert provider.last_telemetry["cost_usd"] == 0.00004


def test_openrouter_rate_limit_retry(sample_request):
    """Verify HTTP 429 triggers retry backoff and succeeds on subsequent attempt."""
    mock_429 = MagicMock(spec=httpx.Response)
    mock_429.status_code = 429

    mock_200 = MagicMock(spec=httpx.Response)
    mock_200.status_code = 200
    mock_200.json.return_value = {
        "choices": [{"message": {"content": "Returns are 30 days [01-returns-policy-current.md > Standard return window]."}}],
        "usage": {"prompt_tokens": 40, "completion_tokens": 15, "cost": 0.00002},
    }

    provider = OpenRouterLLMProvider(api_key="sk-or-test-mock-key", max_retries=1, enable_cache=False)
    with patch("httpx.Client.post", side_effect=[mock_429, mock_200]), patch("time.sleep"):
        response = provider.generate(sample_request)

    assert response.is_fallback is False
    assert provider.last_telemetry["attempts"] == 2


def test_openrouter_auth_failure_non_retryable(sample_request):
    """Verify HTTP 401 fails immediately without retrying."""
    mock_401 = MagicMock(spec=httpx.Response)
    mock_401.status_code = 401

    provider = OpenRouterLLMProvider(api_key="sk-or-invalid-key", max_retries=2, enable_cache=False)
    with patch("httpx.Client.post", return_value=mock_401) as mock_post:
        with pytest.raises(LLMGenerationError) as exc_info:
            provider.generate(sample_request)

    assert mock_post.call_count == 1
    assert "authentication failed" in str(exc_info.value).lower()


def test_openrouter_cost_cap_guard(sample_request):
    """Verify spending beyond max_cost_usd raises OpenRouterCostCapExceededError before making API call."""
    provider = OpenRouterLLMProvider(api_key="sk-or-test-mock-key", max_cost_usd=0.001, enable_cache=False)
    OpenRouterLLMProvider.cumulative_cost_usd = 0.005  # Force over limit

    with pytest.raises(OpenRouterCostCapExceededError) as exc_info:
        provider.generate(sample_request)

    assert "cost limit" in str(exc_info.value).lower()
    OpenRouterLLMProvider.cumulative_cost_usd = 0.0  # Reset for other tests


def test_openrouter_caching_behavior(tmp_path, sample_request):
    """Verify caching returns cached response on second invocation without HTTP calls."""
    cache_dir = str(tmp_path)
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "choices": [{"message": {"content": "Cached return window is 30 days [01-returns-policy-current.md > Standard return window]."}}],
        "usage": {"prompt_tokens": 50, "completion_tokens": 20, "cost": 0.00004},
    }

    provider = OpenRouterLLMProvider(api_key="sk-or-test-mock-key", cache_dir=cache_dir, enable_cache=True)
    with patch("httpx.Client.post", return_value=mock_response) as mock_post:
        # First call
        resp1 = provider.generate(sample_request)
        assert mock_post.call_count == 1
        assert provider.last_telemetry["cached"] is False

        # Second call with identical request
        resp2 = provider.generate(sample_request)
        assert mock_post.call_count == 1  # No additional HTTP call
        assert provider.last_telemetry["cached"] is True
        assert resp1.message == resp2.message


def test_openrouter_fallback_chain_primary_success(sample_request):
    """Verify chain returns primary model response when primary succeeds."""
    chain = OpenRouterFallbackChainProvider(
        openrouter_api_key="sk-or-mock",
        primary_model="model-primary",
        secondary_model="model-secondary",
        enable_cache=False,
    )

    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "choices": [{"message": {"content": "Primary model answer [01-returns-policy-current.md > Standard return window]."}}],
        "usage": {"prompt_tokens": 30, "completion_tokens": 10, "cost": 0.00001},
    }

    with patch("httpx.Client.post", return_value=mock_resp):
        response = chain.generate(sample_request)

    assert response.is_fallback is False
    assert "Primary model answer" in response.message
    assert chain.last_telemetry["final_tier"] == "openrouter_primary"
    assert chain.last_telemetry["fallback_occurred"] is False


def test_openrouter_fallback_chain_secondary_fallback(sample_request):
    """Verify chain falls back to secondary when primary fails."""
    chain = OpenRouterFallbackChainProvider(
        openrouter_api_key="sk-or-mock",
        primary_model="model-primary",
        secondary_model="model-secondary",
        enable_cache=False,
    )

    mock_500 = MagicMock(spec=httpx.Response)
    mock_500.status_code = 500

    mock_200 = MagicMock(spec=httpx.Response)
    mock_200.status_code = 200
    mock_200.json.return_value = {
        "choices": [{"message": {"content": "Secondary model answer [01-returns-policy-current.md > Standard return window]."}}],
        "usage": {"prompt_tokens": 30, "completion_tokens": 10, "cost": 0.00001},
    }

    # Primary fails (500s across max retries), secondary succeeds (200)
    with patch("httpx.Client.post", side_effect=[mock_500, mock_200]), patch("time.sleep"):
        chain.primary_provider.max_retries = 0  # Fast fail primary
        chain.secondary_provider.max_retries = 0
        response = chain.generate(sample_request)

    assert response.is_fallback is False
    assert "Secondary model answer" in response.message
    assert chain.last_telemetry["final_tier"] == "openrouter_secondary"
    assert chain.last_telemetry["fallback_occurred"] is True


def test_openrouter_fallback_chain_all_fail_deterministic_fallback(sample_request):
    """Verify chain cleanly falls back to deterministic evidence builder when all live models fail."""
    chain = OpenRouterFallbackChainProvider(
        openrouter_api_key="sk-or-mock",
        primary_model="model-primary",
        secondary_model="model-secondary",
        tertiary_model="model-tertiary",
        enable_cache=False,
        deterministic_fallback_on_error=True,
    )
    chain.primary_provider.max_retries = 0
    chain.secondary_provider.max_retries = 0
    chain.tertiary_provider.max_retries = 0

    mock_500 = MagicMock(spec=httpx.Response)
    mock_500.status_code = 500

    with patch("httpx.Client.post", return_value=mock_500), patch("time.sleep"):
        response = chain.generate(sample_request)

    assert response.is_fallback is True
    assert chain.last_telemetry["final_tier"] == "deterministic_fallback"
    assert chain.last_telemetry["fallback_occurred"] is True
