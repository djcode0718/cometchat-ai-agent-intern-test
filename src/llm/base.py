"""Abstract base interface for LLM providers."""

from abc import ABC, abstractmethod
from src.llm.models import GeneratedResponse, GroundedGenerationRequest


class LLMGenerationError(Exception):
    """Raised when an LLM provider fails to generate a response."""
    pass


class BaseLLMProvider(ABC):
    """Abstract interface for all language model providers."""

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Name of the provider implementation."""
        pass

    @abstractmethod
    def generate(self, request: GroundedGenerationRequest) -> GeneratedResponse:
        """Generate a validated natural-language customer response for the request."""
        pass
