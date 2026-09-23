"""Common abstract interface for all retrieval strategies."""

from abc import ABC, abstractmethod
from typing import List, Optional

from src.retrieval.models import RetrievalResult


class BaseRetriever(ABC):
    """Abstract base class for all retrieval backends."""

    @property
    @abstractmethod
    def strategy_name(self) -> str:
        """Name of the retrieval strategy (bm25, dense, hybrid, etc.)."""
        pass

    @abstractmethod
    def retrieve(self, query: str, top_k: int = 5) -> List[RetrievalResult]:
        """Retrieve and rank the top_k most relevant chunks for a given query."""
        pass
