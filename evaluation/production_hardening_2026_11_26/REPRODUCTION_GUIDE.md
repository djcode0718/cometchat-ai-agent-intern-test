# End-to-End Reproduction Guide

This guide describes how to reproduce every automated evaluation benchmark, database concurrency test, and report in `evaluation/production_hardening_2026_11_26/`.

---

## 1. Prerequisites & Environment Setup

- **Python Version**: Python 3.11.18 in virtual environment `/Users/sj/miniforge3/envs/cometchat-env`
- **PostgreSQL**: PostgreSQL 14 running on `localhost:5432` with test database `aster_row_test`
- **Ollama**: Local Ollama service running on `http://localhost:11434` with model `llama3.1:8b` (optional for offline LLM evaluation)
- **Node.js**: v20+ with npm dependencies installed in `frontend/`

```bash
# Set environment variables
export PYTHONPATH=.
export APP_ENV=test
export DATABASE_URL="postgresql://sj:@localhost:5432/aster_row_test"
export RATE_LIMIT_CHAT="10000/minute"
export RATE_LIMIT_REVIEWER="10000/minute"
```

---

## 2. Seed Database & Run Alembic Migrations

```bash
# Run database migrations
/Users/sj/miniforge3/envs/cometchat-env/bin/alembic upgrade head

# Seed initial demo orders into PostgreSQL
/Users/sj/miniforge3/envs/cometchat-env/bin/python -c "from src.approvals.seed import seed_database; seed_database()"
```

---

## 3. Execute Automated Evaluation Benchmarks

### A. PostgreSQL Concurrency & ACID Row-Locking (Phase 2)
```bash
/Users/sj/miniforge3/envs/cometchat-env/bin/pytest tests/test_postgres_concurrency.py -v -s
# Produces: evaluation/production_hardening_2026_11_26/postgres_concurrency_results.json
```

### B. RBAC Security & Action Boundaries (Phase 3)
```bash
/Users/sj/miniforge3/envs/cometchat-env/bin/pytest tests/test_auth_rbac_security.py -v
```

### C. 12-Scenario Customer Journey Lifecycle (Phase 4)
```bash
/Users/sj/miniforge3/envs/cometchat-env/bin/pytest tests/test_journey_expanded.py -v
# Produces: evaluation/production_hardening_2026_11_26/journey_results.json
```

### D. 120-Case Adversarial & Injection Suite (Phase 5)
```bash
/Users/sj/miniforge3/envs/cometchat-env/bin/pytest tests/test_adversarial_suite.py -v
# Produces: evaluation/production_hardening_2026_11_26/security_results.json
```

### E. Routing, Guard Latency & Hybrid Retrieval Recall (Phase 6)
```bash
/Users/sj/miniforge3/envs/cometchat-env/bin/pytest tests/test_routing_guard_retrieval_benchmarks.py -v -s
# Produces: guard_results.json, routing_results.json, retrieval_results.json
```

### F. Local Ollama llama3.1:8b Evaluation (Phase 7)
```bash
/Users/sj/miniforge3/envs/cometchat-env/bin/pytest tests/test_local_ollama_benchmark.py -v -s
# Produces: evaluation/production_hardening_2026_11_26/local_llm_results.json
```

### G. Observability Overhead, PII Redaction & Prometheus Metrics (Phase 8)
```bash
/Users/sj/miniforge3/envs/cometchat-env/bin/pytest tests/test_observability_overhead_verification.py -v -s
# Produces: evaluation/production_hardening_2026_11_26/observability_results.json
```

### H. Multi-Concurrency Load Testing C=1 to C=50 (Phase 9)
```bash
/Users/sj/miniforge3/envs/cometchat-env/bin/pytest tests/test_performance_load_benchmarks.py -v -s
# Produces: evaluation/production_hardening_2026_11_26/performance_results.json
```

### I. Frontend Accessibility & VoiceOver Tests (Phase 10)
```bash
cd frontend && npm test -- --run && npm run lint
# Produces: evaluation/production_hardening_2026_11_26/accessibility_results.json
```

### J. Full Test Suite & Coverage Verification (Phase 11)
```bash
PYTHONPATH=. /Users/sj/miniforge3/envs/cometchat-env/bin/pytest --ignore=tests/test_local_ollama_benchmark.py --cov=src --cov-report=json:evaluation/production_hardening_2026_11_26/coverage.json --cov-report=term
```
