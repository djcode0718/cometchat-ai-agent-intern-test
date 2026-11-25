"""Approval service managing HITL proposals, state transitions, and atomic execution."""

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from src.approvals.audit_repository import AuditRepository
from src.approvals.clock import Clock, SystemClock
from src.approvals.models import (
    ActionType,
    OrderModel,
    ProposalStatus,
    ProposedActionModel,
)
from src.approvals.state_machine import (
    InvalidTransition,
    ProposalEvent,
    is_terminal,
    transition,
)
from src.tools.order_models import CustomerSafeOrder, RawOrder
from src.tools.reconciler import StatusReconciler


class ConcurrencyConflictError(Exception):
    """Raised when an optimistic concurrency version check fails (409 Conflict)."""
    pass


class ProposalNotFoundError(Exception):
    """Raised when a requested proposal does not exist."""
    pass


class IneligibleOrderError(Exception):
    """Raised when attempting to propose an action on an ineligible order."""
    pass


class ApprovalService:
    """Service orchestrating Human-in-the-Loop approval workflows."""

    def __init__(
        self,
        session_factory,
        audit_repo: AuditRepository,
        clock: Optional[Clock] = None,
        default_ttl_hours: int = 24,
    ) -> None:
        self._session_factory = session_factory
        self.audit_repo = audit_repo
        self.clock = clock or SystemClock()
        self.default_ttl = timedelta(hours=default_ttl_hours)

    def _expire_if_due(self, proposal: ProposedActionModel, session: Session) -> bool:
        """Check if proposal is expired and lazily transition to EXPIRED."""
        now = self.clock.now()
        # Ensure now and expires_at have compatible tzinfo
        expires_at = proposal.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)

        if proposal.status == ProposalStatus.PENDING_APPROVAL and now > expires_at:
            old_status = proposal.status
            proposal.status = ProposalStatus.EXPIRED
            proposal.version += 1
            session.commit()
            self.audit_repo.record(
                order_id=proposal.order_id,
                proposal_id=proposal.id,
                action="expire",
                from_state=old_status.value,
                to_state=ProposalStatus.EXPIRED.value,
                decided_by="system_clock",
                reason="ttl_expired",
                timestamp=now,
            )
            return True
        return False

    def create_proposal(
        self,
        order_id: str,
        session_id: str,
        action_type: ActionType,
        evidence_snapshot: Dict[str, Any],
        request_id: Optional[str] = None,
        ttl_hours: Optional[int] = None,
    ) -> ProposedActionModel:
        """Create a new proposal in PENDING_APPROVAL.

        Idempotency: If an open (PENDING_APPROVAL) proposal already exists for
        (order_id, action_type), it is returned.
        """
        now = self.clock.now()
        ttl = timedelta(hours=ttl_hours) if ttl_hours else self.default_ttl
        expires_at = now + ttl

        with self._session_factory() as session:
            # Check for existing open proposal
            stmt = select(ProposedActionModel).where(
                ProposedActionModel.order_id == order_id,
                ProposedActionModel.action_type == action_type,
            ).order_by(ProposedActionModel.created_at.desc())
            
            existing = session.scalars(stmt).first()
            if existing:
                self._expire_if_due(existing, session)
                if existing.status == ProposalStatus.PENDING_APPROVAL:
                    # Update session_id to current customer session
                    existing.session_id = session_id
                    session.commit()
                    session.refresh(existing)
                    return existing

            proposal = ProposedActionModel(
                order_id=order_id,
                session_id=session_id,
                action_type=action_type,
                status=ProposalStatus.PENDING_APPROVAL,
                version=1,
                created_at=now,
                expires_at=expires_at,
                evidence_snapshot=evidence_snapshot,
            )
            session.add(proposal)
            session.commit()
            session.refresh(proposal)

            self.audit_repo.record(
                order_id=order_id,
                proposal_id=proposal.id,
                action="create_proposal",
                from_state=None,
                to_state=ProposalStatus.PENDING_APPROVAL.value,
                decided_by="agent",
                reason=f"customer_{action_type.value.lower()}_request",
                request_id=request_id,
                timestamp=now,
            )
            return proposal

    def get(self, proposal_id: str) -> Optional[ProposedActionModel]:
        """Fetch a proposal by ID, lazily checking expiry."""
        with self._session_factory() as session:
            stmt = select(ProposedActionModel).where(ProposedActionModel.id == proposal_id)
            proposal = session.scalar(stmt)
            if not proposal:
                return None
            self._expire_if_due(proposal, session)
            session.refresh(proposal)
            return proposal

    def list(
        self,
        status: Optional[ProposalStatus] = None,
        order_id: Optional[str] = None,
        session_id: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[ProposedActionModel]:
        """List proposals with filters and pagination."""
        with self._session_factory() as session:
            stmt = select(ProposedActionModel)
            if status:
                stmt = stmt.where(ProposedActionModel.status == status)
            if order_id:
                stmt = stmt.where(ProposedActionModel.order_id == order_id)
            if session_id:
                stmt = stmt.where(ProposedActionModel.session_id == session_id)
            stmt = stmt.order_by(ProposedActionModel.created_at.desc()).offset(offset).limit(limit)
            proposals = list(session.scalars(stmt).all())
            for p in proposals:
                self._expire_if_due(p, session)
            return proposals

    def approve(
        self,
        proposal_id: str,
        reviewer_id: str,
        expected_version: Optional[int] = None,
        reason: Optional[str] = None,
        request_id: Optional[str] = None,
    ) -> ProposedActionModel:
        """Approve and atomically execute a proposal with optimistic locking and re-verification."""
        now = self.clock.now()

        with self._session_factory() as session:
            stmt = select(ProposedActionModel).where(ProposedActionModel.id == proposal_id).with_for_update()
            proposal = session.scalar(stmt)
            if not proposal:
                raise ProposalNotFoundError(f"Proposal {proposal_id} not found")

            self._expire_if_due(proposal, session)

            # Idempotency: Approving an already-executed or already-approved proposal returns current state
            if proposal.status in (ProposalStatus.APPROVED, ProposalStatus.EXECUTED):
                return proposal

            # Terminal states (REJECTED, EXPIRED, FAILED) cannot be approved
            if is_terminal(proposal.status):
                raise InvalidTransition(proposal.status, ProposalStatus.APPROVED, "Cannot approve terminal proposal")

            # Optimistic concurrency check
            if expected_version is not None and proposal.version != expected_version:
                raise ConcurrencyConflictError(
                    f"Version conflict: expected {expected_version}, found {proposal.version}"
                )

            # Transition PENDING_APPROVAL -> APPROVED
            old_status = proposal.status
            proposal.status = transition(proposal.status, ProposalEvent.APPROVE)
            proposal.decided_by = reviewer_id
            proposal.decided_at = now
            proposal.decision_reason = reason
            proposal.version += 1

            self.audit_repo.record(
                order_id=proposal.order_id,
                proposal_id=proposal.id,
                action="approve",
                from_state=old_status.value,
                to_state=ProposalStatus.APPROVED.value,
                decided_by=reviewer_id,
                reason=reason,
                request_id=request_id,
                timestamp=now,
            )

            # Atomic Execution Check: Re-verify order eligibility
            order_stmt = select(OrderModel).where(OrderModel.order_id == proposal.order_id).with_for_update()
            order_row = session.scalar(order_stmt)
            
            is_eligible = False
            if order_row:
                raw_dict = dict(order_row.raw_data or {})
                raw_dict["order_id"] = order_row.order_id
                raw_dict["status"] = order_row.status
                if "customer" not in raw_dict:
                    raw_dict["customer"] = {"name": "Customer", "email": "customer@example.test", "shipping_address": "100 Main St"}
                if "membership_tier" not in raw_dict:
                    raw_dict["membership_tier"] = "standard"
                if "items" not in raw_dict:
                    raw_dict["items"] = [{"sku": "SKU-DEMO", "name": "Item", "quantity": 1, "final_sale": False}]
                if "status_updated_at" not in raw_dict:
                    raw_dict["status_updated_at"] = "2026-03-01T10:00:00Z"
                if "placed_at" not in raw_dict:
                    raw_dict["placed_at"] = "2026-03-01T10:00:00Z"
                if "internal" not in raw_dict:
                    raw_dict["internal"] = {"risk_score": 0, "warehouse_note": "None", "support_tags": []}

                raw_order = RawOrder(**raw_dict)
                reconciled = StatusReconciler.reconcile(raw_order)
                if proposal.action_type == ActionType.CANCELLATION:
                    is_eligible = reconciled.is_cancellable
                elif proposal.action_type == ActionType.ADDRESS_CHANGE:
                    is_eligible = reconciled.is_address_change_allowed

            if is_eligible and order_row is not None:
                # Execution Success: Mutate order status
                exec_from = proposal.status
                proposal.status = transition(proposal.status, ProposalEvent.EXECUTE_SUCCESS)
                proposal.version += 1
                if proposal.action_type == ActionType.CANCELLATION:
                    order_row.status = "cancelled"
                    if order_row.raw_data:
                        order_row.raw_data["status"] = "cancelled"
                session.commit()
                session.refresh(proposal)

                self.audit_repo.record(
                    order_id=proposal.order_id,
                    proposal_id=proposal.id,
                    action="execute_success",
                    from_state=exec_from.value,
                    to_state=ProposalStatus.EXECUTED.value,
                    decided_by="system_execution",
                    reason="order_mutated",
                    request_id=request_id,
                    timestamp=now,
                )
            else:
                # Stale order failure: Do NOT mutate order
                exec_from = proposal.status
                proposal.status = transition(proposal.status, ProposalEvent.EXECUTE_FAIL)
                proposal.decision_reason = f"stale_order: no longer eligible for {proposal.action_type.value}"
                proposal.version += 1
                session.commit()
                session.refresh(proposal)

                self.audit_repo.record(
                    order_id=proposal.order_id,
                    proposal_id=proposal.id,
                    action="execute_fail",
                    from_state=exec_from.value,
                    to_state=ProposalStatus.FAILED.value,
                    decided_by="system_execution",
                    reason="stale_order",
                    request_id=request_id,
                    timestamp=now,
                )

            return proposal

    def reject(
        self,
        proposal_id: str,
        reviewer_id: str,
        reason: str,
        expected_version: Optional[int] = None,
        request_id: Optional[str] = None,
    ) -> ProposedActionModel:
        """Reject a pending proposal. Requires reason (10 to 500 characters)."""
        if not reason or len(reason.strip()) < 10 or len(reason.strip()) > 500:
            raise ValueError("Rejection reason must be between 10 and 500 characters.")

        now = self.clock.now()

        with self._session_factory() as session:
            stmt = select(ProposedActionModel).where(ProposedActionModel.id == proposal_id).with_for_update()
            proposal = session.scalar(stmt)
            if not proposal:
                raise ProposalNotFoundError(f"Proposal {proposal_id} not found")

            self._expire_if_due(proposal, session)

            # Idempotency: Rejecting an already-rejected proposal returns it
            if proposal.status == ProposalStatus.REJECTED:
                return proposal

            if is_terminal(proposal.status):
                raise InvalidTransition(proposal.status, ProposalStatus.REJECTED, "Cannot reject terminal proposal")

            if expected_version is not None and proposal.version != expected_version:
                raise ConcurrencyConflictError(
                    f"Version conflict: expected {expected_version}, found {proposal.version}"
                )

            old_status = proposal.status
            proposal.status = transition(proposal.status, ProposalEvent.REJECT)
            proposal.decided_by = reviewer_id
            proposal.decided_at = now
            proposal.decision_reason = reason.strip()
            proposal.version += 1
            session.commit()
            session.refresh(proposal)

            self.audit_repo.record(
                order_id=proposal.order_id,
                proposal_id=proposal.id,
                action="reject",
                from_state=old_status.value,
                to_state=ProposalStatus.REJECTED.value,
                decided_by=reviewer_id,
                reason=reason.strip(),
                request_id=request_id,
                timestamp=now,
            )
            return proposal

    def expire_due(self) -> int:
        """Scan and transition all due proposals to EXPIRED. Returns count expired."""
        now = self.clock.now()
        count = 0
        with self._session_factory() as session:
            stmt = select(ProposedActionModel).where(
                ProposedActionModel.status == ProposalStatus.PENDING_APPROVAL,
                ProposedActionModel.expires_at <= now,
            )
            due_proposals = list(session.scalars(stmt).all())
            for p in due_proposals:
                if self._expire_if_due(p, session):
                    count += 1
        return count
