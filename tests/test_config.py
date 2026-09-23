"""Tests for application configuration."""

import os
from pathlib import Path
from unittest.mock import patch

from src.core.config import Settings, get_settings


def test_default_settings():
    settings = get_settings()
    assert settings.app_env in ["development", "test", "production"]
    assert settings.knowledge_base_path.exists()
    assert settings.knowledge_base_path.is_dir()
    assert settings.data_path.exists()
    assert settings.orders_file_path.exists()


def test_settings_env_override():
    with patch.dict(os.environ, {"APP_ENV": "test", "LOG_LEVEL": "DEBUG"}):
        custom_settings = Settings()
        assert custom_settings.app_env == "test"
        assert custom_settings.log_level == "DEBUG"
