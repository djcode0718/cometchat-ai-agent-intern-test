"""Configuration management for Aster & Row support agent."""

import os
from functools import lru_cache
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from pydantic import BaseModel, Field

# Automatically load .env if present
load_dotenv()

# Find project root based on this file's location (src/core/config.py -> ../..)
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


class Settings(BaseModel):
    """Application settings with environment variable support."""

    app_env: str = Field(
        default_factory=lambda: os.getenv("APP_ENV", "development"),
        description="Application environment (development, test, production)",
    )
    log_level: str = Field(
        default_factory=lambda: os.getenv("LOG_LEVEL", "INFO"),
        description="Logging level",
    )

    # Base Paths
    project_root: Path = Field(default=PROJECT_ROOT)
    knowledge_base_path: Path = Field(
        default_factory=lambda: (
            PROJECT_ROOT / os.getenv("KNOWLEDGE_BASE_DIR", "knowledge-base")
        ).resolve()
    )
    data_path: Path = Field(
        default_factory=lambda: (
            PROJECT_ROOT / os.getenv("DATA_DIR", "data")
        ).resolve()
    )
    orders_file_path: Path = Field(
        default_factory=lambda: (
            PROJECT_ROOT / os.getenv("ORDERS_FILE", "data/orders.json")
        ).resolve()
    )
    evaluation_path: Path = Field(
        default_factory=lambda: (
            PROJECT_ROOT / os.getenv("EVALUATION_DIR", "evaluation")
        ).resolve()
    )

    # Retrieval Configuration Placeholders (for Phase 2+)
    retrieval_top_k: int = Field(
        default_factory=lambda: int(os.getenv("RETRIEVAL_TOP_K", "5"))
    )
    bm25_k1: float = Field(
        default_factory=lambda: float(os.getenv("BM25_K1", "1.5"))
    )
    bm25_b: float = Field(
        default_factory=lambda: float(os.getenv("BM25_B", "0.75"))
    )
    rrf_k: int = Field(
        default_factory=lambda: int(os.getenv("RRF_K", "60"))
    )

    model_config = {"arbitrary_types_allowed": True}


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached application settings instance."""
    return Settings()
