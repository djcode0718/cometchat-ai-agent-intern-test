# Baseline vs. Final Quantitative and Qualitative Comparison

**Comparison Window**: Pre-hardening Baseline (`f0bd93b`) vs. Hardened Milestone (`df77522`)  
**Branch**: `feat/aster-row-production-hardening`  

---

## 1. Quantitative Metrics Comparison

| Metric Dimension | Pre-Hardening Baseline | Post-Hardening Production | Delta / Improvement | Raw Evidence File |
| :--- | :---: | :---: | :---: | :--- |
| **Total Passing Tests** | 358 tests | **392 tests** | **+34 tests** (+9.5%) | `coverage.json` |
| **Statement Code Coverage** | 81.4% | **86.67%** (2,977/3,435 stmts) | **+5.27%** absolute | `coverage.json` |
| **Adversarial Test Queries** | 30 queries | **120 queries** (70 attacks, 50 controls) | **+90 queries** (4x scale) | `security_results.json` |
| **Adversarial Precision** | Unmeasured | **100.00%** (68 / 68 TP) | **100% precision (0 FP)** | `security_results.json` |
| **Adversarial Recall** | Unmeasured | **97.14%** (68 / 70 TP) | **97.14% recall** | `security_results.json` |
| **Pre-Retrieval Guard Latency**| Unmeasured | **p50 = 9.88 µs, p99 = 13.83 µs** | Sub-millisecond scan | `guard_results.json` |
| **Routing Accuracy** | 98.0% | **100.00%** (200 / 200 cases) | **+2.00%** | `routing_results.json` |
| **Hybrid Retrieval Recall@3** | 98.0% | **100.00%** (50 / 50 golden chunks) | **+2.00%** | `retrieval_results.json` |
| **PostgreSQL Concurrency Race**| SQLite in-memory only | **10 concurrent threads: 1 executed, 9 idempotent** | PostgreSQL ACID verified | `postgres_concurrency_results.json` |
| **Action Authorization (RBAC)**| Single global reviewer key | **3-Tier RBAC (Admin, Reviewer, Readonly)** | Unauthorized actions return 403 | `test_auth_rbac_security.py` |
| **Request ID Correlation** | Inconsistent across services | **100% end-to-end trace correlation** | API → Agent → DB → Audit | `observability_results.json` |
| **PII Scrubbing Verification** | Informal unit tests | **100/100 canaries scrubbed, 0 leaks** | Zero PII in logs or metrics | `observability_results.json` |
| **Local LLM Offline Capability**| Untested | **20 queries on local `llama3.1:8b` Metal** | Complete offline operation | `local_llm_results.json` |
| **Sustained Load Capacity** | C=10 Locust test | **C=50 sustained at 41.55 req/s (0% errors)** | Verified stress capacity | `performance_results.json` |
| **WCAG 2.1 AA Compliance** | Partial component tests | **0 violations across 9 interactive states** | Automated axe + VoiceOver | `accessibility_results.json` |

---

## 2. Qualitative Architectural Evolution

### 1. Unified Identity & Identifier Normalization
- **Before**: Historical reports mixed arbitrary customer identifiers (`CUST-401`, `CUST-1001`, `alice@example.com`) and inconsistent order states.
- **After**: All evaluation suites strictly standardized on primary customer `CUST-401` and primary order `ORD-1001`, with explicit normalized timestamps across database records, customer turns, and audit trails.

### 2. Transactional Concurrency & Integrity
- **Before**: Approvals relied heavily on SQLite in-memory execution, where thread concurrency and row-level locking behavior diverged from production SQL engines.
- **After**: Evaluated against live PostgreSQL 14 with `with_for_update()` row-level locks and optimistic concurrency control (`version` integer checking). Race conditions between simultaneous reviewers or concurrent warehouse shipments result in deterministic re-validation and zero duplicate executions.

### 3. Role-Based Access Control (RBAC)
- **Before**: Any caller providing a valid `X-Reviewer-Key` could approve or reject actions.
- **After**: Fine-grained role hierarchy introduced:
  - `admin`: Can view, approve, reject, and reconfigure rules.
  - `reviewer`: Can view, approve, and reject assigned actions.
  - `readonly` / `auditor`: Can inspect proposals and audit logs; blocked from approving or rejecting with HTTP 403 Forbidden.

### 4. Resilient Fallbacks Under Load
- **Before**: High concurrency bursts against external LLM providers risked unhandled exceptions or customer-facing 500 errors.
- **After**: Dual-engine orchestrator gracefully triggers deterministic fallbacks on upstream 429/500 errors in ~160 ms, ensuring 100% of customer inquiries receive grounded policy answers and valid approval tickets.
