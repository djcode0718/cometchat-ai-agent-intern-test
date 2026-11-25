# Observability, Structured Telemetry & Audit Integrity Report

**Evaluation Artifact**: `evaluation/complete_customer_journey_2026_11_26/OBSERVABILITY_REPORT.md`  
**Raw Source**: `evaluation/complete_customer_journey_2026_11_26/observability_results.json`  
**Observability Middleware**: `src/observability/request_context.py`  
**Logging Framework**: `structlog` (JSON output with ISO-8601 UTC timestamps)  
**Metrics Framework**: `prometheus_client` exposing standard Prometheus scrapes on `/metrics`

---

## 1. Structured Logging Specification & Schema

All log events emitted by Aster & Row conform to an invariant JSON schema designed for ingestion by modern log analytics platforms (Datadog, Grafana Loki, CloudWatch).

### Mandatory Top-Level Log Fields:
- `timestamp`: ISO-8601 UTC format (`YYYY-MM-DDTHH:MM:SS.ffffffZ`).
- `level`: Log severity (`info`, `warning`, `error`, `critical`).
- `logger`: Subsystem origin (`http_access`, `orchestrator`, `approvals.service`, `approvals.auth`).
- `event`: Standardized snake_case semantic event identifier.
- `request_id`: UUID or caller-supplied correlation token propagated across all child operations.

### Representative Correlated Journey Log Events

#### 1. Customer Chat Turn Finished (`http_access`)
```json
{
  "timestamp": "2026-11-25T21:07:14.492968Z",
  "level": "info",
  "logger": "http_access",
  "event": "http_request_finished",
  "request_id": "req-cust-04119711",
  "method": "POST",
  "route": "/chat",
  "status": 200,
  "latency_ms": 9.75
}
```

#### 2. Action Proposal Created (`approvals.service`)
```json
{
  "timestamp": "2026-11-25T21:07:14.493405Z",
  "level": "info",
  "logger": "approvals.service",
  "event": "proposal_created",
  "request_id": "req-cust-04119711",
  "proposal_id": "prop_f2a9f4e05b56",
  "order_id": "ORD-1001",
  "action_type": "CANCELLATION",
  "status": "PENDING_APPROVAL",
  "version": 1
}
```

#### 3. Security Guard Attack Neutralization (`orchestrator`)
```json
{
  "timestamp": "2026-11-25T21:05:29.977199Z",
  "level": "warning",
  "logger": "orchestrator",
  "event": "security_guard_triggered",
  "request_id": "req-sec-13-163cc6",
  "guard_category": "instruction_override",
  "query_length": 68
}
```

#### 4. Reviewer Authentication Failure (`approvals.auth`)
```json
{
  "timestamp": "2026-11-25T21:05:29.932247Z",
  "level": "warning",
  "logger": "approvals.auth",
  "event": "reviewer_auth_failed",
  "request_id": "req-app-02-e93aef",
  "reason": "invalid_key"
}
```

#### 5. Proposal Approved and Order Mutated (`approvals.service`)
```json
{
  "timestamp": "2026-11-25T21:07:14.510277Z",
  "level": "info",
  "logger": "approvals.service",
  "event": "proposal_approved_and_executed",
  "request_id": "req-rev-appr-77403d25",
  "proposal_id": "prop_f2a9f4e05b56",
  "order_id": "ORD-1001",
  "reviewer_id": "admin",
  "previous_status": "PENDING_APPROVAL",
  "final_status": "EXECUTED",
  "version": 3
}
```

---

## 2. Prometheus Metrics Inventory & Delta Verification

Aster & Row exposes Prometheus metrics on `/metrics`. Below is the live verification delta captured during the end-to-end journey execution:

| Prometheus Metric Name | Type | Labels | Baseline Value | Final Value | Net Delta |
|---|---|---|---|---|---|
| `approval_proposals_created_total` | Counter | `action_type="CANCELLATION"` | 0 | 1 | **+1** |
| `approval_proposals_executed_total` | Counter | `action_type="CANCELLATION"` | 0 | 1 | **+1** |
| `cancellation_requests_submitted_total`| Counter | `none` | 0 | 1 | **+1** |
| `http_requests_total` | Counter | `route="/chat", status="200"` | 0 | 1 | **+1** |
| `http_requests_total` | Counter | `route="/reviewer/proposals/{proposal_id}/approve", status="200"` | 0 | 2 | **+2** |
| `http_request_duration_seconds` | Histogram | `route="/chat"` | — | — | Recorded |
| `security_injections_blocked_total` | Counter | `category="instruction_override"` | 0 | 2 | **+2** |
| `security_injections_blocked_total` | Counter | `category="approval_spoofing"` | 0 | 1 | **+1** |
| `security_injections_blocked_total` | Counter | `category="prompt_exfiltration"` | 0 | 1 | **+1** |

---

## 3. Customer-Facing Trace Sanitization

The `/sessions/{session_id}/trace` endpoint allows clients and internal operators to inspect the execution pipeline of the last turn while guaranteeing zero sensitive customer data leakage:

```json
{
  "session_id": "journey-cust-e32d4ba1",
  "turn_id": 1,
  "route": "ORDER",
  "intent": "cancellation",
  "decision_state": "ANSWER",
  "decision_reason": "Order ORD-1001 eligible for review; proposal created",
  "is_fallback": false,
  "fallback_reason": null,
  "citations": [
    "01-cancellation-policy.md > Standard Order Cancellation"
  ],
  "stage_timings_ms": {
    "routing": 0.01,
    "retrieval": 3.85,
    "generation": 0.06,
    "validation": 0.0
  },
  "proposal_id": "prop_f2a9f4e05b56"
}
```

### PII & Secret Leakage Verification Results:
- Customer Email Addresses Scanned: 0 leaks detected.
- Customer Physical Street Addresses Scanned: 0 leaks detected.
- API Secrets & Tokens Scanned: 0 leaks detected.
- Internal Fraud Risk Scores Scanned: 0 leaks detected.
- Internal Warehouse Operational Notes Scanned: 0 leaks detected.
- **Overall Leak Rate**: **0.0% (0 / 50 inspected responses)**.
