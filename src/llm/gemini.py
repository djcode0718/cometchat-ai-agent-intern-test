"""Official Gemini API provider implementation for grounded language generation."""

import os
import time
from typing import Optional

from src.core.config import get_settings
from src.llm.base import BaseLLMProvider, LLMGenerationError
from src.llm.models import GeneratedResponse, GroundedGenerationRequest
from src.llm.prompts import SYSTEM_PROMPT, build_user_prompt
from src.llm.validator import OutputValidator


class GeminiLLMProvider(BaseLLMProvider):
    """Primary LLM provider using Google Gemini API."""

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
                settings.gemini_api_key
                or os.getenv("GEMINI_API_KEY")
                or os.getenv("GOOGLE_API_KEY")
            )
        self.model_name = (
            model_name
            or settings.gemini_llm_model
            or os.getenv("GEMINI_LLM_MODEL")
            or os.getenv("GEMINI_MODEL", "models/gemini-flash-latest")
        )
        self.base_url = (
            base_url
            or os.getenv("GEMINI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta")
        ).rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.last_latency_ms: Optional[float] = None

    @property
    def provider_name(self) -> str:
        clean_model = self.model_name.removeprefix("models/")
        return f"gemini-{clean_model}"

    def generate(self, request: GroundedGenerationRequest) -> GeneratedResponse:
        """Generate response via Gemini API. Raises LLMGenerationError on failure."""
        if not self.api_key or not self.api_key.strip():
            raise LLMGenerationError(
                "Gemini API key is not configured. Set GEMINI_API_KEY environment variable."
            )

        import httpx

        prompt = build_user_prompt(request)
        model_endpoint = self.model_name if self.model_name.startswith("models/") else f"models/{self.model_name}"
        url = f"{self.base_url}/{model_endpoint}:generateContent"
        params = {"key": self.api_key}
        headers = {"Content-Type": "application/json"}
        payload = {
            "system_instruction": {
                "parts": [{"text": SYSTEM_PROMPT}]
            },
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": prompt}],
                }
            ],
            "generationConfig": {
                "temperature": 0.0,
            },
        }

        start_time = time.perf_counter()
        try:
            with httpx.Client(timeout=self.timeout_seconds) as client:
                resp = client.post(url, params=params, headers=headers, json=payload)
                self.last_latency_ms = round((time.perf_counter() - start_time) * 1000, 2)

                if resp.status_code == 401 or resp.status_code == 403:
                    raise LLMGenerationError(
                        f"Gemini API authentication failed (HTTP {resp.status_code}). Check GEMINI_API_KEY."
                    )
                if resp.status_code == 429:
                    raise LLMGenerationError("Gemini API rate limit exceeded (HTTP 429).")
                if resp.status_code >= 500:
                    raise LLMGenerationError(
                        f"Gemini API server error (HTTP {resp.status_code})."
                    )
                if resp.status_code != 200:
                    raise LLMGenerationError(
                        f"Gemini API returned unexpected status HTTP {resp.status_code}."
                    )

                data = resp.json()
        except httpx.TimeoutException as e:
            self.last_latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
            raise LLMGenerationError(f"Gemini API request timed out after {self.timeout_seconds}s.") from e
        except httpx.RequestError as e:
            self.last_latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
            raise LLMGenerationError(f"Gemini API network connection error: {type(e).__name__}") from e
        except LLMGenerationError:
            raise
        except Exception as e:
            self.last_latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
            raise LLMGenerationError(f"Gemini API call failed: {type(e).__name__}") from e

        # Extract text content safely from candidates
        try:
            candidates = data.get("candidates", [])
            if not candidates:
                raise LLMGenerationError("Gemini API returned zero candidates.")
            
            content_parts = candidates[0].get("content", {}).get("parts", [])
            if not content_parts or "text" not in content_parts[0]:
                raise LLMGenerationError("Gemini API candidate missing text content.")

            raw_text = content_parts[0]["text"]
        except (KeyError, IndexError, TypeError) as e:
            raise LLMGenerationError(f"Failed to parse Gemini API response payload: {type(e).__name__}") from e

        # Enforce deterministic validation & action boundaries on generated text
        validation = OutputValidator.validate(raw_text, request)
        return validation.repaired_response or OutputValidator.build_fallback(request)
