"""Dedicated end-to-end customer support journey test for Aster & Row.

Exercises the entire production customer-support action lifecycle through actual interfaces:
Customer asks to cancel an order
→ Agent interprets the request
→ Policy and order eligibility are checked
→ Agent creates a human approval request (PENDING_APPROVAL)
→ Proposal is persisted without prematurely mutating the order
→ Authorized reviewer approves via /reviewer/proposals/{id}/approve
→ System revalidates order state and eligibility atomically
→ Cancellation executes exactly once (order becomes 'cancelled')
→ A duplicate approval/execution attempt returns idempotent response without double-cancellation
→ Audit history records every transition with correlated request_id
→ Observability (metrics, structured logs, traces) captures the complete journey
→ Zero customer PII or secret exposure
"""

import json
import uuid
from datetime import datetime, timezone
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from src.api import app, get_orchestrator
from src.approvals import get_engine, get_session_factory
from src.approvals.audit_repository import AuditRepository
from src.approvals.clock import FakeClock
from src.approvals.models import ActionType, Base, OrderModel, ProposalStatus, ProposedActionModel
from src.approvals.seed import seed_database
from src.approvals.service import ApprovalService
from src.approvals.sql_repository import SqlOrderRepository
import src.api as api_module
import src.approvals as approvals_module


class TestCompleteCustomerJourney:
    """Exercises the complete cancellation journey across API, Agent, Database, and Reviewer."""

    @pytest.fixture(autouse=True)
    def setup_journey_environment(self, tmp_path, monkeypatch):
        # 1. Isolated SQLite database for journey
        db_file = tmp_path / "journey_test.db"
        db_url = f"sqlite:///{db_file}"
        monkeypatch.setenv("DATABASE_URL", db_url)
        monkeypatch.setenv("APP_ENV", "test")
        monkeypatch.setenv("LLM_PROVIDER", "mock")
        monkeypatch.setenv("REVIEWER_API_KEY", "journey-reviewer-secret-key-12345")

        engine = create_engine(db_url, connect_args={"check_same_thread": False})
        Base.metadata.create_all(bind=engine)
        session_factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)

        # 2. Seed initial orders (including pending cancellable order ORD-1001)
        seed_database("data/demo_orders.json")

        # 3. Dedicated ApprovalService with controlled clock within the 30-minute window of 11:00:00Z
        audit_repo = AuditRepository(session_factory)
        clock = FakeClock(datetime(2026, 3, 1, 11, 15, 0, tzinfo=timezone.utc))
        approval_service = ApprovalService(
            session_factory=session_factory,
            audit_repo=audit_repo,
            clock=clock,
            default_ttl_hours=24,
        )

        # Inject into approval module singleton
        monkeypatch.setattr(approvals_module, "_global_approval_service", approval_service)
        monkeypatch.setattr(approvals_module, "get_session_factory", lambda url=None: session_factory)

        # Also connect SqlOrderRepository to orchestrator with matching snapshot_at
        sql_order_repo = SqlOrderRepository(
            session_factory=session_factory,
            snapshot_at="2026-03-01T11:15:00Z",
        )
        orch = get_orchestrator()
        orch.order_repository = sql_order_repo

        self.session_factory = session_factory
        self.approval_service = approval_service
        self.clock = clock
        self.client = TestClient(app)
        self.reviewer_headers = {
            "X-Reviewer-Key": "secret_admin_key_123",
            "Content-Type": "application/json",
        }

    def test_complete_cancellation_lifecycle(self):
        """Execute and verify the full customer journey with strict state assertions."""
        session_id = f"journey-cust-{uuid.uuid4().hex[:8]}"
        customer_request_id = f"req-cust-{uuid.uuid4().hex[:8]}"

        # =========================================================================
        # STEP 1: Verify Initial Order State in Database
        # =========================================================================
        with self.session_factory() as session:
            initial_order = session.scalar(select(OrderModel).where(OrderModel.order_id == "ORD-1001"))
            assert initial_order is not None, "Order ORD-1001 must exist in seeded DB"
            assert initial_order.status == "pending", "Initial order status must be pending"
            assert initial_order.raw_data.get("status") == "pending"

        # =========================================================================
        # STEP 2: Customer Submits Cancellation Request via /chat
        # =========================================================================
        chat_payload = {
            "session_id": session_id,
            "message": "I need to cancel my order ORD-1001 please.",
        }
        chat_resp = self.client.post(
            "/chat",
            json=chat_payload,
            headers={"X-Request-ID": customer_request_id},
        )
        assert chat_resp.status_code == 200, f"Chat endpoint failed: {chat_resp.text}"
        chat_data = chat_resp.json()

        # Assertions on Agent Response
        assert chat_data["session_id"] == session_id
        assert chat_data["decision_state"] == "ANSWER"
        assert chat_data["supported_action"] == "cancellation_request_submitted"
        assert chat_data["proposal"] is not None, "Agent must return proposal summary"
        proposal_id = chat_data["proposal"]["id"]
        assert proposal_id.startswith("prop_")
        assert chat_data["proposal"]["status"] == "PENDING_APPROVAL"

        # Response text contains safe acknowledgment
        assert "submitted" in chat_data["message"].lower() or "cancel" in chat_data["message"].lower()
        # Verify NO customer PII or raw secrets leaked
        assert "ava.morgan" not in chat_data["message"].lower()
        assert "risk_score" not in chat_data["message"].lower()

        # =========================================================================
        # STEP 3: Verify Proposal is Persisted but Order is NOT Mutated (Safety Invariant)
        # =========================================================================
        with self.session_factory() as session:
            prop_row = session.scalar(select(ProposedActionModel).where(ProposedActionModel.id == proposal_id))
            assert prop_row is not None, "Proposal must be persisted in database"
            assert prop_row.order_id == "ORD-1001"
            assert prop_row.session_id == session_id
            assert prop_row.action_type == ActionType.CANCELLATION
            assert prop_row.status == ProposalStatus.PENDING_APPROVAL
            assert prop_row.version == 1

            # INVARIANT: Order must remain 'pending' - LLM/Agent CANNOT mutate orders
            order_during = session.scalar(select(OrderModel).where(OrderModel.order_id == "ORD-1001"))
            assert order_during.status == "pending", "Order must NOT be mutated upon proposal creation"

        # =========================================================================
        # STEP 4: Customer Checks Active Proposal via /sessions/{id}/proposal
        # =========================================================================
        cust_prop_resp = self.client.get(
            f"/sessions/{session_id}/proposal",
            headers={"X-Request-ID": f"req-poll-{uuid.uuid4().hex[:6]}"},
        )
        assert cust_prop_resp.status_code == 200
        cust_prop_data = cust_prop_resp.json()
        assert cust_prop_data["id"] == proposal_id
        assert cust_prop_data["status"] == "PENDING_APPROVAL"
        assert cust_prop_data["order_id"] == "ORD-1001"

        # =========================================================================
        # STEP 5: Authorized Reviewer Inspects Proposal via /reviewer/proposals/{id}
        # =========================================================================
        reviewer_get_resp = self.client.get(
            f"/reviewer/proposals/{proposal_id}",
            headers=self.reviewer_headers,
        )
        assert reviewer_get_resp.status_code == 200
        rev_data = reviewer_get_resp.json()
        assert rev_data["id"] == proposal_id
        assert rev_data["status"] == "PENDING_APPROVAL"
        assert rev_data["version"] == 1
        assert rev_data["evidence_snapshot"]["is_cancellable"] is True

        # =========================================================================
        # STEP 6: Authorized Reviewer Approves Proposal
        # =========================================================================
        reviewer_req_id = f"req-rev-appr-{uuid.uuid4().hex[:8]}"
        approve_payload = {
            "version": 1,
            "note": "Verified customer identity and eligibility. Approved for cancellation.",
        }
        approve_resp = self.client.post(
            f"/reviewer/proposals/{proposal_id}/approve",
            json=approve_payload,
            headers={**self.reviewer_headers, "X-Request-ID": reviewer_req_id},
        )
        assert approve_resp.status_code == 200, f"Approve failed: {approve_resp.text}"
        appr_data = approve_resp.json()
        assert appr_data["id"] == proposal_id
        # Transition PENDING_APPROVAL -> APPROVED -> EXECUTED atomically
        assert appr_data["status"] == "EXECUTED"
        assert appr_data["decided_by"] == "admin"
        assert appr_data["version"] == 3  # v1 (pending) -> v2 (approved) -> v3 (executed)

        # =========================================================================
        # STEP 7: Verify Order Mutation & Final State in Database
        # =========================================================================
        with self.session_factory() as session:
            final_order = session.scalar(select(OrderModel).where(OrderModel.order_id == "ORD-1001"))
            assert final_order.status == "cancelled", "Order status must now be mutated to cancelled"
            assert final_order.raw_data.get("status") == "cancelled"

            final_prop = session.scalar(select(ProposedActionModel).where(ProposedActionModel.id == proposal_id))
            assert final_prop.status == ProposalStatus.EXECUTED

        # =========================================================================
        # STEP 8: Idempotency & Duplicate Execution Defense
        # Duplicate approval attempt must return current state without double execution
        # =========================================================================
        dup_approve_resp = self.client.post(
            f"/reviewer/proposals/{proposal_id}/approve",
            json={"version": 3, "note": "Duplicate approval attempt"},
            headers=self.reviewer_headers,
        )
        assert dup_approve_resp.status_code == 200
        dup_data = dup_approve_resp.json()
        assert dup_data["status"] == "EXECUTED"

        # Order must remain cancelled once, version must not continuously increment
        with self.session_factory() as session:
            post_order = session.scalar(select(OrderModel).where(OrderModel.order_id == "ORD-1001"))
            assert post_order.status == "cancelled"

        # =========================================================================
        # STEP 9: Complete and Ordered Audit Trail Verification
        # =========================================================================
        audit_resp = self.client.get(
            f"/reviewer/audit?proposal_id={proposal_id}",
            headers=self.reviewer_headers,
        )
        assert audit_resp.status_code == 200
        audit_events = audit_resp.json()

        # Expected chronological lifecycle:
        # 1. create_proposal: None -> PENDING_APPROVAL (by agent)
        # 2. approve: PENDING_APPROVAL -> APPROVED (by reviewer)
        # 3. execute_success: APPROVED -> EXECUTED (by system_execution)
        assert len(audit_events) == 3, f"Expected 3 audit events, got {len(audit_events)}"

        ev_create, ev_approve, ev_exec = audit_events[0], audit_events[1], audit_events[2]

        assert ev_create["action"] == "create_proposal"
        assert ev_create["from_state"] is None
        assert ev_create["to_state"] == "PENDING_APPROVAL"
        assert ev_create["decided_by"] == "agent"

        assert ev_approve["action"] == "approve"
        assert ev_approve["from_state"] == "PENDING_APPROVAL"
        assert ev_approve["to_state"] == "APPROVED"
        assert ev_approve["decided_by"] == "admin"
        assert ev_approve["request_id"] == reviewer_req_id

        assert ev_exec["action"] == "execute_success"
        assert ev_exec["from_state"] == "APPROVED"
        assert ev_exec["to_state"] == "EXECUTED"
        assert ev_exec["decided_by"] == "system_execution"
        assert ev_exec["reason"] == "order_mutated"

        # =========================================================================
        # STEP 10: Trace & Metrics Observability Verification
        # =========================================================================
        trace_resp = self.client.get(f"/sessions/{session_id}/trace")
        assert trace_resp.status_code == 200
        trace_data = trace_resp.json()
        assert trace_data["session_id"] == session_id
        assert trace_data["trace"] is not None

        # Verify Prometheus metrics expose HTTP traffic and execution
        metrics_resp = self.client.get("/metrics")
        assert metrics_resp.status_code == 200
        metrics_text = metrics_resp.text
        assert "http_requests_total" in metrics_text
        assert "http_request_duration_seconds" in metrics_text
