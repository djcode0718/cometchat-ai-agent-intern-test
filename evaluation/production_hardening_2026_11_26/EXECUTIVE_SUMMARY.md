# Executive Summary — Aster & Row Production Hardening & Evaluation Dossier

**System**: Aster & Row — AI Customer Support & Human-in-the-Loop Order Operations  
**Evaluation Date**: 2026-11-26  
**Target Branch**: `feat/aster-row-production-hardening`  
**Evaluation Dossier Directory**: `evaluation/production_hardening_2026_11_26/`  
**Total Automated Tests**: 392 passed (100.0% passing, 0 failures)  
**Test Coverage**: 86.67% (2,977 / 3,435 statements covered)  

---

## 1. High-Level Mission & Scope

Aster & Row was hardened from an AI prototype into a verified, enterprise-grade customer support platform. The core technical achievement is demonstrating a **deterministic, policy-grounded human-in-the-loop (HITL) transactional lifecycle**:

```
Customer asks to cancel/modify order
  → Deterministic Security Guard checks input (< 0.01 ms)
  → Intent Router classifies order intent
  → Policy & customer order eligibility verified against database
  → Persistent PENDING_APPROVAL proposal created in PostgreSQL
  → Authorized reviewer approves via RBAC-protected API
  → System re-validates order state under row locks
  → Exactly-once cancellation executes (0 duplicate mutations)
  → Immutable audit trail records every state transition
  → Correlated X-Request-ID propagated across all structured logs & Prometheus metrics
```

---

## 2. Key Production Metrics & Benchmarks

All metrics reported below are backed by raw evaluation files in `evaluation/production_hardening_2026_11_26/`.

| Dimension | Metric | Measured Value | Threshold / Target | Status |
| :--- | :--- | :--- | :--- | :--- |
| **PostgreSQL Concurrency** | Race Condition Safety (10 simultaneous threads) | **1 executed, 9 idempotent returns, 0 duplicate mutations** | Exactly-once execution | **PASSED** |
| **Security Guard Latency** | Pre-retrieval regex scan overhead | **p50 = 9.88 µs, p99 = 13.83 µs** | < 1.0 ms | **PASSED** |
| **Adversarial Precision** | Injection detection precision (120 test cases) | **100.00%** (68 / 68 detected attacks) | ≥ 95.0% | **PASSED** |
| **Adversarial Recall** | Injection detection recall (120 test cases) | **97.14%** (68 / 70 attacks neutralized) | ≥ 95.0% | **PASSED** |
| **Customer Data Isolation** | Cross-customer PII leakage events | **0 leaks** (0 / 120 adversarial attempts) | Strict zero leakage | **PASSED** |
| **Intent Routing Accuracy** | Route classification accuracy (200 cases) | **100.00%** (200 / 200 correct) | ≥ 98.0% | **PASSED** |
| **Retrieval Quality** | Hybrid Search Recall@3 (50 standard queries) | **100.00%** (50 / 50 golden chunks retrieved) | ≥ 95.0% | **PASSED** |
| **Retrieval MRR** | Mean Reciprocal Rank (Hybrid BM25 + Dense) | **0.9444** | ≥ 0.90 | **PASSED** |
| **Local LLM Execution** | `llama3.1:8b` Metal GPU Throughput | **12.83 tokens/sec** | Fully offline capable | **PASSED** |
| **Observability Overhead** | HTTP Middleware Latency Overhead | **p50 = 1.589 ms, Mean = 2.347 ms** | < 5.0 ms | **PASSED** |
| **Multi-Concurrency Load**| Peak Throughput at Concurrency C=50 | **41.55 req/s (0.00% error rate)** | Sustained throughput | **PASSED** |
| **Frontend Accessibility** | Axe-Core & WCAG 2.1 AA Violations (9 states) | **0 serious/critical violations** | 100% WCAG 2.1 AA | **PASSED** |
| **Backend Test Coverage** | Pytest line coverage across `src/` | **86.67%** (2,977 / 3,435 statements) | ≥ 80.0% | **PASSED** |

---

## 3. Dossier Structure

The evaluation reports and artifacts are organized as follows:

1. `EXECUTIVE_SUMMARY.md`: High-level findings and scorecard.
2. `BASELINE_AUDIT.md`: Pre-change baseline architecture, test counts, and claims.
3. `REPORT_CONSISTENCY_AUDIT.md`: Identifier and timestamp normalization (`CUST-401`, `ORD-1001`).
4. `POSTGRES_CONCURRENCY_REPORT.md` & `postgres_concurrency_results.json`: ACID transactions and row locking.
5. `SECURITY_AND_APPROVAL_REPORT.md` & `security_results.json`: 120-query adversarial benchmark and RBAC verification.
6. `ROUTING_AND_GUARD_EVALUATION.md` & `routing_results.json`, `guard_results.json`: Routing accuracy and 9.8 µs guard latency.
7. `RETRIEVAL_EVALUATION.md` & `retrieval_results.json`: BM25 vs Dense vs Hybrid fusion benchmarks.
8. `LOCAL_LLM_EVALUATION.md` & `local_llm_results.json`: 20-query `llama3.1:8b` Ollama Metal GPU benchmark.
9. `OBSERVABILITY_REPORT.md` & `observability_results.json`: Request ID tracing, PII scrubbing, Prometheus metrics.
10. `PERFORMANCE_REPORT.md` & `performance_results.json`: Multi-concurrency load testing (C=1 to C=50).
11. `ACCESSIBILITY_REPORT.md` & `accessibility_results.json`: WCAG 2.1 AA, VoiceOver walkthrough, axe audits.
12. `COMPLETE_JOURNEY_REPORT.md`: Step-by-step trace of the end-to-end customer journey.
13. `TEST_AND_COVERAGE_REPORT.md`: Comprehensive test catalogue and coverage analysis.
14. `BASELINE_VS_FINAL.md`: Quantitative and qualitative comparison matrix.
15. `RESUME_METRICS.md`: Bullet points with verified numerical claims and file references.
16. `REPRODUCTION_GUIDE.md`: Step-by-step reproduction instructions.
17. `reproduction_manifest.json`: Checksums, environment versions, and command manifests.
18. `METRICS_SUMMARY.json`: Machine-readable KPI roll-up.
