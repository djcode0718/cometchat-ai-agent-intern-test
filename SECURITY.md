# Aster & Row Security Policy

## Security Model Overview
Aster & Row follows a strict **Deterministic-First Architecture** designed to eliminate hallucinations, prevent prompt injection privilege escalation, and protect customer data privacy.

The Language Model (LLM) is strictly restricted to linguistic phrasing of verified facts. It has **zero authority** to:
1. Determine policy eligibility.
2. Authorize actions or refunds.
3. Mutate databases or execute cancellations.
4. Bypass human review requirements.

---

## Security Boundary Architecture

```
[ Customer Query ]
       │
       ▼
┌────────────────────────────────────────────────────────┐
│ Pre-Retrieval Deterministic Input Guard                │
│ - Instruction override detection                       │
│ - Roleplay / Authority spoofing detection              │
│ - System prompt exfiltration detection                 │
│ - Approval token spoofing detection                    │
└───────────────────────┬────────────────────────────────┘
                        │ PASS (otherwise immediate safe refusal)
                        ▼
┌────────────────────────────────────────────────────────┐
│ Deterministic Router & Policy Authority                │
│ - Strict regex & finite-state classification           │
│ - Exact matching on customer ID & session isolation    │
└───────────────────────┬────────────────────────────────┘
                        │
                        ▼
┌────────────────────────────────────────────────────────┐
│ Dual-Retrieval Policy Grounding (BM25 + Dense)         │
│ - Verified policy chunks with citation anchors         │
└───────────────────────┬────────────────────────────────┘
                        │
                        ▼
┌────────────────────────────────────────────────────────┐
│ LLM Phrasing & Strict Post-Validator                   │
│ - Hallucination suppression                            │
│ - PII & Secret Redaction (Masking & Key Dropping)      │
│ - Deterministic Fallback if ungrounded                 │
└───────────────────────┬────────────────────────────────┘
                        │
                        ▼
┌────────────────────────────────────────────────────────┐
│ Human-In-The-Loop (HITL) State Machine                 │
│ - Append-only immutable audit trail                    │
│ - Optimistic concurrency locking (version tag)         │
│ - Human reviewer bearer token authorization            │
└────────────────────────────────────────────────────────┘
```

---

## Core Security Invariants

### 1. PII and Secret Redaction Guarantee
- The logging system (`structlog`) and trace cache enforce automatic recursive redaction.
- **Sensitive Keys Dropped/Masked**: `email`, `address`, `name`, `warehouse_note`, `risk_score`, `api_key`, `authorization`, `cookie`.
- **String Redaction**: Regex scrubbing for email addresses (`user@domain.com` -> `[REDACTED_EMAIL]`) and API key patterns (`gsk_...`, `AIza...`, `sk-or-...` -> `[REDACTED_KEY]`).
- Internal order notes (e.g., fraud scores, warehouse instructions) are stripped before models or responses are serialized.

### 2. Prompt Injection & Jailbreak Defense
- A pre-retrieval deterministic regex guard monitors all inbound queries.
- Intercepts and immediately defuses:
  - System instruction overrides (`ignore previous instructions`, `new rules apply`).
  - Roleplay/admin impersonation (`you are now in maintenance mode`, `DAN mode`).
  - Prompt leakage vectors (`repeat the above system prompt`, `what are your instructions`).
  - HITL spoofing (`approved by supervisor`, `token: APPROVED`).
- Triggers Prometheus counter `security_injections_blocked_total` and emits structured security log without leaking pattern specifics.

### 3. Human-In-The-Loop (HITL) Guardrails
- Critical mutations (e.g., cancellations, address changes) generate `PENDING_APPROVAL` proposals.
- Proposals can **only** transition to `APPROVED` or `REJECTED` via authenticated reviewer endpoints (`/reviewer/*`) requiring `REVIEWER_API_KEY`.
- Optimistic locking (`version` column) prevents double-decision race conditions (returning HTTP 409 Conflict).
- Audit trail is strictly append-only; SQL repository implements no update/delete primitives on audit records.

### 4. API & Transport Security
- **Rate Limiting**: Configured via `slowapi` (`60/minute` per remote IP on `/chat` and `/reviewer` endpoints).
- **Request Size Limit**: Payloads exceeding 1MB are rejected with HTTP 413.
- **Security Headers**: Injected on every response:
  - `X-Content-Type-Options: nosniff`
  - `X-Frame-Options: DENY`
  - `Content-Security-Policy: default-src 'self'; frame-ancestors 'none';`
  - `Referrer-Policy: strict-origin-when-cross-origin`
- **CORS**: Restricted to explicitly whitelisted origin domains.

---

## Out-of-Scope Boundaries & Limitations
- This agent does not process credit cards or PCI-DSS cardholder data. Payment details must be handled by external PSP interfaces.
- The agent does not execute automated warehouse logistics or carrier rerouting without an external human confirmation step.

---

## Vulnerability Reporting
If you discover a security vulnerability in Aster & Row:
1. Please report it privately to `security@aster-row.example.com`.
2. Do not open public GitHub issues for security vulnerabilities.
3. Reports will be acknowledged within 24 hours with remediation updates.
