"""SQLAlchemy declarative models for orders, proposed actions, and immutable audit events."""

from datetime import datetime, timezone
from enum import Enum
import uuid
from typing import Any, Dict, Optional

from sqlalchemy import (
    Column,
    DateTime,
    Enum as SQLEnum,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    """Base declarative class."""
    pass


class ActionType(str, Enum):
    """Types of customer actions that require human review."""
    CANCELLATION = "CANCELLATION"
    ADDRESS_CHANGE = "ADDRESS_CHANGE"


class ProposalStatus(str, Enum):
    """Lifecycle statuses for a proposed action."""
    PENDING_APPROVAL = "PENDING_APPROVAL"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    EXECUTED = "EXECUTED"
    FAILED = "FAILED"


def utc_now() -> datetime:
    """Return timezone-aware current UTC datetime."""
    return datetime.now(timezone.utc)


class OrderModel(Base):
    """SQL representation of an order, compatible with RawOrder schema."""
    __tablename__ = "orders"

    order_id = Column(String(64), primary_key=True, index=True)
    customer_id = Column(String(64), nullable=False, index=True)
    status = Column(String(32), nullable=False, default="pending", index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)
    items = Column(JSON, nullable=False, default=list)
    shipping_address = Column(JSON, nullable=True)
    raw_data = Column(JSON, nullable=False, default=dict)

    proposals = relationship("ProposedActionModel", back_populates="order", cascade="all, delete-orphan")


class ProposedActionModel(Base):
    """Proposed customer action awaiting or processed by human review."""
    __tablename__ = "proposed_actions"

    id = Column(String(64), primary_key=True, default=lambda: f"prop_{uuid.uuid4().hex[:12]}")
    order_id = Column(String(64), ForeignKey("orders.order_id"), nullable=False, index=True)
    session_id = Column(String(128), nullable=False, index=True)
    action_type = Column(SQLEnum(ActionType, name="action_type_enum"), nullable=False)
    status = Column(SQLEnum(ProposalStatus, name="proposal_status_enum"), nullable=False, default=ProposalStatus.PENDING_APPROVAL, index=True)
    version = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    decided_by = Column(String(128), nullable=True)
    decided_at = Column(DateTime(timezone=True), nullable=True)
    decision_reason = Column(Text, nullable=True)
    evidence_snapshot = Column(JSON, nullable=False, default=dict)

    order = relationship("OrderModel", back_populates="proposals")

    __table_args__ = (
        Index("ix_proposed_actions_order_action", "order_id", "action_type"),
    )


class AuditEventModel(Base):
    """Append-only, immutable audit trail for all HITL decisions and state transitions."""
    __tablename__ = "audit_events"

    id = Column(String(64), primary_key=True, default=lambda: f"aud_{uuid.uuid4().hex[:12]}")
    proposal_id = Column(String(64), nullable=True, index=True)
    order_id = Column(String(64), nullable=False, index=True)
    action = Column(String(64), nullable=False)
    from_state = Column(String(32), nullable=True)
    to_state = Column(String(32), nullable=False)
    decided_by = Column(String(128), nullable=False)
    reason = Column(Text, nullable=True)
    request_id = Column(String(128), nullable=True, index=True)
    timestamp = Column(DateTime(timezone=True), nullable=False, default=utc_now)

    __table_args__ = (
        Index("ix_audit_events_order_time", "order_id", "timestamp"),
    )
