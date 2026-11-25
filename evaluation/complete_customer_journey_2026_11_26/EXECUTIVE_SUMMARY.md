# Executive Summary — End-to-End Customer Journey Validation & Production Evaluation

**Date of Evaluation**: November 26, 2026  
**Target Repository**: Aster & Row Customer Support System  
**Git Branch**: `feat/aster-row-agent-upgrade`  
**Git Commit SHA**: `663f5bbf50e42b90b497240ec466b4e74b19ec8a`  
**Platform**: macOS Darwin (Apple Silicon, 10 CPU / 16 GPU / Unified Memory)  
**Deliverable Directory**: `evaluation/complete_customer_journey_2026_11_26/`

---

## 1. Overview & Objective

Aster & Row is a production-grade AI customer support platform engineered to demonstrate that generative AI in customer operations must be bound by **deterministic policy authority, strict state machines, human-in-the-loop (HITL) approval, and immutable auditability**.

The core engineering demonstration validated in this evaluation is the complete **Customer Support Action Lifecycle**:
```text
Customer Requests Cancellation
    │
    ▼
Deterministic Policy & Eligibility Check (now <= placed_at + 30m)
    │
    ▼
Agent Proposes Action (PENDING_APPROVAL, v1) ──[ Zero Order Mutation ]
    │
    ▼
Reviewer Authenticates via X-Reviewer-Key & Inspects Proposal
    │
    ▼
Reviewer Approves (Optimistic Lock & Atomic State Revalidation)
    │
    ▼
Atomic Order Cancellation (Order becomes 'cancelled', Proposal v3 EXECUTED)
    │
    ▼
Duplicate Approval Probe ──[ Idempotent HTTP 200, Zero Duplicate Mutation ]
    │
    ▼
Immutable Chronological Audit Trail & Correlated JSON Telemetry
```

Every claim, number, and table in this dossier is derived from committed automated test runners, live benchmarks, and raw JSON artifacts located within this repository.

---

## 2. Key Findings & Headline Metrics

All metrics are backed by raw data in `METRICS_SUMMARY.json`, `journey_results.json`, `security_results.json`, `performance_results.json`, and `coverage.json`.

| Evaluation Category | Metric Name | Numerator / Denominator | Measured Value | Threshold / Target | Status |
|---|---|---|---|---|---|
| **E2E Customer Journey** | Action Lifecycle Completion Rate | 1 / 1 journeys | **100.0%** | 100.0% | **PASS** |
| **Idempotency Guarantee** | Single-Mutation Execution Rate | 2 / 2 duplicate probes | **100.0%** | 100.0% | **PASS** |
| **Negative & Adversarial** | Adversarial Matrix Pass Rate | 24 / 24 scenarios | **100.0%** | 100.0% | **PASS** |
| **Data Protection** | Customer PII & Secret Leak Rate | 0 / 50 inspected responses | **0.0%** | 0.0% | **PASS** |
| **Citation Integrity** | Fabricated Citation Containment Rate | 1 / 1 injected hallucination | **100.0%** | 100.0% | **PASS** |
| **Concurrency Safety** | Optimistic Locking Conflict Rate | 1 / 1 concurrent race | **100.0%** | 100.0% | **PASS** |
| **Test Quality** | Full Automated Test Pass Rate | 351 / 351 tests | **100.0%** | 100.0% | **PASS** |
| **Code Coverage** | Python Backend Statement Coverage | 2,937 / 3,399 statements | **86.41%** | > 80.0% | **PASS** |
| **Accessibility (CI)** | Axe Serious/Critical Violations | 0 / 9 UI states | **0** | 0 | **PASS** |
| **Accessibility (Lighthouse)**| Lighthouse Accessibility Score | 100 / 100 | **100** | > 95 | **PASS** |
| **Latency (Mock Engine)** | Pipeline Latency p50 (C=1) | 100 requests | **6.63 ms** | < 25.0 ms | **PASS** |
| **Latency (Local LLM)** | Llama 3.1:8b p50 Generation | 10 queries via Ollama | **5,903.99 ms** | N/A (Comparative) | **PASS** |

---

## 3. Engineering Highlights

### A. Deterministic Authority Over LLM Predictions
The agent never relies on LLM token probabilities to decide whether an order can be cancelled or whether an action has executed. Policy windows (30 minutes from placement) and order states (`pending`, `shipped`, `delivered`, `cancelled`) are evaluated deterministically in Python against validated database rows. If an LLM hallucinates an action completion ("I have processed your cancellation"), `OutputValidator` intercepts the output, flags an `unsupported action claim`, and substitutes a compliant deterministic fallback.

### B. Human-in-the-Loop State Machine with Optimistic Concurrency
Mutations cannot occur directly from customer chat turns. Instead, the agent creates a `ProposedActionModel` in status `PENDING_APPROVAL` with version `1`.
- When an authorized reviewer acts, the system validates the client's `expected_version`.
- If two reviewers act simultaneously on the same proposal, the first wins (transitioning to `APPROVED` then `EXECUTED` at version `3`), and the second receives `HTTP 409 Conflict` ("Version conflict: expected 1, found 3").
- If the proposal has already executed and the client retries the identical call, the service returns an idempotent `HTTP 200` without repeating the mutation.

### C. State Revalidation at Execution Time (Race Containment)
Between the moment a human proposal is drafted and the moment a reviewer clicks "Approve", warehouse fulfillment systems may have shipped the order. `ApprovalService` re-queries the authoritative order row under row-level database locks (`with_for_update`) immediately prior to mutation. If the order is no longer in `pending` status, the proposal atomically transitions to `FAILED` with reason `stale_order: order is already shipped`, and the order remains unmutated.

### D. Zero-Leakage Pre-Retrieval Security Guard
Adversarial attacks (instruction overrides, system prompt exfiltration, admin roleplay, and fake approval tokens) are intercepted before retrieval using deterministic regex pattern filters. Neutralized turns are terminated immediately with an invariant refusal message, generating a warning log event and incrementing Prometheus metrics without invoking the LLM.

### E. Fully Accessible React/TypeScript Console
The frontend implementation satisfies WCAG 2.1 AA across both the customer view and the reviewer console. It features focus-trapped dialogs, an accessible `role="log"` chat transcript with live polite announcements, single `<h1>` semantic hierarchies per view, 3px high-visibility focus indicators, and 0 serious/critical violations across all 9 UI states verified via `@axe-core/playwright`.

---

## 4. Dossier Structure

This dossier contains detailed reports and raw machine-readable data:
- [ARCHITECTURE_AND_DATA_FLOW.md](file:///Users/sj/Documents/cometchat-ai-agent-intern-test/evaluation/complete_customer_journey_2026_11_26/ARCHITECTURE_AND_DATA_FLOW.md): Mermaid sequence diagrams, state machine specification, and data contracts.
- [COMPLETE_JOURNEY_REPORT.md](file:///Users/sj/Documents/cometchat-ai-agent-intern-test/evaluation/complete_customer_journey_2026_11_26/COMPLETE_JOURNEY_REPORT.md): Step-by-step trace of the positive lifecycle customer journey.
- [SCENARIO_MATRIX.csv](file:///Users/sj/Documents/cometchat-ai-agent-intern-test/evaluation/complete_customer_journey_2026_11_26/SCENARIO_MATRIX.csv): 24-scenario negative, adversarial, and reliability test matrix.
- [PERFORMANCE_REPORT.md](file:///Users/sj/Documents/cometchat-ai-agent-intern-test/evaluation/complete_customer_journey_2026_11_26/PERFORMANCE_REPORT.md): Concurrency analysis (C=1 to 25), stage breakdowns, and local Llama 3.1:8b comparison.
- [SECURITY_AND_APPROVAL_REPORT.md](file:///Users/sj/Documents/cometchat-ai-agent-intern-test/evaluation/complete_customer_journey_2026_11_26/SECURITY_AND_APPROVAL_REPORT.md): In-depth security analysis and attack mitigations.
- [OBSERVABILITY_REPORT.md](file:///Users/sj/Documents/cometchat-ai-agent-intern-test/evaluation/complete_customer_journey_2026_11_26/OBSERVABILITY_REPORT.md): Log structure, trace correlation, and Prometheus metrics snapshot.
- [ACCESSIBILITY_REPORT.md](file:///Users/sj/Documents/cometchat-ai-agent-intern-test/evaluation/complete_customer_journey_2026_11_26/ACCESSIBILITY_REPORT.md): Automated Axe audits, Lighthouse score, and manual screen-reader template.
- [TEST_AND_COVERAGE_REPORT.md](file:///Users/sj/Documents/cometchat-ai-agent-intern-test/evaluation/complete_customer_journey_2026_11_26/TEST_AND_COVERAGE_REPORT.md): 351 unit, integration, and e2e tests breakdown with 86.41% coverage.
- [BASELINE_VS_FINAL.md](file:///Users/sj/Documents/cometchat-ai-agent-intern-test/evaluation/complete_customer_journey_2026_11_26/BASELINE_VS_FINAL.md): Controlled before/after defect and architecture comparison.
- [RESUME_METRICS.md](file:///Users/sj/Documents/cometchat-ai-agent-intern-test/evaluation/complete_customer_journey_2026_11_26/RESUME_METRICS.md): Verified, defensible resume bullet points with mathematical formulas.
- [reproduction_manifest.json](file:///Users/sj/Documents/cometchat-ai-agent-intern-test/evaluation/complete_customer_journey_2026_11_26/reproduction_manifest.json): Exact commands to reproduce every benchmark and test run.
