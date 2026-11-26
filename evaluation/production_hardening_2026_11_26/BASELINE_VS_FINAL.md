# Baseline vs. Final Quantitative and Qualitative Comparison

**Comparison Window**: Pre-hardening Baseline (`f0bd93b`) vs. Hardened Milestone (`13859eadc43d982ee7a0b0d606513b7cebcde32e`)  
**Branch**: `feat/aster-row-production-hardening`  

---

## 1. Single Unified Baseline (Commit `f0bd93b`)

Baseline metrics are taken strictly from `docs/archive/testing/coverage.json` at commit `f0bd93b`:
- **num_statements**: 2,368
- **covered_lines**: 2,081
- **missing_lines**: 287
- **percent_covered**: 87.88%
- **total_tests**: 358 passed

---

## 2. Quantitative Metrics Comparison

| Metric Dimension | Pre-Hardening Baseline (`f0bd93b`) | Post-Hardening Production (`13859eadc43d982ee7a0b0d606513b7cebcde32e`) | Delta / Improvement | Raw Evidence File |
| :--- | :---: | :---: | :---: | :--- |
| **Total Passing Tests** | 358 tests | **392 tests** | **+34 tests** (+9.5%) | `coverage.json` |
| **Statement Code Coverage** | 87.88% (2,081 / 2,368 stmts) | **86.67%** (2977 / 3435 stmts) | Expanded codebase (+1,067 statements) | `coverage.json` |
| **Adversarial Test Queries** | 30 queries | **120 queries** (70 attacks, 50 controls) | **4x scale** | `security_results.json` |
| **Adversarial Precision** | Unmeasured | **100.00%** (68 / 68 TP) | 100% precision (0 FP) | `security_results.json` |
| **Adversarial Recall** | Unmeasured | **97.14%** (68 / 70 TP) | 97.14% recall | `security_results.json` |
| **Pre-Retrieval Guard Latency**| Unmeasured | **p50 = 11.67 µs, p99 = 49.79 µs** | Sub-millisecond scan | `guard_results.json` |
| **Routing Accuracy** | 98.0% | **100.00%** (200 / 200 cases) | +2.00% | `routing_results.json` |
| **Hybrid Retrieval Recall@3** | 98.0% | **100.00%** (N=12) | Dense equals Hybrid at Recall@3 (100%) | `retrieval_results.json` |
| **PostgreSQL Concurrency Race**| SQLite in-memory only | **10 concurrent threads: 1 executed, 9 idempotent** | PostgreSQL ACID verified | `postgres_concurrency_results.json` |
| **Action Authorization (RBAC)**| Single global reviewer key | **3-Tier RBAC (Admin, Reviewer, Readonly)** | Unauthorized actions return 403 | `test_auth_rbac_security.py` |
| **Request ID Correlation** | Inconsistent | **100% trace correlation** | API → Agent → DB → Audit | `observability_results.json` |
| **Real Middleware Overhead** | Unmeasured | **/health: +0.599 ms; /chat: +182.179 ms** | 1,000 samples x 3 repeats | `observability_results.json` |
| **Local LLM Offline Capability**| Untested | **mean = 9.27 tok/s, p50 = 9.44 tok/s** | Ollama eval_count/eval_duration | `local_llm_results.json` |
| **Load Capacity (N=500/tier)** | C=10 Locust test | **Peak tier C=1: 170.97 req/s; C=50: 97.8 req/s** | 0.00% error rate across all tiers | `performance_results.json` |
| **Frontend Accessibility** | Partial component tests | **0 violations across 9 interactive states** | automated WCAG 2.1 AA checks; manual screen-reader pass: pending | `accessibility_results.json` |
