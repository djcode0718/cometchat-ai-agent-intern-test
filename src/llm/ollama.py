"""Local Ollama LLM provider implementation for complete offline inference."""

import json
import os
import time
from typing import Any, Dict, Optional

import httpx

from src.core.config import get_settings
from src.llm.base import BaseLLMProvider, LLMGenerationError
from src.llm.models import GeneratedResponse, GroundedGenerationRequest
from src.llm.prompts import SYSTEM_PROMPT, build_user_prompt
from src.llm.validator import OutputValidator
from src.observability.logging import get_logger

logger = get_logger("llm.ollama")


class OllamaLLMProvider(BaseLLMProvider):
    """Local offline LLM provider running on Ollama (e.g. llama3.1:8b)."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        model_name: Optional[str] = None,
        timeout_seconds: Optional[float] = None,
        temperature: float = 0.0,
        max_tokens: int = 512,
    ) -> None:
        settings = get_settings()
        self.base_url = (
            base_url
            or getattr(settings, "ollama_base_url", None)
            or os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        ).rstrip("/")
        self.model_name = (
            model_name
            or getattr(settings, "ollama_model", None)
            or os.getenv("OLLAMA_MODEL", "llama3.1:8b")
        )
        self.timeout_seconds = (
            timeout_seconds
            if timeout_seconds is not None
            else float(os.getenv("OLLAMA_TIMEOUT_SECONDS", "60.0"))
        )
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.last_telemetry: Dict[str, Any] = {}

    @property
    def provider_name(self) -> str:
        return f"ollama_{self.model_name}"

    def generate(self, request: GroundedGenerationRequest) -> GeneratedResponse:
        """Generate response via local Ollama instance and validate."""
        user_prompt = build_user_prompt(request)
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ]

        endpoint = f"{self.base_url}/api/chat"
        payload = {
            "model": self.model_name,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": self.temperature,
                "num_predict": self.max_tokens,
            },
        }

        start_time = time.perf_counter()
        raw_text = ""
        prompt_tokens = 0
        completion_tokens = 0
        eval_count = 0
        eval_duration_ns = 0

        try:
            with httpx.Client(timeout=self.timeout_seconds) as client:
                resp = client.post(
                    endpoint,
                    json=payload,
                    headers={"Content-Type": "application/json"},
                )

            if resp.status_code != 200:
                raise LLMGenerationError(
                    f"Ollama returned HTTP {resp.status_code}: {resp.text}"
                )

            data = resp.json()
            message_obj = data.get("message", {})
            raw_text = message_obj.get("content", "").strip()
            prompt_tokens = data.get("prompt_eval_count", 0)
            eval_count = data.get("eval_count", 0)
            eval_duration_ns = data.get("eval_duration", 0)
            completion_tokens = eval_count

        except httpx.ConnectError as ce:
            logger.error("ollama_connection_failed", error=str(ce), base_url=self.base_url)
            raise LLMGenerationError(f"Cannot connect to local Ollama at {self.base_url}. Ensure Ollama is running: {ce}") from ce
        except Exception as exc:
            logger.error("ollama_generation_failed", error=str(exc))
            raise LLMGenerationError(f"Ollama generation failed: {exc}") from exc

        elapsed_ms = (time.perf_counter() - start_time) * 1000.0
        self.last_telemetry = {
            "provider": self.provider_name,
            "model": self.model_name,
            "latency_ms": round(elapsed_ms, 2),
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
            "eval_count": eval_count,
            "eval_duration_ns": eval_duration_ns,
            "eval_duration_ms": round(eval_duration_ns / 1_000_000.0, 2) if eval_duration_ns else 0.0,
            "offline": True,
        }

        # Validate groundedness, citations, PII and boundaries
        val_result = OutputValidator.validate(raw_text, request)
        if val_result.is_valid and val_result.repaired_response is not None:
            return val_result.repaired_response

        # Fallback if invalid
        fallback = OutputValidator.build_fallback(
            request,
            reason=f"Output validation failed: {'; '.join(val_result.violations)}",
        )
        return fallback
