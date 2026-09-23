"""Fallback chain provider orchestrating Primary (Gemini) -> Fallback (Grok) -> Deterministic Fallback."""

import time
from typing import Any, Dict, Optional

from src.llm.base import BaseLLMProvider, LLMGenerationError
from src.llm.models import GeneratedResponse, GroundedGenerationRequest
from src.llm.validator import OutputValidator


class FallbackChainLLMProvider(BaseLLMProvider):
    """Orchestrates structured fallback across multiple LLM providers."""

    def __init__(
        self,
        primary_provider: BaseLLMProvider,
        fallback_provider: Optional[BaseLLMProvider] = None,
        deterministic_fallback_on_error: bool = False,
    ) -> None:
        self.primary_provider = primary_provider
        self.fallback_provider = fallback_provider
        self.deterministic_fallback_on_error = deterministic_fallback_on_error
        self.last_telemetry: Dict[str, Any] = {}

    @property
    def provider_name(self) -> str:
        fallback_name = self.fallback_provider.provider_name if self.fallback_provider else "none"
        return f"chain({self.primary_provider.provider_name} -> {fallback_name})"

    def generate(self, request: GroundedGenerationRequest) -> GeneratedResponse:
        """Generate response attempting primary first, falling back to secondary, and then deterministic fallback."""
        start_time = time.perf_counter()
        telemetry: Dict[str, Any] = {
            "primary_provider": self.primary_provider.provider_name,
            "primary_success": False,
            "primary_error": None,
            "fallback_used": False,
            "fallback_provider": self.fallback_provider.provider_name if self.fallback_provider else None,
            "fallback_success": None,
            "fallback_error": None,
            "final_provider": None,
            "latency_ms": 0.0,
        }

        # 1. Attempt Primary Provider (Gemini)
        try:
            response = self.primary_provider.generate(request)
            telemetry["primary_success"] = True
            telemetry["final_provider"] = self.primary_provider.provider_name
            telemetry["latency_ms"] = round((time.perf_counter() - start_time) * 1000, 2)
            self.last_telemetry = telemetry
            return response
        except Exception as primary_exc:
            telemetry["primary_error"] = str(primary_exc)
            telemetry["primary_success"] = False

        # 2. Attempt Secondary/Fallback Provider (Grok) if available
        if self.fallback_provider is not None:
            telemetry["fallback_used"] = True
            try:
                response = self.fallback_provider.generate(request)
                telemetry["fallback_success"] = True
                telemetry["final_provider"] = self.fallback_provider.provider_name
                telemetry["latency_ms"] = round((time.perf_counter() - start_time) * 1000, 2)
                self.last_telemetry = telemetry
                return response
            except Exception as fallback_exc:
                telemetry["fallback_success"] = False
                telemetry["fallback_error"] = str(fallback_exc)

        # 3. Final fallback handling
        telemetry["final_provider"] = "deterministic_fallback"
        telemetry["latency_ms"] = round((time.perf_counter() - start_time) * 1000, 2)
        self.last_telemetry = telemetry

        if self.deterministic_fallback_on_error:
            reason = (
                f"Primary provider '{self.primary_provider.provider_name}' and fallback "
                f"'{self.fallback_provider.provider_name if self.fallback_provider else 'none'}' failed."
            )
            return OutputValidator.build_fallback(request, reason=reason)

        # Raise LLMGenerationError so calling orchestrator captures the error and applies OutputValidator.build_fallback
        combined_err = f"Primary provider failed ({telemetry['primary_error']})"
        if self.fallback_provider:
            combined_err += f"; Fallback provider failed ({telemetry['fallback_error']})"
        raise LLMGenerationError(combined_err)
