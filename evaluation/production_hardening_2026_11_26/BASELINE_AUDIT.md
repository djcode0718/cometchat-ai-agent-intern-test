# Baseline Audit & Repository Inspection Report

**Audit Date**: November 26, 2026  
**Program**: Aster & Row Production Hardening, End-to-End Reliability, Evaluation Integrity & Resume Evidence Program  
**Starting Commit SHA**: `f0bd93ba4c75ca0a133496f8c70757c3e721669c` (Merge of `feat/aster-row-agent-upgrade` into `main`)  
**Feature Branch**: `feat/aster-row-production-hardening`  
**Host Environment**: macOS Darwin (Apple Silicon, 10-core CPU, 16-core GPU, Unified Memory)  
**Database Systems Available**: SQLite 3.x (Embedded) & PostgreSQL 14.18 (Homebrew localhost:5432)  
**Local LLM Engine Available**: Ollama v0.1.x+ with `llama3.1:8b` (Metal GPU acceleration)  
**Container Engine Available**: Docker 29.8.2 / Docker Compose v5.6.0  

---

## 1. Executive Baseline & Frozen Metrics

The following metrics represent the frozen baseline established in the previous evaluation phase (`evaluation/complete_customer_journey_2026_11_26/`). These figures are preserved as historical benchmarks to be validated, stress-tested, and defended under real multi-user and PostgreSQL transactional conditions:

| Metric Category | Target Dimension | Frozen Baseline Value | Source Artifact |
|---|---|---|---|
| **Test Quality** | Automated pytest suite pass count | **351 / 351 passed (100%)** | `pytest --cov=src` in 74.01s |
| **Code Coverage** | Python statement coverage | **86.41%** (2,937 / 3,399 lines) | `coverage.json` |
| **Adversarial Security**| Negative & adversarial matrix pass rate | **24 / 24 scenarios (100%)** | `SCENARIO_MATRIX.csv` |
| **Frontend A11y** | Axe-core serious/critical violations | **0 violations** across 9 states | `accessibility_results.json` |
| **Frontend A11y** | Lighthouse accessibility score | **100 / 100** | `@lhci/cli` |
| **Pipeline Latency** | Mock engine latency p50 (C=1) | **6.63 ms** | `performance_results.json` |
| **System Throughput** | Unthrottled throughput at C=25 | **194.10 req/s** (0.0% error) | `performance_results.json` |
| **Local LLM Latency** | Llama 3.1:8b generation latency p50 | **5,903.99 ms** (17.77 tok/s) | `performance_results.json` |

---

## 2. Source Architecture Inspection

### A. API Gateway & Middleware (`src/api.py`, `src/observability/`)
- **FastAPI Application**: Routes for `/chat`, `/sessions/{id}/proposal`, `/sessions/{id}/trace`, `/reviewer/proposals`, `/reviewer/proposals/{id}`, `/reviewer/proposals/{id}/approve`, `/reviewer/proposals/{id}/reject`, `/reviewer/audit`, `/metrics`, and `/health`.
- **Middleware**: `RequestContextMiddleware` for request ID extraction and correlation; `slowapi` rate limiting (`RATE_LIMIT_CHAT`, `RATE_LIMIT_REVIEWER`); `RequestSizeLimitMiddleware` rejecting payloads > 1MB (`HTTP 413`).
- **Telemetry**: Structlog JSON logging, Prometheus metrics endpoints on `/metrics`.

### B. Agent & Orchestration Engine (`src/agent/`)
- **`security_guard.py`**: Pre-retrieval deterministic regex filter intercepting `instruction_override`, `role_play`, `prompt_exfiltration`, and `approval_spoofing`.
- **`router.py`**: High-precision deterministic regular expressions routing queries into `ORDER`, `KNOWLEDGE`, `ACTION`, or `UNSUPPORTED`.
- **`retriever.py`**: SentenceTransformer `all-MiniLM-L6-v2` generating dense embeddings with cosine similarity scoring.
- **`knowledge.py`**: Hierarchical policy resolver selecting approved chunks and enforcing policy conflict boundaries.
- **`validator.py`**: Language safety and output validator intercepting PII, unsupported mutation claims, and unapproved citations.

### C. Approvals & State Machine (`src/approvals/`)
- **`models.py`**: SQLAlchemy relational models for `OrderModel`, `ProposedActionModel`, and `AuditEventModel`.
- **`state_machine.py`**: Formal finite state machine defining valid transitions between `PENDING_APPROVAL`, `APPROVED`, `EXECUTED`, `REJECTED`, `EXPIRED`, and `FAILED`.
- **`service.py`**: `ApprovalService` implementing optimistic locking (`version`), lazy TTL expiry, atomic revalidation, and row-level locking (`with_for_update`).
- **`sql_repository.py`**: Database repository querying `OrderModel` and enforcing the 30-minute policy cancellation window.
- **`audit_repository.py`**: Append-only audit logger recording every lifecycle transition with actor and timestamp.

### D. Frontend Console (`frontend/src/`)
- **React 18 + TypeScript + Vite**: Single-page application providing both the Customer View (`CustomerView.tsx`) with accessible chat log and live polling status card, and the Reviewer Console (`ReviewerConsole.tsx`) with proposals table, memory-only key entry, and focus-trapped approval/rejection dialogs.

---

## 3. Discrepancies & Issues Identified for Remediation

During this Phase 0 audit of previous artifacts, the following discrepancies were identified:

1. **Customer Identifier Discrepancy**:
   - `data/demo_orders.json` defines `ORD-1001` with `customer_id: "CUST-401"`.
   - In some historical narratives and reports, `CUST-001` was referenced interchangeably.
   - *Fix*: Standardize on `CUST-401` as the canonical synthetic customer identifier across all JSON artifacts, Markdown tables, and test fixtures.
2. **Timestamp Disambiguation**:
   - Simulated business eligibility time (`2026-03-01T11:15:00Z` vs order placement `2026-03-01T11:00:00Z`) was occasionally intermixed with real-world evaluation execution timestamps (`2026-11-25T21:07:14Z`).
   - *Fix*: Explicitly partition all telemetry and reports into:
     - `simulated_order_placed_at`
     - `simulated_business_clock`
     - `evaluation_started_at`
     - `evaluation_completed_at`
     - `audit_event_created_at`
3. **Request ID Correlation Inconsistency**:
   - In earlier drafts of `create_proposal`, request correlation occasionally defaulted to generated internal UUIDs rather than propagating the incoming customer HTTP `X-Request-ID`.
   - *Fix*: Ensure strict end-to-end propagation from HTTP request headers into proposal entities, audit records, and trace logs.
4. **Reviewer Credential Exposure**:
   - Static test keys (e.g. `secret_admin_key_123`) appeared in raw JSON files and test command descriptions.
   - *Fix*: Sanitize all documentation, reports, and manifests using `[REDACTED_TEST_CREDENTIAL]`.
5. **PostgreSQL Concurrency Evidence**:
   - Previous evaluation runs executed exclusively against embedded SQLite with `check_same_thread=False`. Real PostgreSQL row locking (`SELECT ... FOR UPDATE`), transaction rollbacks, and concurrent worker execution remain to be formally proven on a running PostgreSQL instance.
   - *Fix*: Build a dedicated PostgreSQL concurrency test suite executing against PostgreSQL 14.18 (`aster_row_test`).
6. **Isolated Benchmarks for Resume Metrics**:
   - Resume claims such as "90% routine query bypass", "sub-1.2ms guard latency", and "0 false positives on 150 benign queries" need dedicated, reproducible benchmark scripts with explicit numerators and denominators.

---

## 4. Phase-by-Phase Implementation Plan

- **Phase 1**: Report consistency audit & evidence normalization.
- **Phase 2**: PostgreSQL database and transaction correctness (migrations, row locks, concurrent reviewer races).
- **Phase 3**: Authentication, authorization, and action security regression suite.
- **Phase 4**: Expanded customer journey test suite (multiple order states, failures, and edge cases).
- **Phase 5**: Comprehensive security & adversarial evaluation (100+ cases, precision/recall/F1).
- **Phase 6**: Dedicated routing, guard latency (1,000 runs), and retrieval benchmarks.
- **Phase 7**: Local LLM evaluation with Ollama `llama3.1:8b` (50 queries, tokens/sec, per-query logs).
- **Phase 8**: Observability, structured logging verification, and instrumentation overhead measurement.
- **Phase 9**: Multi-concurrency load testing (C=1, 5, 10, 25, 50) and pipeline latency breakdown.
- **Phase 10**: Frontend accessibility & assistive technology audit (Axe, Lighthouse, VoiceOver steps).
- **Phase 11**: Architecture and maintainability review.
- **Phase 12**: Docker and multi-container Compose deployment readiness.
- **Phase 13**: Final production hardening dossier in `evaluation/production_hardening_2026_11_26/`.
- **Phase 14**: Final verification, acceptance checks, and merge into `main`.

---

## 5. Risks & Mitigation Strategies

| Risk Factor | Impact | Mitigation Strategy |
|---|---|---|
| PostgreSQL connection issues in CI/Local | Blocks Phase 2 concurrency tests | Verified Homebrew PostgreSQL 14.18 running locally on localhost:5432; dedicated `aster_row_test` database initialized. |
| Local LLM (llama3.1:8b) thermal throttling / latency | Slows Phase 7 benchmarks | Run 50 targeted queries in batch with pre-warmed Ollama context; record tokens/sec and execution timestamp. |
| Port conflicts with running Docker containers | Fails Docker readiness | Verify port mappings (`8000`, `3000`, `5432`, `9090`, `3001`) before starting containers. |
| Premature merge or history rewrite | Violates repository rules | Strict additive commits; no force-pushes; merge to `main` only during Phase 14 after all criteria pass. |
