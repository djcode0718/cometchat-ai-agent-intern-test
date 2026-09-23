"""Groq API provider implementation for fallback language generation."""

import os
import time
from typing import Optional

from src.core.config import get_settings
from src.llm.base import BaseLLMProvider, LLMGenerationError
from src.llm.models import GeneratedResponse, GroundedGenerationRequest
from src.llm.prompts import SYSTEM_PROMPT, build_user_prompt
from src.llm.validator import OutputValidator


class GrokLLMProvider(BaseLLMProvider):
    """Fallback LLM provider using Groq API."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model_name: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout_seconds: float = 15.0,
    ) -> None:
        settings = get_settings()
        if api_key is not None:
            self.api_key = api_key
        else:
            self.api_key = (
                settings.groq_api_key
                or os.getenv("GROQ_API_KEY")
                or os.getenv("GROK_API_KEY")
                or os.getenv("XAI_API_KEY")
            )
        self.model_name = (
            model_name
            or settings.groq_llm_model
            or os.getenv("GROQ_LLM_MODEL")
            or os.getenv("GROK_MODEL", "llama-3.3-70b-versatile")
        )
        self.base_url = (
            base_url
            or settings.groq_base_url
            or os.getenv("GROQ_BASE_URL")
            or os.getenv("GROK_BASE_URL", "https://api.groq.com/openai/v1")
        ).rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.last_latency_ms: Optional[float] = None

    @property
    def provider_name(self) -> str:
        return f"groq-{self.model_name}"

    def generate(self, request: GroundedGenerationRequest) -> GeneratedResponse:
        """Generate response via Groq API. Raises LLMGenerationError on failure."""
        if not self.api_key or not self.api_key.strip():
            raise LLMGenerationError(
                "Groq API key is not configured. Set GROQ_API_KEY environment variable."
            )

        import httpx

        prompt = build_user_prompt(request)
        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model_name,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.0,
        }

        start_time = time.perf_counter()
        try:
            with httpx.Client(timeout=self.timeout_seconds) as client:
                resp = client.post(url, headers=headers, json=payload)
                self.last_latency_ms = round((time.perf_counter() - start_time) * 1000, 2)

                if resp.status_code == 401 or resp.status_code == 403:
                    raise LLMGenerationError(
                        f"Grok API authentication failed (HTTP {resp.status_code}). Check GROK_API_KEY."
                    )
                if resp.status_code == 429:
                    raise LLMGenerationError("Grok API rate limit exceeded (HTTP 429).")
                if resp.status_code >= 500:
                    raise LLMGenerationError(
                        f"Grok API server error (HTTP {resp.status_code})."
                    )
                if resp.status_code != 200:
                    raise LLMGenerationError(
                        f"Grok API returned unexpected status HTTP {resp.status_code}."
                    )

                data = resp.json()
        except httpx.TimeoutException as e:
            self.last_latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
            raise LLMGenerationError(f"Grok API request timed out after {self.timeout_seconds}s.") from e
        except httpx.RequestError as e:
            self.last_latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
            raise LLMGenerationError(f"Grok API network connection error: {type(e).__name__}") from e
        except LLMGenerationError:
            raise
        except Exception as e:
            self.last_latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
            raise LLMGenerationError(f"Grok API call failed: {type(e).__name__}") from e

        # Extract text content safely
        try:
            choices = data.get("choices", [])
            if not choices:
                raise LLMGenerationError("Grok API returned zero choice completions.")
            
            message = choices[0].get("message", {})
            raw_text = message.get("content")
            if not raw_text:
                raise LLMGenerationError("Grok API choice missing message content.")
        except (KeyError, IndexError, TypeError) as e:
            raise LLMGenerationError(f"Failed to parse Grok API response payload: {type(e).__name__}") from e

        # Enforce deterministic validation & action boundaries on generated text
        validation = OutputValidator.validate(raw_text, request)
        return validation.repaired_response or OutputValidator.build_fallback(request)


# Canonical alias for Groq provider naming
GroqLLMProvider = GrokLLMProvider
