"""PostgreSQL Concurrency, Transactional Isolation, and OCC Stress Suite.

Runs against live PostgreSQL (aster_row_test) to verify:
1. Simultaneous approval race (10 concurrent threads): Exactly one execution, no double cancellation.
2. Optimistic Concurrency Control (OCC): Stale expected_version raises ConcurrencyConflictError.
3. Concurrent order state mutation: Race between warehouse shipment and reviewer approval.
4. Transactional atomicity and rollback on mutation failure.
5. Row-level locking serialization (with_for_update).
"""

import concurrent.futures
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import sessionmaker

from src.approvals.audit_repository import AuditRepository
from src.approvals.models import (
    ActionType,
    AuditEventModel,
    OrderModel,
    ProposalStatus,
    ProposedActionModel,
)
from src.approvals.service import (
    ApprovalService,
    ConcurrencyConflictError,
    ProposalNotFoundError,
)
from src.approvals.state_machine import InvalidTransition, ProposalEvent

POSTGRES_TEST_URL = os.getenv(
    "POSTGRES_TEST_URL", "postgresql+psycopg2://sj@localhost:5432/aster_row_test"
)


@pytest.fixture(scope="module")
def pg_engine():
    """Verify live PostgreSQL connectivity or skip."""
    try:
        engine = create_engine(POSTGRES_TEST_URL, pool_size=20, max_overflow=10)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return engine
    except Exception as exc:
        pytest.skip(f"Live PostgreSQL not reachable on {POSTGRES_TEST_URL}: {exc}")


@pytest.fixture
def pg_session_factory(pg_engine):
    """Provide scoped sessionmaker for PostgreSQL."""
    return sessionmaker(bind=pg_engine, autoflush=False, expire_on_commit=False)


@pytest.fixture
def clean_pg_db(pg_engine, pg_session_factory):
    """Clean tables before each test and re-seed baseline test orders."""
    with pg_session_factory() as session:
        session.query(AuditEventModel).delete()
        session.query(ProposedActionModel).delete()
        session.query(OrderModel).delete()
        session.commit()

        # Seed initial cancellable order ORD-1001 and non-cancellable ORD-1002
        o1 = OrderModel(
            order_id="ORD-1001",
            customer_id="CUST-401",
            status="pending",
            created_at=datetime(2026, 3, 1, 10, 0, 0, tzinfo=timezone.utc),
            updated_at=datetime(2026, 3, 1, 10, 0, 0, tzinfo=timezone.utc),
            raw_data={
                "order_id": "ORD-1001",
                "customer_id": "CUST-401",
                "status": "pending",
                "placed_at": "2026-03-01T10:00:00Z",
                "is_cancellable": True,
                "membership_tier": "standard",
                "customer": {
                    "customer_id": "CUST-401",
                    "name": "Alex Mercer",
                    "email": "alex.mercer@example.com",
                    "shipping_address": "123 Main St, Seattle, WA 98101",
                },
            },
        )
        o2 = OrderModel(
            order_id="ORD-1002",
            customer_id="CUST-402",
            status="shipped",
            created_at=datetime(2026, 3, 1, 8, 0, 0, tzinfo=timezone.utc),
            updated_at=datetime(2026, 3, 1, 8, 0, 0, tzinfo=timezone.utc),
            raw_data={
                "order_id": "ORD-1002",
                "customer_id": "CUST-402",
                "status": "shipped",
                "placed_at": "2026-03-01T08:00:00Z",
                "is_cancellable": False,
                "membership_tier": "gold",
            },
        )
        session.add_all([o1, o2])
        session.commit()

    yield pg_session_factory

    # Teardown: clean tables after test
    with pg_session_factory() as session:
        session.query(AuditEventModel).delete()
        session.query(ProposedActionModel).delete()
        session.query(OrderModel).delete()
        session.commit()


@pytest.fixture
def pg_approval_service(clean_pg_db):
    """Provide ApprovalService backed by live PostgreSQL."""
    audit_repo = AuditRepository(clean_pg_db)
    return ApprovalService(session_factory=clean_pg_db, audit_repo=audit_repo)


# ===========================================================================
# 1. Simultaneous Approval Race Test (10 Threads)
# ===========================================================================

def test_postgres_simultaneous_approval_race(clean_pg_db, pg_approval_service):
    """Verify 10 concurrent threads attempting to approve the same proposal execute exactly once."""
    prop = pg_approval_service.create_proposal(
        order_id="ORD-1001",
        session_id="sess_race_test",
        action_type=ActionType.CANCELLATION,
        evidence_snapshot={"order_id": "ORD-1001", "is_cancellable": True},
        request_id="req-race-init",
    )
    assert prop.status == ProposalStatus.PENDING_APPROVAL
    assert prop.version == 1

    num_threads = 10
    results: List[Dict[str, Any]] = []
    t0 = time.perf_counter()

    def worker_approve(worker_id: int):
        try:
            svc = ApprovalService(
                session_factory=clean_pg_db,
                audit_repo=AuditRepository(clean_pg_db),
            )
            res = svc.approve(
                proposal_id=prop.id,
                reviewer_id=f"rev_{worker_id}",
                reason=f"Concurrent approval attempt from reviewer {worker_id}",
                request_id=f"req-rev-{worker_id}",
            )
            return {"worker_id": worker_id, "status": res.status.value, "error": None}
        except Exception as e:
            return {"worker_id": worker_id, "status": "ERROR", "error": str(e)}

    with concurrent.futures.ThreadPoolExecutor(max_workers=num_threads) as executor:
        futures = [executor.submit(worker_approve, i) for i in range(num_threads)]
        for f in concurrent.futures.as_completed(futures):
            results.append(f.result())

    race_duration_ms = (time.perf_counter() - t0) * 1000

    # Strict Invariant Assertions
    # 1. All threads must successfully return EXECUTED (1 winning execution + 9 idempotent returns)
    for r in results:
        assert r["error"] is None, f"Worker {r['worker_id']} encountered unexpected error: {r['error']}"
        assert r["status"] == ProposalStatus.EXECUTED.value

    # 2. Database Verification: Order ORD-1001 must be cancelled exactly once
    with clean_pg_db() as session:
        order = session.scalar(select(OrderModel).where(OrderModel.order_id == "ORD-1001"))
        assert order is not None
        assert order.status == "cancelled"
        assert order.raw_data.get("status") == "cancelled"

        # 3. Exactly ONE execute_success audit event recorded in PostgreSQL
        audit_events = list(
            session.scalars(
                select(AuditEventModel)
                .where(AuditEventModel.proposal_id == prop.id)
                .order_by(AuditEventModel.timestamp.asc())
            ).all()
        )
        exec_events = [e for e in audit_events if e.action == "execute_success"]
        assert len(exec_events) == 1, f"Expected exactly 1 execution audit event, got {len(exec_events)}"
        assert exec_events[0].to_state == ProposalStatus.EXECUTED.value

    # Record metrics artifact
    output_dir = Path("evaluation/production_hardening_2026_11_26")
    output_dir.mkdir(parents=True, exist_ok=True)
    results_file = output_dir / "postgres_concurrency_results.json"

    data = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "database": "PostgreSQL 14.18 (localhost:5432/aster_row_test)",
        "concurrent_threads": num_threads,
        "race_duration_ms": round(race_duration_ms, 2),
        "results_summary": {
            "total_attempts": num_threads,
            "successful_executions": 1,
            "idempotent_safe_returns": num_threads - 1,
            "unhandled_errors": 0,
            "double_execution_count": 0,
            "order_cancelled_exactly_once": True,
        },
        "worker_results": results,
    }
    with open(results_file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


# ===========================================================================
# 2. Optimistic Concurrency Control (OCC) Stale Version Check
# ===========================================================================

def test_postgres_stale_version_occ_conflict(clean_pg_db, pg_approval_service):
    """Verify that submitting an outdated version raises ConcurrencyConflictError."""
    prop = pg_approval_service.create_proposal(
        order_id="ORD-1001",
        session_id="sess_occ_test",
        action_type=ActionType.CANCELLATION,
        evidence_snapshot={"order_id": "ORD-1001", "is_cancellable": True},
    )
    assert prop.version == 1

    # Client sends stale expected_version=0 or version=99
    with pytest.raises(ConcurrencyConflictError) as exc_info:
        pg_approval_service.approve(
            proposal_id=prop.id,
            reviewer_id="rev_stale",
            expected_version=99,
            reason="Attempting stale approve",
        )
    assert "Version conflict" in str(exc_info.value)
    assert "expected 99, found 1" in str(exc_info.value)

    # Verify proposal remains untouched in PENDING_APPROVAL
    fresh = pg_approval_service.get(prop.id)
    assert fresh.status == ProposalStatus.PENDING_APPROVAL
    assert fresh.version == 1


# ===========================================================================
# 3. Concurrent Order State Mutation Race (Warehouse vs Reviewer)
# ===========================================================================

def test_postgres_order_state_mutation_during_pending_approval(clean_pg_db, pg_approval_service):
    """Verify that if order becomes shipped before approval executes, execution fails safely."""
    prop = pg_approval_service.create_proposal(
        order_id="ORD-1001",
        session_id="sess_warehouse_race",
        action_type=ActionType.CANCELLATION,
        evidence_snapshot={"order_id": "ORD-1001", "is_cancellable": True},
    )
    assert prop.status == ProposalStatus.PENDING_APPROVAL

    # Simulate warehouse carrier pickup mutating order to "shipped"
    with clean_pg_db() as session:
        order = session.scalar(select(OrderModel).where(OrderModel.order_id == "ORD-1001"))
        order.status = "shipped"
        order.raw_data = {
            "order_id": "ORD-1001",
            "customer_id": "CUST-401",
            "status": "shipped",
            "placed_at": "2026-03-01T10:00:00Z",
            "is_cancellable": False,
            "carrier": "FedEx",
            "tracking_number": "TRK-999",
        }
        session.commit()

    # Reviewer approves, but atomic re-validation detects order is no longer cancellable
    approved_prop = pg_approval_service.approve(
        proposal_id=prop.id,
        reviewer_id="rev_warehouse_guard",
        reason="Approved by reviewer without knowing warehouse picked up",
    )

    # Invariant checks:
    # 1. Proposal transitions to FAILED
    assert approved_prop.status == ProposalStatus.FAILED
    assert "stale_order" in approved_prop.decision_reason

    # 2. Order remains shipped (NEVER mutated to cancelled)
    with clean_pg_db() as session:
        fresh_order = session.scalar(select(OrderModel).where(OrderModel.order_id == "ORD-1001"))
        assert fresh_order.status == "shipped"
        assert fresh_order.raw_data.get("status") == "shipped"

        # 3. Audit trail records execute_fail event
        events = list(
            session.scalars(
                select(AuditEventModel).where(AuditEventModel.proposal_id == prop.id)
            ).all()
        )
        fail_events = [e for e in events if e.action == "execute_fail"]
        assert len(fail_events) == 1
        assert fail_events[0].to_state == ProposalStatus.FAILED.value


# ===========================================================================
# 4. Atomic Transaction Rollback on Mid-Execution Crash
# ===========================================================================

def test_postgres_atomic_transaction_rollback_on_failure(clean_pg_db, pg_approval_service, monkeypatch):
    """Verify that an unexpected exception during execution aborts transaction atomically."""
    prop = pg_approval_service.create_proposal(
        order_id="ORD-1001",
        session_id="sess_rollback_test",
        action_type=ActionType.CANCELLATION,
        evidence_snapshot={"order_id": "ORD-1001", "is_cancellable": True},
    )

    # Monkeypatch session.commit to simulate network partition or db crash on final commit
    from sqlalchemy.orm import Session
    original_commit = Session.commit

    def crashing_commit(self):
        # Crash only if this session has pending changes
        if self.new or self.dirty:
            raise RuntimeError("SIMULATED_DATABASE_IO_ERROR_DURING_COMMIT")
        return original_commit(self)

    monkeypatch.setattr(Session, "commit", crashing_commit)

    with pytest.raises(RuntimeError) as exc_info:
        pg_approval_service.approve(
            proposal_id=prop.id,
            reviewer_id="rev_crash_tester",
            reason="Testing rollback",
        )
    assert "SIMULATED_DATABASE_IO_ERROR_DURING_COMMIT" in str(exc_info.value)

    # Restore commit and verify complete atomicity
    monkeypatch.undo()

    with clean_pg_db() as session:
        persisted_prop = session.scalar(
            select(ProposedActionModel).where(ProposedActionModel.id == prop.id)
        )
        assert persisted_prop.status == ProposalStatus.PENDING_APPROVAL
        assert persisted_prop.version == 1

        persisted_order = session.scalar(
            select(OrderModel).where(OrderModel.order_id == "ORD-1001")
        )
        assert persisted_order.status == "pending"

        # No orphaned approved/executed audit events
        audit_events = list(
            session.scalars(
                select(AuditEventModel).where(AuditEventModel.proposal_id == prop.id)
            ).all()
        )
        assert not any(e.action in ("approve", "execute_success") for e in audit_events)


# ===========================================================================
# 5. Row-Level Locking Verification (with_for_update)
# ===========================================================================

def test_postgres_row_level_locking_with_for_update(clean_pg_db, pg_approval_service):
    """Verify PostgreSQL select(...).with_for_update() blocks concurrent session until commit."""
    prop = pg_approval_service.create_proposal(
        order_id="ORD-1001",
        session_id="sess_lock_test",
        action_type=ActionType.CANCELLATION,
        evidence_snapshot={"order_id": "ORD-1001", "is_cancellable": True},
    )

    lock_acquired_time = None
    lock_released_time = None
    concurrent_lock_attempt_time = None

    def holding_session_worker():
        nonlocal lock_acquired_time, lock_released_time
        with clean_pg_db() as session:
            stmt = select(ProposedActionModel).where(ProposedActionModel.id == prop.id).with_for_update()
            p = session.scalar(stmt)
            lock_acquired_time = time.perf_counter()
            # Hold lock for 300ms
            time.sleep(0.3)
            p.version += 1
            session.commit()
            lock_released_time = time.perf_counter()

    def competing_session_worker():
        nonlocal concurrent_lock_attempt_time
        # Wait 50ms so holding worker definitely acquires lock first
        time.sleep(0.05)
        t_start = time.perf_counter()
        with clean_pg_db() as session:
            stmt = select(ProposedActionModel).where(ProposedActionModel.id == prop.id).with_for_update()
            p = session.scalar(stmt)
            concurrent_lock_attempt_time = time.perf_counter()
            session.commit()
            return concurrent_lock_attempt_time - t_start

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        f1 = executor.submit(holding_session_worker)
        f2 = executor.submit(competing_session_worker)
        f1.result()
        competing_wait_s = f2.result()

    # Invariant: Competing worker was blocked until holding worker released the row lock
    assert lock_acquired_time is not None
    assert lock_released_time is not None
    assert concurrent_lock_attempt_time is not None
    # Competing worker acquired lock AFTER holding worker committed
    assert concurrent_lock_attempt_time >= lock_released_time
    assert competing_wait_s >= 0.20, f"Expected competing session to wait at least 200ms, waited {competing_wait_s:.3f}s"
