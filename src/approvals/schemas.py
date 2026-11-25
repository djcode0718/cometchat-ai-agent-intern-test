"""Pydantic schemas for HITL approval requests and responses."""

from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from src.approvals.models import ActionType, ProposalStatus


class ProposalResponse(BaseModel):
    """Customer and reviewer safe response for proposed actions."""
    id: str = Field(..., description="Unique proposal identifier")
    order_id: str = Field(..., description="Target order ID")
    session_id: str = Field(..., description="Session ID bound to customer")
    action_type: ActionType = Field(..., description="Type of proposed action")
    status: ProposalStatus = Field(..., description="Current status of proposal")
    version: int = Field(..., description="Optimistic concurrency version")
    created_at: datetime = Field(..., description="Creation timestamp UTC")
    expires_at: datetime = Field(..., description="Expiration timestamp UTC")
    decided_by: Optional[str] = Field(None, description="Reviewer or system identity")
    decided_at: Optional[datetime] = Field(None, description="Decision timestamp UTC")
    decision_reason: Optional[str] = Field(None, description="Reason for decision or failure")
    evidence_snapshot: Dict[str, Any] = Field(default_factory=dict, description="Customer-safe evidence snapshot")
    request_id: Optional[str] = Field(None, description="Correlation request ID")

    model_config = {
        "json_schema_extra": {
            "example": {
                "id": "prop_a1b2c3d4e5f6",
                "order_id": "ORD-1001",
                "session_id": "sess_cust_123",
                "action_type": "CANCELLATION",
                "status": "PENDING_APPROVAL",
                "version": 1,
                "created_at": "2026-03-01T12:00:00Z",
                "expires_at": "2026-03-02T12:00:00Z",
                "decided_by": None,
                "decided_at": None,
                "decision_reason": None,
                "evidence_snapshot": {
                    "order_id": "ORD-1001",
                    "status": "pending",
                    "is_cancellable": True,
                },
                "request_id": "req-9876543210",
            }
        }
    }


class ApproveProposalRequest(BaseModel):
    """Reviewer request to approve a proposal."""
    version: Optional[int] = Field(None, description="Expected version for optimistic locking")
    note: Optional[str] = Field(None, max_length=500, description="Optional reviewer approval note")

    model_config = {
        "json_schema_extra": {
            "example": {
                "version": 1,
                "note": "Customer contacted support within eligible window.",
            }
        }
    }


class RejectProposalRequest(BaseModel):
    """Reviewer request to reject a proposal."""
    version: Optional[int] = Field(None, description="Expected version for optimistic locking")
    reason: str = Field(..., min_length=10, max_length=500, description="Mandatory rejection reason")

    model_config = {
        "json_schema_extra": {
            "example": {
                "version": 1,
                "reason": "Order already processed for packing in warehouse.",
            }
        }
    }


class AuditEventResponse(BaseModel):
    """Response representing an immutable audit log record."""
    id: str
    order_id: str
    proposal_id: Optional[str] = None
    action: str
    from_state: Optional[str] = None
    to_state: str
    decided_by: str
    reason: Optional[str] = None
    request_id: Optional[str] = None
    timestamp: datetime
