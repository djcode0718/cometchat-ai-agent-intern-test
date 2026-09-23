"""Local sentence-transformer embedding service."""

from typing import List, Optional, Union
import numpy as np

try:
    from sentence_transformers import SentenceTransformer
    SENTENCE_TRANSFORMERS_AVAILABLE = True
except ImportError:
    SENTENCE_TRANSFORMERS_AVAILABLE = False


class LocalEmbeddingService:
    """Generates normalized vector embeddings using local sentence-transformer models."""

    def __init__(self, model_name: str = "all-MiniLM-L6-v2") -> None:
        self.model_name = model_name
        self._model: Optional["SentenceTransformer"] = None

    def _ensure_model(self) -> "SentenceTransformer":
        if self._model is None:
            if not SENTENCE_TRANSFORMERS_AVAILABLE:
                raise ImportError(
                    "sentence-transformers is required for dense retrieval. Please install it."
                )
            self._model = SentenceTransformer(self.model_name)
        return self._model

    def encode(self, texts: List[str]) -> np.ndarray:
        """Encode a list of text strings into normalized 2D numpy embedding vectors."""
        if not texts:
            return np.empty((0, 384), dtype=np.float32)

        model = self._ensure_model()
        # normalize_embeddings=True ensures cosine similarity is equivalent to dot product
        embeddings = model.encode(
            texts,
            normalize_embeddings=True,
            show_progress_bar=False,
            convert_to_numpy=True,
        )
        return np.asarray(embeddings, dtype=np.float32)

    def encode_query(self, query: str) -> np.ndarray:
        """Encode a single query string into a normalized 1D vector."""
        if not query.strip():
            return np.zeros(384, dtype=np.float32)
        vectors = self.encode([query])
        return vectors[0]
