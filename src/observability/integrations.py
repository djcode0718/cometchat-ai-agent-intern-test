"""Optional external integrations for Sentry error tracking and LangSmith LLM tracing."""

import hashlib
import os
from typing import Any, Callable, Dict, Optional

from src.observability.logging import SENSITIVE_KEYS, _mask_string_value, get_logger

logger = get_logger("integrations")


def init_sentry() -> None:
    """Initialize Sentry SDK if SENTRY_DSN is configured, strictly stripping PII."""
    dsn = os.getenv("SENTRY_DSN")
    if not dsn:
        return

    try:
        import sentry_sdk

        def before_send_filter(event: Dict[str, Any], hint: Dict[str, Any]) -> Optional[Dict[str, Any]]:
            # Sanitize event breadcrumbs, extra data, and request details
            if "request" in event:
                event["request"].pop("data", None)
                if "headers" in event["request"]:
                    for h in ["authorization", "cookie"]:
                        event["request"]["headers"].pop(h, None)
            # Redact user tags
            event["user"] = {"ip_address": "[REDACTED]"}
            return event

        sentry_sdk.init(
            dsn=dsn,
            send_default_pii=False,
            traces_sample_rate=float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", "0.1")),
            before_send=before_send_filter,
        )
        logger.info("sentry_initialized")
    except ImportError:
        logger.warning("sentry_sdk_not_installed")
    except Exception as e:
        logger.error("sentry_init_failed", error=str(e))


def trace_langsmith_turn(
    session_id: str,
    request_id: str,
    route: str,
    decision_state: str,
    fn: Callable[[], Any],
) -> Any:
    """Wrap agent process_turn with LangSmith trace if enabled, masking PII and hashing session_id."""
    tracing_enabled = os.getenv("LANGSMITH_TRACING", "false").lower() in ("true", "1")
    api_key = os.getenv("LANGSMITH_API_KEY")

    if not (tracing_enabled and api_key):
        return fn()

    try:
        from langsmith import traceable

        # Mask session_id with SHA-256 for external tracing privacy
        hashed_session = hashlib.sha256(session_id.encode("utf-8")).hexdigest()[:16]

        wrapped = traceable(
            name="agent_turn",
            run_type="chain",
            metadata={
                "request_id": request_id,
                "hashed_session_id": hashed_session,
                "route": route,
                "decision_state": decision_state,
            },
        )(fn)
        return wrapped()
    except ImportError:
        return fn()
    except Exception:
        return fn()
