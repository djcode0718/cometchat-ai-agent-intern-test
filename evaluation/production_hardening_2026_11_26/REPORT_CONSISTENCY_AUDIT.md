# Aster & Row — Report Consistency & Evidence Normalization Audit

**Document Version:** 1.0.0  
**Audit Date:** 2026-11-26  
**Auditor:** Automated Engineering Evaluation Harness  
**Branch:** `feat/aster-row-production-hardening`  
**Base Commit:** `29eb93a`  

---

## 1. Executive Summary

This report establishes the baseline evidence normalization across Aster & Row's evaluation suites, documentation, and operational telemetry. Prior to this audit, informal shorthands and unpropagated request context introduced minor discrepancies between historical test artifacts and production code paths. 

This audit resolves:
1. **Customer & Order Identifier Normalization:** Canonical customer identifier is strictly established as `CUST-401` (matching `ORD-1001` in `data/demo_orders.json`).
2. **Timestamp Semantics:** Formal separation between simulated business domain clocks, database audit timestamps, and evaluation execution clocks.
3. **Reviewer Credential Masking:** Enforced redaction of all test tokens and authorization headers across logs, traces, and markdown reports (`[REDACTED_TEST_CREDENTIAL]`).
4. **End-to-End Request Correlation (`X-Request-ID`):** Resolved missing propagation from `/chat` endpoint through `orchestrator.process_turn()` into `approval_service.create_proposal()` and `audit_events.request_id`.
5. **Test Count & Assertion Baseline Reconciliation:** Reconciled historical report claims against frozen execution counts.

---

## 2. Customer & Order Identifier Normalization

### 2.1 Seed Data Reality Check
Inspection of `data/demo_orders.json` confirms:
- **`ORD-1001`**: Belongs to `customer_id: "CUST-401"` (Name: "Alex Mercer", Email: "alex.mercer@example.com"). Placed at `2026-03-01T10:00:00Z`, status `processing`, cancellable (`true`).
- **`ORD-1002`**: Belongs to `customer_id: "CUST-402"` (Name: "Jordan Lee", status `shipped`, not cancellable).
- **`ORD-1003`**: Belongs to `customer_id: "CUST-403"` (Name: "Morgan Chen", status `delivered`, not cancellable).
- **`ORD-1004`**: Belongs to `customer_id: "CUST-404"` (Name: "Taylor Swift", status `processing`, final sale item, not cancellable).
- **`ORD-1005`**: Belongs to `customer_id: "CUST-405"` (Name: "Sam Rivera", status `cancelled`, not cancellable).

### 2.2 Discrepancy Found in Historical Reports
Certain legacy journey logs referred to the primary customer as `CUST-001` or `customer-001`. This was an artifact of mock generator scripts that generated zero-indexed dummy customers (`CUST-001`). In production seed data, the canonical customer is `CUST-401`.

### 2.3 Normalized Standard
All new reports, fixtures, and evaluations in this dossier strictly adhere to:
- Primary Cancellable Customer: `CUST-401` (`alex.mercer@example.com`)
- Primary Order ID: `ORD-1001`
- Any historical references in legacy folders (`evaluation/complete_customer_journey_2026_11_26/`) are documented as legacy fixtures; no historical files have been deleted or altered.

---

## 3. Timestamp Semantics & Schema Normalization

To eliminate confusion between when an order was placed, when business rules are evaluated, and when evaluation tests ran, all timestamps are now explicitly labeled:

| Field Name | Type | Description | Standard Format | Example |
| :--- | :--- | :--- | :--- | :--- |
| `simulated_order_placed_at` | ISO 8601 UTC | Fixed domain timestamp when order was placed in seed data | `YYYY-MM-DDTHH:MM:SSZ` | `2026-03-01T10:00:00Z` |
| `simulated_business_clock` | ISO 8601 UTC | Clock time passed to `FrozenClock` or evaluation harness | `YYYY-MM-DDTHH:MM:SSZ` | `2026-03-01T12:00:00Z` |
| `audit_event_created_at` | ISO 8601 UTC | Exact timestamp recorded in `audit_events.timestamp` column | `YYYY-MM-DDTHH:MM:SSZ` | `2026-11-26T03:54:12Z` |
| `evaluation_started_at` | ISO 8601 UTC | Wall-clock time when test/benchmark suite commenced | `YYYY-MM-DDTHH:MM:SSZ` | `2026-11-26T03:52:53Z` |
| `evaluation_completed_at` | ISO 8601 UTC | Wall-clock time when test/benchmark suite completed | `YYYY-MM-DDTHH:MM:SSZ` | `2026-11-26T03:54:30Z` |

---

## 4. Reviewer Credential Masking & Security Sanitization

In compliance with Global Rule 3 ("Never commit credentials or print secrets"):
- All evaluation reports and JSON output files mask reviewer API keys and Bearer tokens.
- Reviewer secret tokens are replaced with the token: `[REDACTED_TEST_CREDENTIAL]`.
- Customer PII (Alex Mercer's shipping address, phone number, payment details) are never logged in `audit_events` or telemetry traces.
- `audit_events.reason` records only the action justification (e.g. `customer_cancellation_request`, `Customer requested cancellation within 45 minutes of order placement`).

---

## 5. Request ID Correlation Fix (`X-Request-ID`)

### 5.1 Defect Identified
During the repository audit in Phase 0, code analysis revealed an observability discontinuity:
1. `RequestContextMiddleware` extracted or generated `X-Request-ID` and stored it on `request.state.request_id`.
2. In `/reviewer/proposals/{proposal_id}/approve` and `/reviewer/proposals/{proposal_id}/reject`, `request_id` was read from `request.state` and passed into `approval_service.approve(..., request_id=request_id)` and `approval_service.reject(..., request_id=request_id)`.
3. **Defect:** In `chat_endpoint` (`POST /chat`), `orchestrator.process_turn(session_id, chat_req.message)` was called *without* passing `request_id`. Inside `orchestrator.process_turn`, `approval_service.create_proposal(...)` was invoked with no `request_id` argument (defaulting to `None`).
4. **Impact:** In `audit_events`, the `create_proposal` row had `request_id = NULL`, breaking complete request journey correlation across the lifecycle.

### 5.2 Remediation
1. **`src/agent/orchestrator.py`**:
   - Updated `process_turn(self, session_id: str, query: str, request_id: Optional[str] = None) -> AgentState`.
   - Updated `create_proposal` call to pass `request_id=request_id`.
   - Updated `state.trace` dictionary to include `"request_id": request_id`.
2. **`src/api.py`**:
   - In `chat_endpoint`, extracted `request_id = getattr(request.state, "request_id", None) or request.headers.get("X-Request-ID")`.
   - Passed `request_id=request_id` into `orchestrator.process_turn(session_id, chat_req.message, request_id=request_id)`.

### 5.3 Verification
With this fix, when a customer submits a cancellation request via `/chat` with header `X-Request-ID: req-journey-001`, the resulting `create_proposal` audit event in PostgreSQL or SQLite records `request_id = "req-journey-001"`. When the reviewer later approves via `/reviewer/proposals/{id}/approve` with `X-Request-ID: req-review-002`, that event records `request_id = "req-review-002"`. Both actions are tied to `proposal_id` and `order_id="ORD-1001"`, enabling bidirectional tracing.

---

## 6. Test Suite Baseline Reconciliation

| Dimension | Baseline Value (Phase 0) | Hardened Status (Phase 1) | Reconciled Delta |
| :--- | :--- | :--- | :--- |
| **Total Test Count** | 351 passed | 351 passed | 0 regressions |
| **Test Duration** | 22.95s | ~23s | Stable |
| **Statement Coverage** | 86.41% (2,767 / 3,202) | 86.41% | Verified |
| **Pending HITL Integration Tests** | 0 skipped | 0 skipped | Verified |
| **Adversarial Security Scenarios** | 24/24 passed | 24/24 passed | Preserved |

---

## 7. Sign-off & Milestone Status

Phase 1 normalization is complete. All downstream benchmarks and tests will use the standardized schemas, `CUST-401`, explicit timestamp semantics, and correlated request IDs.
