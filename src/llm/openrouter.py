"""OpenRouter API provider implementation for grounded language generation with multi-model support, retries, cost tracking, and caching."""

import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any, Dict, Optional

from src.core.config import get_settings
from src.llm.base import BaseLLMProvider, LLMGenerationError
from src.llm.models import GeneratedResponse, GroundedGenerationRequest
from src.llm.prompts import SYSTEM_PROMPT, build_user_prompt
from src.llm.validator import OutputValidator


class OpenRouterCostCapExceededError(LLMGenerationError):
    """Raised when cumulative OpenRouter API spend exceeds the configured safety limit."""
    pass


class OpenRouterLLMProvider(BaseLLMProvider):
    """OpenRouter provider supporting OpenAI-compatible chat completions with caching, cost guards, and retries."""

    # Class-level accumulator for tracking session spend
    cumulative_cost_usd: float = 0.0

    def __init__(
        self,
        api_key: Optional[str] = None,
        model_name: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout_seconds: Optional[float] = None,
        max_retries: Optional[int] = None,
        max_cost_usd: Optional[float] = None,
        enable_cache: bool = True,
        cache_dir: Optional[str] = None,
    ) -> None:
        settings = get_settings()
        if api_key is not None:
            self.api_key = api_key
        else:
            self.api_key = settings.openrouter_api_key or os.getenv("OPENROUTER_API_KEY")
        self.model_name = (
            model_name
            or settings.openrouter_primary_model
            or os.getenv("OPENROUTER_PRIMARY_MODEL", "meta-llama/llama-3.3-70b-instruct")
        )
        self.base_url = (
            base_url
            or settings.openrouter_base_url
            or os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
        ).rstrip("/")
        self.timeout_seconds = (
            timeout_seconds
            if timeout_seconds is not None
            else settings.openrouter_timeout_seconds
        )
        self.max_retries = (
            max_retries
            if max_retries is not None
            else settings.openrouter_max_retries
        )
        self.max_cost_usd = (
            max_cost_usd
            if max_cost_usd is not None
            else settings.openrouter_max_cost_usd
        )
        self.enable_cache = enable_cache

        # Set up cache path
        if cache_dir:
            self.cache_file = Path(cache_dir) / "openrouter_cache.json"
        else:
            self.cache_file = Path(settings.project_root) / ".cache" / "openrouter_cache.json"
        
        self.last_telemetry: Dict[str, Any] = {}

    @property
    def provider_name(self) -> str:
        return f"openrouter-{self.model_name}"

    def _get_cache_key(self, prompt: str) -> str:
        """Compute stable hash for question and evidence payload."""
        content = f"{self.model_name}::{SYSTEM_PROMPT}::{prompt}"
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    def _read_cache(self, cache_key: str) -> Optional[Dict[str, Any]]:
        """Read cached response if caching is enabled and entry exists."""
        if not self.enable_cache or not self.cache_file.exists():
            return None
        try:
            with open(self.cache_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data.get(cache_key)
        except Exception:
            return None

    def _write_cache(self, cache_key: str, entry: Dict[str, Any]) -> None:
        """Persist successful generation to cache."""
        if not self.enable_cache:
            return
        try:
            self.cache_file.parent.mkdir(parents=True, exist_ok=True)
            cache_data = {}
            if self.cache_file.exists():
                try:
                    with open(self.cache_file, "r", encoding="utf-8") as f:
                        cache_data = json.load(f)
                except Exception:
                    cache_data = {}
            cache_data[cache_key] = entry
            with open(self.cache_file, "w", encoding="utf-8") as f:
                json.dump(cache_data, f, indent=2)
        except Exception:
            pass  # Non-fatal if caching write fails

    def generate(self, request: GroundedGenerationRequest) -> GeneratedResponse:
        """Generate response via OpenRouter API with safety guards, retry backoff, and validation."""
        if not self.api_key or not self.api_key.strip():
            raise LLMGenerationError(
                "OpenRouter API key is not configured. Set OPENROUTER_API_KEY environment variable."
            )

        # Cost safety check before making outbound request
        if OpenRouterLLMProvider.cumulative_cost_usd >= self.max_cost_usd:
            raise OpenRouterCostCapExceededError(
                f"OpenRouter cumulative cost limit (${self.max_cost_usd:.2f}) reached. "
                f"Current spend: ${OpenRouterLLMProvider.cumulative_cost_usd:.4f}. Aborting live call."
            )

        prompt = build_user_prompt(request)
        cache_key = self._get_cache_key(prompt)

        # 1. Check local cache
        cached_entry = self._read_cache(cache_key)
        if cached_entry:
            raw_text = cached_entry["raw_text"]
            self.last_telemetry = {
                "provider": "openrouter",
                "model": self.model_name,
                "latency_ms": 0.0,
                "tokens_prompt": cached_entry.get("tokens_prompt", 0),
                "tokens_completion": cached_entry.get("tokens_completion", 0),
                "cost_usd": 0.0,
                "cached": True,
                "attempts": 0,
            }
            validation = OutputValidator.validate(raw_text, request)
            return validation.repaired_response or OutputValidator.build_fallback(request)

        # 2. Outbound HTTP Request via httpx with retry loop
        import httpx

        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "HTTP-Referer": "https://github.com/djcode0718/cometchat-ai-agent-intern-test",
            "X-Title": "Aster & Row Evaluation Suite",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model_name,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            "max_tokens": 600,
            "temperature": 0.0,
        }

        last_error: Optional[Exception] = None
        attempt = 0
        max_attempts = max(1, self.max_retries + 1)

        while attempt < max_attempts:
            attempt += 1
            start_time = time.perf_counter()
            try:
                with httpx.Client(timeout=self.timeout_seconds) as client:
                    resp = client.post(url, headers=headers, json=payload)
                    latency_ms = round((time.perf_counter() - start_time) * 1000, 2)

                    # Non-retryable Auth Errors
                    if resp.status_code in (401, 403):
                        raise LLMGenerationError(
                            f"OpenRouter authentication failed (HTTP {resp.status_code}). Check OPENROUTER_API_KEY."
                        )
                    # Insufficient credits / Billing
                    if resp.status_code == 402:
                        raise LLMGenerationError(
                            "OpenRouter credits exhausted or billing restriction (HTTP 402)."
                        )
                    # Bad Request / Model Unavailable
                    if resp.status_code == 400:
                        raise LLMGenerationError(
                            f"OpenRouter rejected request for model '{self.model_name}' (HTTP 400): {resp.text[:200]}"
                        )
                    # Transient Rate Limits (429) & Server Errors (5xx)
                    if resp.status_code == 429:
                        last_error = LLMGenerationError(f"OpenRouter rate limit exceeded (HTTP 429) on model '{self.model_name}'.")
                        if attempt < max_attempts:
                            time.sleep(2.0 * attempt)
                            continue
                        raise last_error
                    if resp.status_code >= 500:
                        last_error = LLMGenerationError(f"OpenRouter server error (HTTP {resp.status_code}) on model '{self.model_name}'.")
                        if attempt < max_attempts:
                            time.sleep(1.5 * attempt)
                            continue
                        raise last_error
                    if resp.status_code != 200:
                        raise LLMGenerationError(
                            f"OpenRouter returned unexpected status HTTP {resp.status_code}: {resp.text[:200]}"
                        )

                    data = resp.json()
                    break

            except (httpx.TimeoutException, httpx.RequestError) as e:
                latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
                last_error = LLMGenerationError(f"OpenRouter network/timeout error ({type(e).__name__}) after {self.timeout_seconds}s.")
                if attempt < max_attempts:
                    time.sleep(1.0 * attempt)
                    continue
                raise last_error from e

        # Extract completion and usage
        try:
            choices = data.get("choices", [])
            if not choices:
                raise LLMGenerationError(f"OpenRouter model '{self.model_name}' returned zero choice completions.")

            message = choices[0].get("message", {})
            raw_text = message.get("content")
            if not raw_text or not raw_text.strip():
                raise LLMGenerationError(f"OpenRouter model '{self.model_name}' returned empty content.")

            usage = data.get("usage", {})
            tokens_in = usage.get("prompt_tokens", 0)
            tokens_out = usage.get("completion_tokens", 0)
            cost = float(usage.get("cost", 0.0) or 0.0)

            OpenRouterLLMProvider.cumulative_cost_usd += cost

            self.last_telemetry = {
                "provider": "openrouter",
                "model": self.model_name,
                "latency_ms": latency_ms,
                "tokens_prompt": tokens_in,
                "tokens_completion": tokens_out,
                "cost_usd": cost,
                "cached": False,
                "attempts": attempt,
            }

            # Cache the successful generation
            self._write_cache(cache_key, {
                "raw_text": raw_text,
                "tokens_prompt": tokens_in,
                "tokens_completion": tokens_out,
                "cost_usd": cost,
                "model": self.model_name,
                "timestamp": time.time(),
            })

        except (KeyError, IndexError, TypeError) as e:
            raise LLMGenerationError(f"Failed to parse OpenRouter response payload: {type(e).__name__}") from e

        # 3. Output validation against safety boundaries and action claims
        validation = OutputValidator.validate(raw_text, request)
        return validation.repaired_response or OutputValidator.build_fallback(request)
