"""Approvals package initialization and factory functions."""

import os
from functools import lru_cache
from typing import Optional
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.approvals.audit_repository import AuditRepository
from src.approvals.clock import Clock, SystemClock
from src.approvals.models import Base
from src.approvals.service import ApprovalService
from src.approvals.sql_repository import SqlOrderRepository


def get_engine(database_url: Optional[str] = None):
    url = database_url or os.getenv("DATABASE_URL", "sqlite:///./data/aster_row.db")
    # For SQLite, check same thread is false for concurrent web requests
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    return create_engine(url, connect_args=connect_args)


def get_session_factory(database_url: Optional[str] = None):
    engine = get_engine(database_url)
    Base.metadata.create_all(bind=engine)
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)


_global_approval_service: Optional[ApprovalService] = None


def get_approval_service(
    database_url: Optional[str] = None,
    clock: Optional[Clock] = None,
) -> ApprovalService:
    """Return configured ApprovalService singleton."""
    global _global_approval_service
    if _global_approval_service is None or database_url is not None or clock is not None:
        session_factory = get_session_factory(database_url)
        audit_repo = AuditRepository(session_factory)
        service = ApprovalService(
            session_factory=session_factory,
            audit_repo=audit_repo,
            clock=clock or SystemClock(),
        )
        if database_url is None and clock is None:
            _global_approval_service = service
        return service
    return _global_approval_service
