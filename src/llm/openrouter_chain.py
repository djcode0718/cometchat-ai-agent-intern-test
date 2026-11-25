"""Robust multi-model fallback chain orchestrating Primary -> Secondary -> Tertiary OpenRouter models -> Groq -> Deterministic fallback."""

import time
from typing import Any, Dict, List, Optional

from src.core.config import get_settings
from src.llm.base import BaseLLMProvider, LLMGenerationError
from src.llm.grok import GrokLLMProvider
from src.llm.models import GeneratedResponse, GroundedGenerationRequest
from src.llm.openrouter import OpenRouterLLMProvider
from src.llm.validator import OutputValidator


class OpenRouterFallbackChainProvider(BaseLLMProvider):
    """Orchestrates an ordered multi-model fallback chain across OpenRouter, Groq, and Deterministic fallback."""

    # History of fallback transitions across the session
    session_fallback_history: List[Dict[str, Any]] = []

    def __init__(
        self,
        primary_model: Optional[str] = None,
        secondary_model: Optional[str] = None,
        tertiary_model: Optional[str] = None,
        openrouter_api_key: Optional[str] = None,
        groq_api_key: Optional[str] = None,
        enable_cache: bool = True,
        deterministic_fallback_on_error: bool = True,
    ) -> None:
        settings = get_settings()
        self.primary_model = primary_model or settings.openrouter_primary_model
        self.secondary_model = secondary_model or settings.openrouter_secondary_model
        self.tertiary_model = tertiary_model or settings.openrouter_tertiary_model
        self.deterministic_fallback_on_error = deterministic_fallback_on_error

        # 1. OpenRouter Primary
        self.primary_provider = OpenRouterLLMProvider(
            api_key=openrouter_api_key,
            model_name=self.primary_model,
            enable_cache=enable_cache,
        )

        # 2. OpenRouter Secondary
        self.secondary_provider = OpenRouterLLMProvider(
            api_key=openrouter_api_key,
            model_name=self.secondary_model,
            enable_cache=enable_cache,
        )

        # 3. OpenRouter Tertiary
        self.tertiary_provider = OpenRouterLLMProvider(
            api_key=openrouter_api_key,
            model_name=self.tertiary_model,
            enable_cache=enable_cache,
        )

        # 4. Optional Groq provider
        self.groq_provider: Optional[BaseLLMProvider] = None
        groq_key = groq_api_key or settings.groq_api_key
        if groq_key and groq_key.strip():
            self.groq_provider = GrokLLMProvider(api_key=groq_key)

        self.last_telemetry: Dict[str, Any] = {}

    @property
    def provider_name(self) -> str:
        groq_str = f" -> {self.groq_provider.provider_name}" if self.groq_provider else ""
        return (
            f"openrouter-chain({self.primary_model} -> {self.secondary_model} "
            f"-> {self.tertiary_model}{groq_str} -> deterministic)"
        )

    def generate(self, request: GroundedGenerationRequest) -> GeneratedResponse:
        """Generate response attempting primary model first, cascading through fallbacks upon failure."""
        start_time = time.perf_counter()
        chain_attempts: List[Dict[str, Any]] = []
        
        # Build ordered provider list
        providers = [
            ("openrouter_primary", self.primary_provider, self.primary_model),
            ("openrouter_secondary", self.secondary_provider, self.secondary_model),
            ("openrouter_tertiary", self.tertiary_provider, self.tertiary_model),
        ]
        if self.groq_provider:
            providers.append(("groq_backup", self.groq_provider, getattr(self.groq_provider, "model_name", "groq")))

        for step_idx, (tier_name, provider, model_id) in enumerate(providers, 1):
            step_start = time.perf_counter()
            try:
                response = provider.generate(request)
                step_latency_ms = round((time.perf_counter() - step_start) * 1000, 2)
                
                attempt_record = {
                    "tier": tier_name,
                    "provider": provider.provider_name,
                    "model_id": model_id,
                    "attempt": step_idx,
                    "status": "success",
                    "error": None,
                    "latency_ms": step_latency_ms,
                    "cost_usd": provider.last_telemetry.get("cost_usd", 0.0) if hasattr(provider, "last_telemetry") else 0.0,
                    "cached": provider.last_telemetry.get("cached", False) if hasattr(provider, "last_telemetry") else False,
                }
                chain_attempts.append(attempt_record)
                OpenRouterFallbackChainProvider.session_fallback_history.append(attempt_record)

                self.last_telemetry = {
                    "final_tier": tier_name,
                    "final_model": model_id,
                    "final_provider": provider.provider_name,
                    "total_latency_ms": round((time.perf_counter() - start_time) * 1000, 2),
                    "fallback_occurred": step_idx > 1,
                    "attempts_count": step_idx,
                    "attempts": chain_attempts,
                    "is_fallback": False,
                }
                return response

            except Exception as exc:
                step_latency_ms = round((time.perf_counter() - step_start) * 1000, 2)
                error_msg = f"{type(exc).__name__}: {str(exc)}"
                attempt_record = {
                    "tier": tier_name,
                    "provider": provider.provider_name,
                    "model_id": model_id,
                    "attempt": step_idx,
                    "status": "failure",
                    "error": error_msg,
                    "latency_ms": step_latency_ms,
                    "cost_usd": 0.0,
                    "cached": False,
                }
                chain_attempts.append(attempt_record)
                OpenRouterFallbackChainProvider.session_fallback_history.append(attempt_record)

        # 5. All live LLM providers failed -> Deterministic evidence-based fallback
        final_latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
        fallback_record = {
            "tier": "deterministic_fallback",
            "provider": "OutputValidator.build_fallback",
            "model_id": "deterministic_evidence_builder",
            "attempt": len(providers) + 1,
            "status": "success",
            "error": "All upstream LLM providers exhausted or unavailable.",
            "latency_ms": 0.1,
            "cost_usd": 0.0,
            "cached": False,
        }
        chain_attempts.append(fallback_record)
        OpenRouterFallbackChainProvider.session_fallback_history.append(fallback_record)

        self.last_telemetry = {
            "final_tier": "deterministic_fallback",
            "final_model": "deterministic_evidence_builder",
            "final_provider": "deterministic_fallback",
            "total_latency_ms": final_latency_ms,
            "fallback_occurred": True,
            "attempts_count": len(chain_attempts),
            "attempts": chain_attempts,
            "is_fallback": True,
        }

        if self.deterministic_fallback_on_error:
            reason = f"All {len(providers)} live LLM providers failed. Fallen back to deterministic evidence response."
            return OutputValidator.build_fallback(request, reason=reason)

        errors_summary = "; ".join([f"{a['tier']} failed ({a['error']})" for a in chain_attempts if a['status'] == 'failure'])
        raise LLMGenerationError(f"All providers failed in fallback chain: {errors_summary}")
