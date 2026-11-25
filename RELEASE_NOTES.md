# Release Notes - Aster & Row v2.0.0

**Release Tag**: `v2.0.0`  
**Date**: November 26, 2026  
**Commit**: `HEAD`

---

## Executive Summary
Aster & Row v2.0.0 represents a major architectural upgrade transitioning the support agent from a prototype chatbot into a production-grade, deterministic-first autonomous support platform. This release introduces comprehensive observability, optimistic-concurrency human-in-the-loop (HITL) approval workflows, a fully accessible WCAG 2.1 AA customer and reviewer frontend, pre-retrieval prompt injection security defenses, containerization, and automated regression evaluation gates.

---

## Key Highlights & Architectural Changes

### 1. Deterministic-First Policy & Intent Authority
- Replaced ambiguous pattern matching with rigorous deterministic order routing and intent extraction regexes.
- **Intent classification accuracy** surged from **71.43% to 100.00%** on the 140-case `agent_decision` suite.
- Preserved strict core invariant: the LLM never decides eligibility, authorizes an action, or executes an order mutation.

### 2. Full-Stack Observability
- Integrated `structlog` with unified JSON structured logging in production and contextvars propagation.
- Distributed `X-Request-ID` request tracking across all FastAPI endpoints, middleware, and sub-services.
- Automatic, recursive PII and secret redaction (`[REDACTED_EMAIL]`, `[REDACTED_KEY]`, stripping internal risk scores).
- Prometheus metrics exposition (`/metrics`) and provisioned Grafana dashboard monitoring latency, token usage, error rates, and security injection attempts.

### 3. Human-in-the-Loop (HITL) Approval Architecture
- Implemented state-machine driven proposal workflow (`docs/adr/0001-hitl-approvals.md`) with PostgreSQL/SQLite persistence via SQLAlchemy 2 + Alembic.
- Enforced optimistic concurrency locking (`version` column) preventing race conditions (returning HTTP 409 Conflict).
- Append-only immutable audit trail recording every state transition, actor, reason, and timestamp.
- Evaluated against 32 adversarial attack vectors (`hitl_adversarial`) with 100% enforcement and 0 unauthorized mutations.

### 4. Deterministic Pre-Retrieval Security Guard
- Added pre-retrieval security inspection filtering instruction-override attacks, roleplay/admin impersonation, prompt exfiltration, and approval token spoofing.
- Direct prompt injection resistance jumped from **8.33% to 100.00%** on the 85-case `security_adversarial` suite.
- Zero pattern leakage in responses, zero false positives on legitimate customer queries.

### 5. Grounded Knowledge Fallback Enhancement
- Upgraded deterministic fallback from chunk-0 truncation to query-relevant sentence extraction.
- Preserved citation anchors (`[file > heading]`).
- Claim recall improved from **18.11% to 51.85%** across 150 `answer_quality` cases while maintaining 94.67% citation coverage.

### 6. Accessible React Frontend (WCAG 2.1 AA)
- Modern Vite + React + TypeScript frontend featuring both customer chat and `/reviewer` console.
- Zero accessibility violations verified via `@axe-core/react`, `eslint-plugin-jsx-a11y`, and Lighthouse CI.
- Features polite live region announcements, keyboard focus traps, contrast compliance, and responsive reflow up to 200% zoom.

### 7. Containerization & Security Hardening
- Multi-stage non-root `Dockerfile` with healthcheck on `/health`.
- `docker-compose.yml` orchestrating API, React frontend (nginx), PostgreSQL, Prometheus, and Grafana.
- `slowapi` rate limiting (60 req/min), 1MB payload limits, security headers (`nosniff`, `DENY`, `CSP`).
- 0 vulnerabilities detected via `pip-audit` and `npm audit --omit=dev`.

---

## Measured Evaluation Metrics (Before vs. After)

All metrics were computed via `evaluation/run_suite.py` across 430 test cases:

| Suite / Dimension | Baseline (v1 / Step 1) | Final (v2.0.0) | Target / Gate |
| :--- | :--- | :--- | :--- |
| **Agent Decision: Intent Accuracy** | 71.43% | **100.00%** | >=95% |
| **Agent Decision: Route Accuracy** | 92.86% | **100.00%** | >=95% |
| **Security: Direct Injection Refusal** | 8.33% | **100.00%** | >=95% |
| **Security: Overall Attacks Blocked** | 87.06% | **100.00%** | >=90% |
| **Security: PII & Secret Disclosures** | 0 disclosures | **0 disclosures** | 0 |
| **Answer Quality: Claim Recall** | 18.11% | **51.85%** | >=45% |
| **Answer Quality: Citation Coverage** | 94.67% | **94.67%** | >=90% |
| **Visible & Regression Test Scenarios**| 100.0% (23/23) | **100.0% (23/23)** | >=95% |
| **HITL Adversarial Attack Vectors** | 100.0% (32/32) | **100.0% (32/32)** | 100% |

---

## Upgrade & Verification Instructions

```bash
# 1. Update dependencies
pip install -r requirements.txt

# 2. Run test suite
PYTHONPATH=. pytest

# 3. Verify regression evaluation gates
PYTHONPATH=. python evaluation/run_suite.py --check-thresholds

# 4. Start full stack with Docker Compose
docker compose up -d
```
