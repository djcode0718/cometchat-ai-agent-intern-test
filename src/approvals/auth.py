"""Reviewer authentication and authorization using constant-time key comparison."""

import hmac
import os
from typing import Dict, Optional
from fastapi import Header, HTTPException, Request, status

from src.observability.logging import get_logger

logger = get_logger("approvals.auth")


# Reviewer role mappings: identity -> role (e.g. 'admin', 'reviewer', 'readonly')
_reviewer_roles: Dict[str, str] = {}


def parse_reviewer_keys(raw_keys: Optional[str] = None) -> Dict[str, str]:
    """Parse REVIEWER_KEYS environment variable formatted as 'name:key[:role],name2:key2[:role]'."""
    global _reviewer_roles
    raw = raw_keys if raw_keys is not None else os.getenv("REVIEWER_KEYS", "admin:secret_admin_key_123:admin,reviewer1:rev_key_abc:reviewer,auditor_readonly:audit_key_ro:readonly")
    keys: Dict[str, str] = {}
    roles: Dict[str, str] = {}
    for entry in raw.split(","):
        entry = entry.strip()
        if ":" in entry:
            parts = entry.split(":")
            if len(parts) >= 3:
                name, key, role = parts[0].strip(), parts[1].strip(), parts[2].strip()
            else:
                name, key = parts[0].strip(), parts[1].strip()
                role = "admin" if name == "admin" else "reviewer"
            keys[key] = name
            roles[name] = role
    _reviewer_roles = roles
    return keys


def get_reviewer_role(reviewer_id: str) -> str:
    """Return the role associated with a reviewer identity."""
    if not _reviewer_roles:
        parse_reviewer_keys()
    return _reviewer_roles.get(reviewer_id, "reviewer")


def authorize_reviewer_action(reviewer_id: str, action: str = "approve") -> None:
    """Enforce Role-Based Access Control (RBAC) on reviewer actions.
    
    Roles:
      - 'admin': Full access (read, approve, reject, configure)
      - 'reviewer': Standard HITL access (read, approve, reject)
      - 'readonly' / 'auditor': Read-only audit access (read only; approve/reject forbidden)
    """
    role = get_reviewer_role(reviewer_id)
    if action in ("approve", "reject") and role in ("readonly", "auditor"):
        logger.warning(
            "reviewer_authorization_denied",
            reviewer_id=reviewer_id,
            role=role,
            attempted_action=action,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Forbidden: Reviewer '{reviewer_id}' with role '{role}' is not authorized to {action} actions.",
        )


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
