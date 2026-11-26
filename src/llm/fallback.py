"""Fallback chain provider orchestrating multi-tier failover across LLM providers -> Deterministic Fallback."""

import time
from typing import Any, Dict, List, Optional

from src.llm.base import BaseLLMProvider, LLMGenerationError
from src.llm.models import GeneratedResponse, GroundedGenerationRequest
from src.llm.validator import OutputValidator


class FallbackChainLLMProvider(BaseLLMProvider):
    """Orchestrates structured fallback across an ordered list of LLM providers."""

    def __init__(
        self,
        primary_provider: Optional[BaseLLMProvider] = None,
        fallback_provider: Optional[BaseLLMProvider] = None,
        providers: Optional[List[BaseLLMProvider]] = None,
        deterministic_fallback_on_error: bool = False,
    ) -> None:
        if providers is not None:
            self.providers = list(providers)
        else:
            self.providers = []
            if primary_provider is not None:
                self.providers.append(primary_provider)
            if fallback_provider is not None:
                self.providers.append(fallback_provider)

        # Retain backward-compatible attributes
        self.primary_provider = self.providers[0] if self.providers else None
        self.fallback_provider = self.providers[1] if len(self.providers) > 1 else None
        self.deterministic_fallback_on_error = deterministic_fallback_on_error
        self.last_telemetry: Dict[str, Any] = {}

    @property
    def provider_name(self) -> str:
        names = [p.provider_name for p in self.providers]
        return f"chain({' -> '.join(names)})"

    def generate(self, request: GroundedGenerationRequest) -> GeneratedResponse:
        """Generate response attempting providers in order, falling back to deterministic fallback."""
        start_time = time.perf_counter()
        primary_name = self.providers[0].provider_name if self.providers else "none"
        secondary_name = self.providers[1].provider_name if len(self.providers) > 1 else None

        telemetry: Dict[str, Any] = {
            "primary_provider": primary_name,
            "primary_success": False,
            "primary_error": None,
            "fallback_used": False,
            "fallback_provider": secondary_name,
            "fallback_success": None,
            "fallback_error": None,
            "final_provider": None,
            "latency_ms": 0.0,
            "attempts": [],
        }

        # Iterate through providers in priority order
        for idx, provider in enumerate(self.providers):
            t0 = time.perf_counter()
            attempt: Dict[str, Any] = {
                "tier": idx + 1,
                "provider": provider.provider_name,
                "success": False,
                "error": None,
                "latency_ms": 0.0,
            }

            try:
                response = provider.generate(request)
                attempt["success"] = True
                attempt["latency_ms"] = round((time.perf_counter() - t0) * 1000, 2)
                telemetry["attempts"].append(attempt)

                if idx == 0:
                    telemetry["primary_success"] = True
                else:
                    telemetry["fallback_used"] = True
                    telemetry["fallback_success"] = True

                telemetry["final_provider"] = provider.provider_name
                telemetry["latency_ms"] = round((time.perf_counter() - start_time) * 1000, 2)
                self.last_telemetry = telemetry
                return response
            except Exception as exc:
                attempt["error"] = str(exc)
                attempt["latency_ms"] = round((time.perf_counter() - t0) * 1000, 2)
                telemetry["attempts"].append(attempt)

                if idx == 0:
                    telemetry["primary_success"] = False
                    telemetry["primary_error"] = str(exc)
                else:
                    telemetry["fallback_used"] = True
                    telemetry["fallback_success"] = False
                    telemetry["fallback_error"] = str(exc)

        # All providers failed
        telemetry["fallback_used"] = True
        telemetry["final_provider"] = "deterministic_fallback"
        telemetry["latency_ms"] = round((time.perf_counter() - start_time) * 1000, 2)
        self.last_telemetry = telemetry

        if self.deterministic_fallback_on_error:
            failed_reasons = [f"{a.get('provider')}: {a.get('error')}" for a in telemetry["attempts"]]
            reason = f"All providers in chain failed: {failed_reasons}"
            return OutputValidator.build_fallback(request, reason=reason)

        # Raise LLMGenerationError so calling orchestrator captures the error and applies OutputValidator.build_fallback
        combined_err = f"Primary provider failed ({telemetry['primary_error']})"
        if len(self.providers) > 1:
            combined_err += f"; Fallback provider failed ({telemetry['fallback_error']})"
        raise LLMGenerationError(combined_err)
