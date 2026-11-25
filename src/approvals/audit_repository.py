"""Append-only, strictly immutable audit repository.

Invariants:
- Only record() and list() / get() are provided.
- NO update, delete, or clear methods exist.
"""

from typing import List, Optional
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.approvals.models import AuditEventModel


class AuditRepository:
    """Append-only audit event repository."""

    def __init__(self, session_factory) -> None:
        self._session_factory = session_factory

    def record(
        self,
        order_id: str,
        action: str,
        to_state: str,
        decided_by: str,
        proposal_id: Optional[str] = None,
        from_state: Optional[str] = None,
        reason: Optional[str] = None,
        request_id: Optional[str] = None,
        timestamp=None,
    ) -> AuditEventModel:
        """Append an immutable audit event."""
        with self._session_factory() as session:
            event = AuditEventModel(
                order_id=order_id,
                proposal_id=proposal_id,
                action=action,
                from_state=from_state,
                to_state=to_state,
                decided_by=decided_by,
                reason=reason,
                request_id=request_id,
            )
            if timestamp is not None:
                event.timestamp = timestamp
            session.add(event)
            session.commit()
            session.refresh(event)
            return event

    def list_events(
        self,
        order_id: Optional[str] = None,
        proposal_id: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[AuditEventModel]:
        """List audit events in descending chronological order."""
        with self._session_factory() as session:
            stmt = select(AuditEventModel)
            if order_id:
                stmt = stmt.where(AuditEventModel.order_id == order_id)
            if proposal_id:
                stmt = stmt.where(AuditEventModel.proposal_id == proposal_id)
            stmt = stmt.order_by(AuditEventModel.timestamp.desc()).offset(offset).limit(limit)
            return list(session.scalars(stmt).all())
