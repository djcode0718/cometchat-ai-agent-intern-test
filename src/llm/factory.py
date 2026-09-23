"""Provider factory for constructing configured LLM providers and fallback chains."""

import os
from typing import Optional

from src.core.config import get_settings
from src.llm.base import BaseLLMProvider
from src.llm.fallback import FallbackChainLLMProvider
from src.llm.gemini import GeminiLLMProvider
from src.llm.grok import GrokLLMProvider
from src.llm.mock import MockLLMProvider
from src.llm.provider import FlexibleLLMProvider


def get_llm_provider(
    provider_type: Optional[str] = None,
    gemini_api_key: Optional[str] = None,
    grok_api_key: Optional[str] = None,
) -> BaseLLMProvider:
    """Instantiate and return the configured LLM provider or fallback chain."""
    settings = get_settings()
    ptype = (
        provider_type
        or settings.llm_provider
        or os.getenv("LLM_PROVIDER", "gemini")
    ).lower()

    if ptype in ("mock", "test", "offline"):
        return MockLLMProvider()

    if ptype in ("groq", "grok"):
        return GrokLLMProvider(api_key=grok_api_key)

    if ptype in ("flexible", "openai"):
        return FlexibleLLMProvider(api_key=gemini_api_key)

    # Default: Primary Gemini with Fallback Groq
    gemini = GeminiLLMProvider(api_key=gemini_api_key)
    groq = GrokLLMProvider(api_key=grok_api_key)

    return FallbackChainLLMProvider(
        primary_provider=gemini,
        fallback_provider=groq,
        deterministic_fallback_on_error=False,
    )
