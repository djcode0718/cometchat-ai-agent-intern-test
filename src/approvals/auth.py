"""Reviewer authentication and authorization using constant-time key comparison."""

import hmac
import os
from typing import Dict, Optional
from fastapi import Header, HTTPException, Request, status

from src.observability.logging import get_logger

logger = get_logger("approvals.auth")


def parse_reviewer_keys(raw_keys: Optional[str] = None) -> Dict[str, str]:
    """Parse REVIEWER_KEYS environment variable formatted as 'name:key,name2:key2'."""
    raw = raw_keys if raw_keys is not None else os.getenv("REVIEWER_KEYS", "admin:secret_admin_key_123,reviewer1:rev_key_abc")
    keys: Dict[str, str] = {}
    for entry in raw.split(","):
        entry = entry.strip()
        if ":" in entry:
            name, key = entry.split(":", 1)
            keys[key.strip()] = name.strip()
    return keys


def authenticate_reviewer(
    x_reviewer_key: Optional[str] = Header(None, alias="X-Reviewer-Key"),
) -> str:
    """Validate reviewer API key using constant-time comparison.

    Returns the authenticated reviewer's identity string.
    Raises HTTPException 401 if missing or invalid.
    """
    if not x_reviewer_key:
        logger.warning("reviewer_auth_failed", reason="missing_header")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing required X-Reviewer-Key header.",
        )

    valid_keys = parse_reviewer_keys()
    
    # Constant-time lookup across configured keys
    matched_identity: Optional[str] = None
    for configured_key, identity in valid_keys.items():
        if hmac.compare_digest(configured_key.encode("utf-8"), x_reviewer_key.encode("utf-8")):
            matched_identity = identity
            break

    if not matched_identity:
        logger.warning("reviewer_auth_failed", reason="invalid_key")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid reviewer key.",
        )

    return matched_identity
