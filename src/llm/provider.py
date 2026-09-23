"""Flexible LLM provider supporting standard API providers without silent mock fallback."""

import os
from typing import Optional

from src.llm.base import BaseLLMProvider, LLMGenerationError
from src.llm.models import GeneratedResponse, GroundedGenerationRequest
from src.llm.prompts import SYSTEM_PROMPT, build_user_prompt
from src.llm.validator import OutputValidator


class FlexibleLLMProvider(BaseLLMProvider):
    """Production-ready LLM provider interface supporting external API models."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model_name: Optional[str] = None,
        base_url: Optional[str] = None,
    ) -> None:
        if api_key is not None:
            self.api_key = api_key
        else:
            self.api_key = os.getenv("OPENAI_API_KEY") or os.getenv("LLM_API_KEY") or os.getenv("GEMINI_API_KEY")
        self.model_name = model_name or os.getenv("LLM_MODEL_NAME", "gpt-4o-mini")
        self.base_url = base_url or os.getenv("LLM_BASE_URL", "https://api.openai.com/v1")

    @property
    def provider_name(self) -> str:
        return f"api-{self.model_name}"

    def generate(self, request: GroundedGenerationRequest) -> GeneratedResponse:
        """Generate response via API. Raises LLMGenerationError on missing credentials or failure."""
        if not self.api_key:
            raise LLMGenerationError(
                f"No API key configured for provider '{self.provider_name}'. Set OPENAI_API_KEY, LLM_API_KEY, or GEMINI_API_KEY."
            )

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
            raise LLMGenerationError(f"LLM API generation failed: {e}") from e
