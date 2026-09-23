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
    groq_api_key: Optional[str] = None,
    primary_model: Optional[str] = None,
    fallback_model: Optional[str] = None,
    gemini_api_key: Optional[str] = None,
    grok_api_key: Optional[str] = None,
) -> BaseLLMProvider:
    """Instantiate and return the configured LLM provider or fallback chain."""
    settings = get_settings()
    ptype = (
        provider_type
        or settings.llm_provider
        or os.getenv("LLM_PROVIDER", "groq")
    ).lower()

    if ptype in ("mock", "test", "offline"):
        return MockLLMProvider()

    if ptype in ("single_groq", "single_grok"):
        return GrokLLMProvider(
            api_key=groq_api_key or grok_api_key,
            model_name=primary_model,
        )

    if ptype == "gemini":
        # Kept dormant/explicit for compatibility
        return GeminiLLMProvider(api_key=gemini_api_key)

    if ptype in ("flexible", "openai"):
        return FlexibleLLMProvider(api_key=groq_api_key or gemini_api_key)

    # Default Active Chain: Primary Groq (e.g. openai/gpt-oss-120b) -> Fallback Groq (e.g. openai/gpt-oss-20b) -> Deterministic
    key = groq_api_key if groq_api_key is not None else grok_api_key
    primary_groq = GrokLLMProvider(
        api_key=key,
        model_name=primary_model or settings.groq_llm_model,
    )
    fallback_groq = GrokLLMProvider(
        api_key=key,
        model_name=fallback_model or settings.groq_fallback_model,
    )

    return FallbackChainLLMProvider(
        primary_provider=primary_groq,
        fallback_provider=fallback_groq,
        deterministic_fallback_on_error=False,
    )
