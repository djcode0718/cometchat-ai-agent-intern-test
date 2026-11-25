"""Comprehensive test suite for Human-in-the-Loop (HITL) approval workflows.

Tests:
1. Pure State Machine transitions (legal vs illegal matrix).
2. Optimistic concurrency locking (version match vs 409).
3. Double approve, approve after reject, approve after expiry.
4. Stale order detection: status changes after proposal, resulting in FAILED and no order mutation.
5. Reviewer authentication matrix (missing key, invalid key, valid key).
6. Customer session isolation (cannot access other session's proposal).
7. Audit immutability (proves no update or delete method exists).
8. Language safety: agent states "submitted for review" and validator blocks premature claims.
"""

from datetime import datetime, timezone
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.api import app
from src.approvals.audit_repository import AuditRepository
from src.approvals.clock import FakeClock
from src.approvals.models import (
    ActionType,
    Base,
    OrderModel,
    ProposalStatus,
    ProposedActionModel,
)
from src.approvals.service import (
    ApprovalService,
    ConcurrencyConflictError,
    ProposalNotFoundError,
)
from src.approvals.sql_repository import SqlOrderRepository
from src.approvals.state_machine import (
    InvalidTransition,
    ProposalEvent,
    is_terminal,
    transition,
)
from src.llm.models import GroundedGenerationRequest
from src.llm.validator import OutputValidator
from src.tools.order_models import CustomerSafeOrder


@pytest.fixture
def in_memory_db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    return session_factory


@pytest.fixture
def fake_clock():
    return FakeClock(datetime(2026, 3, 1, 12, 0, 0, tzinfo=timezone.utc))


@pytest.fixture
def approval_service(in_memory_db, fake_clock):
    audit_repo = AuditRepository(in_memory_db)
    return ApprovalService(session_factory=in_memory_db, audit_repo=audit_repo, clock=fake_clock)


@pytest.fixture
def seed_orders(in_memory_db):
    with in_memory_db() as session:
        o1 = OrderModel(
            order_id="ORD-1001",
            customer_id="CUST-001",
            status="pending",
            created_at=datetime(2026, 3, 1, 10, 0, 0, tzinfo=timezone.utc),
            updated_at=datetime(2026, 3, 1, 10, 0, 0, tzinfo=timezone.utc),
            raw_data={"order_id": "ORD-1001", "status": "pending", "placed_at": "2026-03-01T10:00:00Z", "is_cancellable": True},
        )
        o2 = OrderModel(
            order_id="ORD-1003",
            customer_id="CUST-003",
            status="shipped",
            created_at=datetime(2026, 2, 28, 9, 0, 0, tzinfo=timezone.utc),
            updated_at=datetime(2026, 3, 1, 8, 0, 0, tzinfo=timezone.utc),
            raw_data={"order_id": "ORD-1003", "status": "shipped", "placed_at": "2026-02-28T09:00:00Z", "is_cancellable": False},
        )
        session.add_all([o1, o2])
        session.commit()


# ---------------------------------------------------------------------------
# 1. State Machine Tests (Parametrized over states and events)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "from_state,event,expected_state",
    [
        (ProposalStatus.PENDING_APPROVAL, ProposalEvent.APPROVE, ProposalStatus.APPROVED),
        (ProposalStatus.PENDING_APPROVAL, ProposalEvent.REJECT, ProposalStatus.REJECTED),
        (ProposalStatus.PENDING_APPROVAL, ProposalEvent.EXPIRE, ProposalStatus.EXPIRED),
        (ProposalStatus.APPROVED, ProposalEvent.EXECUTE_SUCCESS, ProposalStatus.EXECUTED),
        (ProposalStatus.APPROVED, ProposalEvent.EXECUTE_FAIL, ProposalStatus.FAILED),
    ],
)
def test_legal_state_transitions(from_state, event, expected_state):
    assert transition(from_state, event) == expected_state


@pytest.mark.parametrize(
    "from_state,event",
    [
        (ProposalStatus.REJECTED, ProposalEvent.APPROVE),
        (ProposalStatus.EXPIRED, ProposalEvent.APPROVE),
        (ProposalStatus.EXECUTED, ProposalEvent.APPROVE),
        (ProposalStatus.FAILED, ProposalEvent.APPROVE),
        (ProposalStatus.PENDING_APPROVAL, ProposalEvent.EXECUTE_SUCCESS),
        (ProposalStatus.APPROVED, ProposalEvent.REJECT),
    ],
)
def test_illegal_state_transitions_raise(from_state, event):
    with pytest.raises(InvalidTransition):
        transition(from_state, event)


# ---------------------------------------------------------------------------
# 2. Concurrency & Replay Tests
# ---------------------------------------------------------------------------

def test_optimistic_concurrency_conflict(approval_service, seed_orders):
    prop = approval_service.create_proposal(
        order_id="ORD-1001",
        session_id="sess_test",
        action_type=ActionType.CANCELLATION,
        evidence_snapshot={"order_id": "ORD-1001", "is_cancellable": True},
    )
    assert prop.version == 1

    # Stale expected_version
    with pytest.raises(ConcurrencyConflictError):
        approval_service.approve(prop.id, reviewer_id="reviewer1", expected_version=99)


def test_double_approve_is_idempotent_noop(approval_service, seed_orders):
    prop = approval_service.create_proposal(
        order_id="ORD-1001",
        session_id="sess_test",
        action_type=ActionType.CANCELLATION,
        evidence_snapshot={"order_id": "ORD-1001", "is_cancellable": True},
    )
    p1 = approval_service.approve(prop.id, reviewer_id="reviewer1")
    assert p1.status == ProposalStatus.EXECUTED

    # Second approve call should return proposal without error or second mutation
    p2 = approval_service.approve(prop.id, reviewer_id="reviewer1")
    assert p2.status == ProposalStatus.EXECUTED


def test_approve_after_reject_raises(approval_service, seed_orders):
    prop = approval_service.create_proposal(
        order_id="ORD-1001",
        session_id="sess_test",
        action_type=ActionType.CANCELLATION,
        evidence_snapshot={"order_id": "ORD-1001", "is_cancellable": True},
    )
    approval_service.reject(prop.id, reviewer_id="reviewer1", reason="Valid rejection reason 12345")

    with pytest.raises(InvalidTransition):
        approval_service.approve(prop.id, reviewer_id="reviewer1")


def test_approve_after_expiry_raises(approval_service, seed_orders, fake_clock):
    prop = approval_service.create_proposal(
        order_id="ORD-1001",
        session_id="sess_test",
        action_type=ActionType.CANCELLATION,
        evidence_snapshot={"order_id": "ORD-1001", "is_cancellable": True},
        ttl_hours=2,
    )
    # Advance clock past TTL
    fake_clock.advance(hours=3)

    with pytest.raises(InvalidTransition):
        approval_service.approve(prop.id, reviewer_id="reviewer1")


# ---------------------------------------------------------------------------
# 3. Stale Order Safety Execution
# ---------------------------------------------------------------------------

def test_stale_order_fails_execution_without_mutation(approval_service, in_memory_db, seed_orders):
    prop = approval_service.create_proposal(
        order_id="ORD-1001",
        session_id="sess_test",
        action_type=ActionType.CANCELLATION,
        evidence_snapshot={"order_id": "ORD-1001", "is_cancellable": True},
    )

    # Order status changes in warehouse before reviewer acts
    with in_memory_db() as session:
        order = session.query(OrderModel).filter_by(order_id="ORD-1001").first()
        order.status = "shipped"
        order.raw_data = {"order_id": "ORD-1001", "status": "shipped", "is_cancellable": False}
        session.commit()

    # Reviewer approves, but atomic execution detects order is stale
    result = approval_service.approve(prop.id, reviewer_id="reviewer1")
    assert result.status == ProposalStatus.FAILED
    assert "stale_order" in result.decision_reason

    # Verify order was NOT cancelled
    with in_memory_db() as session:
        order = session.query(OrderModel).filter_by(order_id="ORD-1001").first()
        assert order.status == "shipped"


# ---------------------------------------------------------------------------
# 4. Audit Immutability Test
# ---------------------------------------------------------------------------

def test_audit_repository_has_no_mutating_methods(in_memory_db):
    audit_repo = AuditRepository(in_memory_db)
    forbidden_methods = ["update", "delete", "remove", "clear", "modify", "drop"]
    for method_name in forbidden_methods:
        assert not hasattr(audit_repo, method_name), f"AuditRepository exposes forbidden mutable method '{method_name}'"


def test_audit_completeness_per_transition(approval_service, seed_orders):
    prop = approval_service.create_proposal(
        order_id="ORD-1001",
        session_id="sess_test",
        action_type=ActionType.CANCELLATION,
        evidence_snapshot={"order_id": "ORD-1001"},
        request_id="req-123456",
    )
    approval_service.approve(prop.id, reviewer_id="reviewer_alice", request_id="req-789012")

    events = approval_service.audit_repo.list_events(proposal_id=prop.id)
    assert len(events) >= 3  # create_proposal, approve, execute_success
    actions = [e.action for e in events]
    assert "create_proposal" in actions
    assert "approve" in actions
    assert "execute_success" in actions


# ---------------------------------------------------------------------------
# 5. Language Safety & Premature Completion Validator Tests
# ---------------------------------------------------------------------------

def test_validator_rejects_premature_cancellation_claims():
    from src.core.models import DecisionState

    req = GroundedGenerationRequest(
        user_query="Please cancel my order ORD-1001",
        decision_state=DecisionState.ANSWER,
        decision_reason="Order eligible for review",
        proposal_info={"id": "prop_123", "status": "PENDING_APPROVAL"},
    )

    # Violating claim: asserts cancellation has already happened
    premature_text = "I have cancelled your order ORD-1001 and your refund has been processed."
    val = OutputValidator.validate(premature_text, req)
    assert val.is_valid is False
    assert any("claimed an action completion" in v.lower() for v in val.violations)

    # Compliant claim: states submitted for review
    compliant_text = "Your cancellation request for order ORD-1001 has been submitted for review (reference: prop_123)."
    val2 = OutputValidator.validate(compliant_text, req)
    assert val2.is_valid is True


# ---------------------------------------------------------------------------
# 6. HTTP API Reviewer Auth & Tenant Isolation Tests
# ---------------------------------------------------------------------------

def test_api_reviewer_auth_matrix():
    client = TestClient(app)

    # 1. Missing header -> 401
    res = client.get("/reviewer/proposals")
    assert res.status_code == 401

    # 2. Bad key -> 401
    res = client.get("/reviewer/proposals", headers={"X-Reviewer-Key": "invalid_wrong_key"})
    assert res.status_code == 401

    # 3. Valid key -> 200
    res = client.get("/reviewer/proposals", headers={"X-Reviewer-Key": "secret_admin_key_123"})
    assert res.status_code == 200


def test_customer_tenant_isolation_blocks_cross_session_reading():
    client = TestClient(app)

    # Create proposal under session_legit
    res_chat = client.post("/chat", json={"message": "Please cancel my order ORD-1001", "session_id": "session_legit"})
    assert res_chat.status_code == 200

    # Legit customer fetches their own proposal
    res_own = client.get("/sessions/session_legit/proposal")
    assert res_own.status_code == 200
    assert res_own.json()["order_id"] == "ORD-1001"

    # Attacker tries to read without knowing or with wrong session_id
    res_attacker = client.get("/sessions/session_attacker/proposal")
    assert res_attacker.status_code == 404
