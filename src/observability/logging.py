"""Structured logging configuration with PII redaction and contextvars support."""

import logging
import os
import re
import sys
from typing import Any, Dict, MutableMapping

import structlog

# Sensitive key names that must be redacted
SENSITIVE_KEYS = {
    "email",
    "customer_email",
    "address",
    "customer_address",
    "name",
    "customer_name",
    "warehouse_note",
    "warehouse_notes",
    "internal_notes",
    "risk_score",
    "fraud_score",
    "api_key",
    "authorization",
    "token",
    "secret",
    "password",
}

# Regex for masking email patterns: redact username and domain body, e.g. j***@d***.com
EMAIL_PATTERN = re.compile(
    r"\b([A-Za-z0-9._%+-])[A-Za-z0-9._%+-]*@([A-Za-z0-9.-]+\.[A-Za-z]{2,})\b",
    re.IGNORECASE,
)

# Regex for masking API keys: sk-*, gsk_*, Bearer tokens, hex/base64 long strings
API_KEY_PATTERN = re.compile(
    r"\b(sk-[a-zA-Z0-9_\-]{8,}|gsk_[a-zA-Z0-9_\-]{8,}|xai-[a-zA-Z0-9_\-]{8,}|AIza[0-9A-Za-z\-_]{20,})\b"
)


def _mask_string_value(val: str) -> str:
    """Mask email-shaped and API-key-shaped tokens inside a string."""
    # Mask API keys first
    masked = API_KEY_PATTERN.sub(r"[REDACTED_KEY]", val)
    # Mask emails: preserve first char of username
    masked = EMAIL_PATTERN.sub(r"\1***@***.***", masked)
    return masked


def pii_redactor_processor(
    logger: Any, method_name: str, event_dict: MutableMapping[str, Any]
) -> MutableMapping[str, Any]:
    """Processor that redacts sensitive keys and masks sensitive patterns in values."""
    return _redact_data(event_dict)


def _redact_data(data: Any) -> Any:
    """Recursively scrub sensitive keys and mask string patterns."""
    if isinstance(data, dict):
        cleaned: Dict[str, Any] = {}
        for k, v in data.items():
            if str(k).lower() in SENSITIVE_KEYS:
                cleaned[k] = "[REDACTED]"
            else:
                cleaned[k] = _redact_data(v)
        return cleaned
    elif isinstance(data, list):
        return [_redact_data(item) for item in data]
    elif isinstance(data, tuple):
        return tuple(_redact_data(item) for item in data)
    elif isinstance(data, str):
        return _mask_string_value(data)
    return data


def configure_logging(app_env: str = "development", log_level: str = "INFO") -> None:
    """Configure structlog once globally based on application environment."""
    level = getattr(logging, log_level.upper(), logging.INFO)

    shared_processors = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        pii_redactor_processor,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    if app_env.lower() in ("production", "prod"):
        # JSON renderer for production
        renderer = structlog.processors.JSONRenderer()
    else:
        # Development / test: human-readable colored console output
        renderer = structlog.dev.ConsoleRenderer(colors=sys.stderr.isatty())

    structlog.configure(
        processors=shared_processors + [structlog.stdlib.ProcessorFormatter.wrap_for_formatter],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(level)

    # Silence overly verbose external loggers
    for ext_logger in ("uvicorn.access", "urllib3", "httpx", "httpcore", "sentence_transformers"):
        logging.getLogger(ext_logger).setLevel(logging.WARNING)


def get_logger(name: str = "aster_row") -> structlog.stdlib.BoundLogger:
    """Retrieve a structured logger instance."""
    return structlog.get_logger(name)
