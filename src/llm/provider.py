"""Flexible LLM provider supporting standard API providers with automatic mock fallback."""

import os
from typing import Optional

from src.llm.base import BaseLLMProvider
from src.llm.mock import MockLLMProvider
from src.llm.models import GeneratedResponse, GroundedGenerationRequest
from src.llm.prompts import SYSTEM_PROMPT, build_user_prompt
from src.llm.validator import OutputValidator


class FlexibleLLMProvider(BaseLLMProvider):
    """Production-ready LLM provider interface supporting API calls with safe offline mock fallback."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model_name: Optional[str] = None,
        base_url: Optional[str] = None,
        fallback_provider: Optional[BaseLLMProvider] = None,
    ) -> None:
        self.api_key = api_key or os.getenv("OPENAI_API_KEY") or os.getenv("LLM_API_KEY") or os.getenv("GEMINI_API_KEY")
        self.model_name = model_name or os.getenv("LLM_MODEL_NAME", "gpt-4o-mini")
        self.base_url = base_url or os.getenv("LLM_BASE_URL", "https://api.openai.com/v1")
        self.mock_fallback = fallback_provider or MockLLMProvider()

    @property
    def provider_name(self) -> str:
        if self.api_key:
            return f"api-{self.model_name}"
        return "mock"

    def generate(self, request: GroundedGenerationRequest) -> GeneratedResponse:
        """Generate response via API if credentials exist, otherwise utilize deterministic mock."""
        if not self.api_key:
            return self.mock_fallback.generate(request)

        # Attempt API generation
        try:
            import httpx

            prompt = build_user_prompt(request)
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

            url = f"{self.base_url.rstrip('/')}/chat/completions"
            with httpx.Client(timeout=15.0) as client:
                resp = client.post(url, headers=headers, json=payload)
                resp.raise_for_status()
                data = resp.json()
                raw_text = data["choices"][0]["message"]["content"]

            validation = OutputValidator.validate(raw_text, request)
            return validation.repaired_response or OutputValidator.build_fallback(request)

        except Exception as e:
            # On any network or API failure, fallback gracefully to deterministic grounded response
            return self.mock_fallback.generate(request)
