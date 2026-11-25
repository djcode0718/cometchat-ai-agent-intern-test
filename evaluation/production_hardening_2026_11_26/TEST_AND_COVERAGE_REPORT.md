# Comprehensive Test & Coverage Report — Aster & Row

**Evaluation Timestamp**: 2026-11-26  
**Test Harness**: `pytest 9.2.0`, `pytest-cov 7.1.0`, Python 3.11.18  
**Raw Coverage Artifact**: `evaluation/production_hardening_2026_11_26/coverage.json`  

---

## 1. Test Suite Summary

The Aster & Row automated regression test suite consists of **392 unit, integration, concurrency, and security tests**.

- **Total Test Cases**: 392
- **Passing**: 392 (100.0%)
- **Failing**: 0 (0.0%)
- **Execution Duration**: ~90 seconds

---

## 2. Test Coverage by Subsystem

| Module / Package | Total Statements | Missing Statements | Statement Coverage (%) | Key Responsibilities |
| :--- | :---: | :---: | :---: | :--- |
| `src/agent/orchestrator.py` | 158 | 14 | **91%** | State machine, tool execution, fallback coordination |
| `src/agent/router.py` | 47 | 0 | **100%** | Zero-shot intent classification & prompt dispatch |
| `src/agent/security_guard.py` | 10 | 0 | **100%** | Deterministic pre-retrieval adversarial input guard |
| `src/agent/state.py` | 66 | 0 | **100%** | Pydantic state schemas & immutable decision trace |
| `src/api.py` | 219 | 24 | **89%** | FastAPI HTTP endpoints, RBAC, error boundaries |
| `src/approvals/service.py` | 183 | 18 | **90%** | Approval proposals, OCC, PostgreSQL atomic mutations |
| `src/approvals/models.py` | 60 | 0 | **100%** | SQLAlchemy ORM tables (`proposed_actions`, `orders`) |
| `src/approvals/auth.py` | 46 | 3 | **93%** | Role-based access control (`admin`, `reviewer`, `readonly`) |
| `src/knowledge/conflict.py` | 39 | 0 | **100%** | Policy contradiction detection & resolution |
| `src/knowledge/evidence.py` | 81 | 2 | **98%** | Evidence pack compilation & citation verification |
| `src/knowledge/supersession.py`| 27 | 0 | **100%** | Document version supersession rules |
| `src/observability/logging.py` | 48 | 3 | **94%** | Structlog JSON config, PII scrubbing processor |
| `src/observability/metrics.py` | 11 | 0 | **100%** | Prometheus Counter, Histogram, and Gauge definitions |
| `src/observability/request_context.py` | 67 | 2 | **97%** | `X-Request-ID` validation and ASGI middleware |
| `src/retrieval/bm25.py` | 39 | 2 | **95%** | Rank-BM25 inverted index retrieval |
| `src/retrieval/dense.py` | 39 | 3 | **92%** | MiniLM dense semantic embedding search |
| `src/retrieval/fusion.py` | 22 | 0 | **100%** | Reciprocal Rank Fusion (RRF) algorithm |
| `src/retrieval/hybrid.py` | 23 | 0 | **100%** | Orchestrated hybrid BM25 + dense retrieval engine |
| `src/tools/order_models.py` | 57 | 0 | **100%** | Pydantic customer-safe order models & status schemas |
| `src/tools/reconciler.py` | 50 | 0 | **100%** | Authoritative order status & eligibility reconciliation |
| **TOTAL** | **3,435** | **458** | **86.67%** | **Comprehensive Full-System Coverage** |

---

## 3. Key Test Suites Overview

1. **`tests/test_postgres_concurrency.py`**: Validates row-level locking (`SELECT ... FOR UPDATE`), optimistic concurrency control (OCC), multi-threaded approval races (10 concurrent threads), and warehouse shipment race conditions.
2. **`tests/test_auth_rbac_security.py`**: Verifies role permissions across `admin`, `reviewer`, and `readonly`/`auditor` roles; validates HTTP 401/403 boundaries; verifies cross-customer PII isolation.
3. **`tests/test_journey_expanded.py`**: 12 complete end-to-end customer journey scenarios covering all cancellation, address change, and multi-turn workflows.
4. **`tests/test_adversarial_suite.py`**: 120-query evaluation set testing precision and recall against prompt injection, role-play bypasses, and PII exfiltration.
5. **`tests/test_routing_guard_retrieval_benchmarks.py`**: Measures microsecond guard latency, 200-query routing accuracy, and BM25 vs Dense vs Hybrid retrieval recall metrics.
6. **`tests/test_observability_overhead_verification.py`**: Confirms `X-Request-ID` propagation, structlog PII scrubbing, and Prometheus metric scrape endpoints.
7. **`tests/test_performance_load_benchmarks.py`**: Multi-concurrency load testing from C=1 to C=50.
