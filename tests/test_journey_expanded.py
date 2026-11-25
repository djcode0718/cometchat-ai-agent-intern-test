"""Expanded Customer Support Journey Lifecycle Matrix (12 Scenarios).

Tests distinct end-to-end user journeys through the real API, agent, and reviewer interfaces:
J01: Eligible cancellation happy path (ORD-1001: PENDING_APPROVAL -> APPROVED -> EXECUTED).
J02: Ineligible cancellation - Already shipped (ORD-1002: Refusal, no proposal created).
J03: Ineligible cancellation - Already delivered (ORD-1003: Return policy explanation, no proposal).
J04: Ineligible cancellation - Final sale item (ORD-1004: Policy exclusion, no proposal).
J05: Ineligible cancellation - Already cancelled (ORD-1005: Clarification, no proposal).
J06: Ineligible cancellation - Cancellation window expired (>60m window).
J07: Eligible cancellation rejected by reviewer (PENDING_APPROVAL -> REJECTED, order untouched).
J08: Eligible cancellation expires TTL without reviewer action (PENDING_APPROVAL -> EXPIRED).
J09: Eligible address change request (ORD-1001: PENDING_APPROVAL -> APPROVED -> EXECUTED).
J10: Multi-turn journey: policy discovery -> order status -> cancellation submission.
J11: Idempotent duplicate cancellation requests within same customer session.
J12: Race condition: warehouse marks order shipped while proposal is pending approval.
"""

import csv
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

import src.approvals as approvals_module
from src.api import app, get_orchestrator
from src.approvals.audit_repository import AuditRepository
from src.approvals.clock import FakeClock
from src.approvals.models import (
    ActionType,
    AuditEventModel,
    Base,
    OrderModel,
    ProposalStatus,
    ProposedActionModel,
)
from src.approvals.seed import seed_database
from src.approvals.service import ApprovalService
from src.approvals.sql_repository import SqlOrderRepository
from src.llm.mock import MockLLMProvider


class TestCustomerJourneyLifecycleExpansion:
    """Matrix of 12 distinct customer journey lifecycles."""

    @pytest.fixture(autouse=True)
    def setup_journey_environment(self, tmp_path, monkeypatch):
        db_file = tmp_path / "journey_expansion_test.db"
        db_url = f"sqlite:///{db_file}"
        monkeypatch.setenv("DATABASE_URL", db_url)
        monkeypatch.setenv("APP_ENV", "test")
        monkeypatch.setenv("LLM_PROVIDER", "mock")
        monkeypatch.setenv("REVIEWER_KEYS", "admin:secret_admin_key_123:admin,reviewer1:rev_key_abc:reviewer")

        engine = create_engine(db_url, connect_args={"check_same_thread": False})
        Base.metadata.create_all(bind=engine)
        session_factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)

        seed_database("data/demo_orders.json")

        audit_repo = AuditRepository(session_factory)
        # Baseline clock: 2026-03-01 11:15:00 UTC (15 mins after ORD-1001 placed at 11:00:00 UTC)
        clock = FakeClock(datetime(2026, 3, 1, 11, 15, 0, tzinfo=timezone.utc))
        approval_service = ApprovalService(
            session_factory=session_factory,
            audit_repo=audit_repo,
            clock=clock,
            default_ttl_hours=24,
        )

        monkeypatch.setattr(approvals_module, "_global_approval_service", approval_service)
        monkeypatch.setattr(approvals_module, "get_session_factory", lambda url=None: session_factory)

        sql_order_repo = SqlOrderRepository(
            session_factory=session_factory,
            snapshot_at="2026-03-01T11:15:00Z",
        )
        orch = get_orchestrator()
        orch.order_repository = sql_order_repo
        orch.llm_provider = MockLLMProvider()

        self.session_factory = session_factory
        self.approval_service = approval_service
        self.clock = clock
        self.client = TestClient(app)
        self.reviewer_headers = {"X-Reviewer-Key": "secret_admin_key_123"}
        self.results: List[Dict[str, Any]] = []

    # -----------------------------------------------------------------------
    # J01: Eligible Cancellation Happy Path
    # -----------------------------------------------------------------------
    def test_j01_eligible_cancellation_happy_path(self):
        session_id = f"sess-j01-{uuid.uuid4().hex[:6]}"
        resp = self.client.post(
            "/chat",
            json={"session_id": session_id, "message": "I need to cancel order ORD-1001 please."},
            headers={"X-Request-ID": "req-j01-chat"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["decision_state"] == "ANSWER"
        assert data["supported_action"] == "cancellation_request_submitted"
        proposal_id = data["proposal"]["id"]

        # Reviewer approves
        appr_resp = self.client.post(
            f"/reviewer/proposals/{proposal_id}/approve",
            json={"version": 1, "note": "Customer requested within 20 mins of placement"},
            headers={"X-Reviewer-Key": "secret_admin_key_123", "X-Request-ID": "req-j01-appr"},
        )
        assert appr_resp.status_code == 200
        assert appr_resp.json()["status"] == "EXECUTED"

        # Verify order mutated to cancelled
        with self.session_factory() as s:
            order = s.scalar(select(OrderModel).where(OrderModel.order_id == "ORD-1001"))
            assert order.status == "cancelled"

    # -----------------------------------------------------------------------
    # J02: Ineligible Cancellation - Already Shipped
    # -----------------------------------------------------------------------
    def test_j02_ineligible_cancellation_already_shipped(self):
        session_id = f"sess-j02-{uuid.uuid4().hex[:6]}"
        resp = self.client.post(
            "/chat",
            json={"session_id": session_id, "message": "Cancel order ORD-1003 immediately."},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["proposal"] is None, "Ineligible order must not create proposal"
        assert "shipped" in data["message"].lower() or "cannot" in data["message"].lower()

        # Invariant: Order status remains shipped
        with self.session_factory() as s:
            order = s.scalar(select(OrderModel).where(OrderModel.order_id == "ORD-1003"))
            assert order.status == "shipped"

    # -----------------------------------------------------------------------
    # J03: Ineligible Cancellation - Already Delivered
    # -----------------------------------------------------------------------
    def test_j03_ineligible_cancellation_already_delivered(self):
        session_id = f"sess-j03-{uuid.uuid4().hex[:6]}"
        resp = self.client.post(
            "/chat",
            json={"session_id": session_id, "message": "Can I cancel ORD-1004?"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["proposal"] is None
        assert "delivered" in data["message"].lower() or "return" in data["message"].lower()

    # -----------------------------------------------------------------------
    # J04: Ineligible Cancellation - Final Sale Item
    # -----------------------------------------------------------------------
    def test_j04_ineligible_cancellation_final_sale(self):
        with self.session_factory() as s:
            order = s.scalar(select(OrderModel).where(OrderModel.order_id == "ORD-1002"))
            raw = dict(order.raw_data or {})
            raw["items"] = [{"sku": "SKU-FINAL", "name": "Final Sale Cap", "quantity": 1, "final_sale": True}]
            raw["is_cancellable"] = False
            order.raw_data = raw
            s.commit()

        session_id = f"sess-j04-{uuid.uuid4().hex[:6]}"
        resp = self.client.post(
            "/chat",
            json={"session_id": session_id, "message": "Cancel my order ORD-1002"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["proposal"] is None
        with self.session_factory() as s:
            order = s.scalar(select(OrderModel).where(OrderModel.order_id == "ORD-1002"))
            assert order.status != "cancelled"

    # -----------------------------------------------------------------------
    # J05: Ineligible Cancellation - Already Cancelled
    # -----------------------------------------------------------------------
    def test_j05_ineligible_cancellation_already_cancelled(self):
        with self.session_factory() as s:
            order = s.scalar(select(OrderModel).where(OrderModel.order_id == "ORD-1005"))
            order.status = "cancelled"
            raw = dict(order.raw_data or {})
            raw["status"] = "cancelled"
            raw["is_cancellable"] = False
            order.raw_data = raw
            s.commit()

        session_id = f"sess-j05-{uuid.uuid4().hex[:6]}"
        resp = self.client.post(
            "/chat",
            json={"session_id": session_id, "message": "Please cancel ORD-1005"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["proposal"] is None
        assert "already" in data["message"].lower() or "cancelled" in data["message"].lower()

    # -----------------------------------------------------------------------
    # J06: Ineligible Cancellation - Window Expired
    # -----------------------------------------------------------------------
    def test_j06_ineligible_cancellation_window_expired(self):
        session_id = f"sess-j06-{uuid.uuid4().hex[:6]}"
        resp = self.client.post(
            "/chat",
            json={"session_id": session_id, "message": "I want to cancel ORD-1005"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["proposal"] is None

    # -----------------------------------------------------------------------
    # J07: Reviewer Rejection Journey
    # -----------------------------------------------------------------------
    def test_j07_reviewer_rejection_journey(self):
        session_id = f"sess-j07-{uuid.uuid4().hex[:6]}"
        resp = self.client.post(
            "/chat",
            json={"session_id": session_id, "message": "Cancel order ORD-1001"},
        )
        assert resp.status_code == 200
        proposal_id = resp.json()["proposal"]["id"]

        # Reviewer rejects proposal with clear reason
        rej_resp = self.client.post(
            f"/reviewer/proposals/{proposal_id}/reject",
            json={"version": 1, "reason": "Suspected unauthorized account access, cancellation rejected."},
            headers=self.reviewer_headers,
        )
        assert rej_resp.status_code == 200
        assert rej_resp.json()["status"] == "REJECTED"

        # Invariant: Order was NOT cancelled
        with self.session_factory() as s:
            order = s.scalar(select(OrderModel).where(OrderModel.order_id == "ORD-1001"))
            assert order.status != "cancelled"

    # -----------------------------------------------------------------------
    # J08: Reviewer TTL Expiration Journey
    # -----------------------------------------------------------------------
    def test_j08_reviewer_ttl_expiration_journey(self):
        session_id = f"sess-j08-{uuid.uuid4().hex[:6]}"
        resp = self.client.post(
            "/chat",
            json={"session_id": session_id, "message": "Cancel order ORD-1001"},
        )
        assert resp.status_code == 200
        proposal_id = resp.json()["proposal"]["id"]

        # Advance clock past 24h default TTL
        self.clock.advance(hours=25)

        # Attempt to approve expired proposal -> 400 Bad Request
        appr_resp = self.client.post(
            f"/reviewer/proposals/{proposal_id}/approve",
            json={"version": 1, "note": "Late approval attempt"},
            headers=self.reviewer_headers,
        )
        assert appr_resp.status_code == 400
        assert "Cannot approve terminal proposal" in appr_resp.json()["detail"]

        with self.session_factory() as s:
            prop = s.scalar(select(ProposedActionModel).where(ProposedActionModel.id == proposal_id))
            assert prop.status == ProposalStatus.EXPIRED

    # -----------------------------------------------------------------------
    # J09: Address Change Request Journey
    # -----------------------------------------------------------------------
    def test_j09_address_change_request_journey(self):
        session_id = f"sess-j09-{uuid.uuid4().hex[:6]}"
        resp = self.client.post(
            "/chat",
            json={"session_id": session_id, "message": "I need to update my shipping address for order ORD-1001"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["proposal"] is not None
        proposal_id = data["proposal"]["id"]

        # Reviewer approves address change
        appr_resp = self.client.post(
            f"/reviewer/proposals/{proposal_id}/approve",
            json={"version": 1, "note": "Verified customer ID, approved address update"},
            headers=self.reviewer_headers,
        )
        assert appr_resp.status_code == 200
        assert appr_resp.json()["status"] == "EXECUTED"

    # -----------------------------------------------------------------------
    # J10: Multi-Turn Discovery Before Cancellation
    # -----------------------------------------------------------------------
    def test_j10_multiturn_policy_discovery_then_cancellation(self):
        session_id = f"sess-j10-{uuid.uuid4().hex[:6]}"

        # Turn 1: Policy inquiry
        t1 = self.client.post(
            "/chat",
            json={"session_id": session_id, "message": "What is your cancellation policy for standard orders?"},
        )
        assert t1.status_code == 200
        assert "cancel" in t1.json()["message"].lower()
        assert t1.json()["proposal"] is None

        # Turn 2: Order status inquiry
        t2 = self.client.post(
            "/chat",
            json={"session_id": session_id, "message": "Can I cancel ORD-1001?"},
        )
        assert t2.status_code == 200

        # Turn 3: Explicit cancellation instruction
        t3 = self.client.post(
            "/chat",
            json={"session_id": session_id, "message": "Yes, please cancel ORD-1001 now."},
        )
        assert t3.status_code == 200
        assert t3.json()["proposal"] is not None
        assert t3.json()["supported_action"] == "cancellation_request_submitted"

    # -----------------------------------------------------------------------
    # J11: Idempotent Duplicate Cancellation Requests
    # -----------------------------------------------------------------------
    def test_j11_idempotent_duplicate_cancellation_requests(self):
        session_id = f"sess-j11-{uuid.uuid4().hex[:6]}"

        # First request
        resp1 = self.client.post(
            "/chat",
            json={"session_id": session_id, "message": "Cancel order ORD-1001"},
        )
        assert resp1.status_code == 200
        p1_id = resp1.json()["proposal"]["id"]

        # Second request in same session
        resp2 = self.client.post(
            "/chat",
            json={"session_id": session_id, "message": "Please cancel ORD-1001 again"},
        )
        assert resp2.status_code == 200
        p2_id = resp2.json()["proposal"]["id"]

        # Invariant: Same proposal ID returned (no duplicate pending proposals)
        assert p1_id == p2_id

    # -----------------------------------------------------------------------
    # J12: Warehouse State Race Condition
    # -----------------------------------------------------------------------
    def test_j12_warehouse_fulfillment_race_condition(self):
        session_id = f"sess-j12-{uuid.uuid4().hex[:6]}"
        resp = self.client.post(
            "/chat",
            json={"session_id": session_id, "message": "Cancel order ORD-1001"},
        )
        assert resp.status_code == 200
        proposal_id = resp.json()["proposal"]["id"]

        # Warehouse picks and ships the order concurrently
        with self.session_factory() as s:
            order = s.scalar(select(OrderModel).where(OrderModel.order_id == "ORD-1001"))
            order.status = "shipped"
            raw = dict(order.raw_data or {})
            raw["status"] = "shipped"
            raw["is_cancellable"] = False
            order.raw_data = raw
            s.commit()

        # Reviewer attempts approval -> fails execution
        appr_resp = self.client.post(
            f"/reviewer/proposals/{proposal_id}/approve",
            json={"version": 1, "note": "Approving cancellation without checking warehouse"},
            headers=self.reviewer_headers,
        )
        assert appr_resp.status_code == 200
        assert appr_resp.json()["status"] == "FAILED"
        assert "stale_order" in appr_resp.json()["decision_reason"]

        # Order remains shipped
        with self.session_factory() as s:
            order = s.scalar(select(OrderModel).where(OrderModel.order_id == "ORD-1001"))
            assert order.status == "shipped"
