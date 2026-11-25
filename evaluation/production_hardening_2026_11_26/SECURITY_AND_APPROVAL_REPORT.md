# Aster & Row — Security, Adversarial Robustness & Action Authorization Report

**Document Version:** 1.0.0  
**Audit Date:** 2026-11-26  
**Auditor:** Automated Engineering Evaluation Harness  
**Branch:** `feat/aster-row-production-hardening`  
**Test Suites:** `tests/test_auth_rbac_security.py`, `tests/test_adversarial_suite.py`  
**Dataset Artifact:** `evaluation/datasets/security_adversarial_v2.json` (120 labeled samples)  
**Results Artifact:** `evaluation/production_hardening_2026_11_26/security_results.json`  

---

## 1. Executive Summary

A critical requirement of Aster & Row is demonstrating that an AI customer support platform cannot be tricked into mutating transactional records, leaking sensitive credentials, or exposing customer Personally Identifiable Information (PII). 

This report provides the empirical evaluation of a **120-query adversarial benchmark suite** combining 70 targeted adversarial attacks and 50 benign control queries across 7 attack categories.

### Key Security Findings
- **Unauthorized Mutation Count:** **0** (0 / 70 attacks resulted in order cancellation or state mutation).
- **Secret & Credential Leakage:** **0** (0 / 120 queries leaked API keys, reviewer keys, or environment secrets).
- **Customer PII Exposure:** **0** (0 / 120 queries exposed email addresses, home addresses, or internal fraud scores).
- **Precision:** **100.00%** (68 / (68 + 0)). Zero false positives across all 50 benign customer queries.
- **Recall:** **97.14%** (68 / (68 + 2)). 68 of 70 attacks were intercepted by deterministic security guards or neutralized by grounded policy authority.
- **F1 Score:** **0.9855**.
- **Role-Based Access Control (RBAC):** Read-only auditors are strictly barred from executing or rejecting actions (`403 Forbidden`).

---

## 2. Attack Taxonomy & Dataset Composition

The 120-case evaluation dataset (`evaluation/datasets/security_adversarial_v2.json`) tests seven attack categories alongside benign controls:

| Category | Sample Count | Attack Type Description | Primary Defense Layer |
| :--- | :---: | :--- | :--- |
| **Instruction Override & Jailbreaks** | 15 | `[SYSTEM OVERRIDE]`, DAN mode, sudo mode, emergency protocols | Pre-retrieval Security Guard (`evaluate_input_guard`) |
| **Secret & Credential Exfiltration** | 12 | Extraction of `REVIEWER_KEYS`, `.env`, API tokens, connection strings | Regex Guard & Structured Logging Sanitizer |
| **PII & Data Exfiltration** | 12 | Dumping customer lists, home addresses, phone numbers, risk scores | Schema Sanitizer & Pre-retrieval Guard |
| **SQL & Command Injection** | 12 | `'; DROP TABLE orders; --`, `UNION SELECT`, parameter tampering | SQLAlchemy Parameterized Queries & Input Guard |
| **Policy Distortion & Bypassing** | 10 | Prompting agent to promise 365-day refunds or cash price matching | Evidence-Grounded Policy Authority |
| **Forged Approval & Tokens** | 9 | Submitting `{"action": "APPROVE"}` in chat, spoofing review headers | State Machine Enforcement & Endpoint Isolation |
| **Benign Controls (Negative Class)**| 50 | Routine return inquiries, order tracking, product care questions | Hybrid Retriever & Response Generator |
| **Total** | **120** | **70 Attack / 50 Benign** | **Defense-in-Depth Pipeline** |

---

## 3. Empirical Confusion Matrix

```
                      PREDICTED ATTACK     PREDICTED BENIGN
ACTUAL ATTACK (70)         TP = 68              FN = 2
ACTUAL BENIGN (50)         FP = 0               TN = 50
```

### Numerical Evaluation Metrics
- **True Positives (TP):** 68
- **False Positives (FP):** 0
- **True Negatives (TN):** 50
- **False Negatives (FN):** 2 (both non-mutating, zero secrets leaked; routed to standard grounded refusal)
- **Accuracy:** $(68 + 50) / 120 = 98.33\%$
- **Precision:** $68 / (68 + 0) = 100.00\%$
- **Recall:** $68 / (68 + 2) = 97.14\%$
- **F1 Score:** $2 \times \frac{1.0000 \times 0.9714}{1.0000 + 0.9714} = 0.9855$

---

## 4. Architectural Defense Mechanisms

### 4.1 Pre-Retrieval Deterministic Guard (`evaluate_input_guard`)
Executes before vector search or LLM generation at sub-millisecond latency (<0.1 ms). Neutralizes jailbreaks, instruction overrides, and SQL injection syntax before expensive or vulnerable components run.

### 4.2 Endpoint Isolation (Customer vs Reviewer)
Under Aster & Row's architecture, customer chat endpoints (`POST /chat`) **have no code path to mutate database orders**. 
- Customer requests for eligible cancellations can only transition state to `PENDING_APPROVAL`.
- The actual state transition to `APPROVED` -> `EXECUTED` exists exclusively in the authenticated reviewer route (`POST /reviewer/proposals/{proposal_id}/approve`).
- Injecting `{"action": "APPROVE"}` or claiming to be the administrator in customer chat is mathematically incapable of triggering an order mutation.

### 4.3 Reviewer Authentication & Role-Based Access Control (RBAC)
- Reviewer endpoints require `X-Reviewer-Key` validated via `hmac.compare_digest()` to prevent timing attacks.
- Configurable roles (`admin`, `reviewer`, `readonly`/`auditor`):
  - `readonly` auditors receive `403 Forbidden` if attempting `approve` or `reject`.
  - Missing keys receive `401 Unauthorized`.
  - Invalid keys receive `401 Unauthorized`.

---

## 5. Security Invariant Verdict

| Security Invariant | Requirement | Empirical Result | Status |
| :--- | :--- | :--- | :---: |
| **Zero Unauthorized Mutations** | Exact 0 mutations from adversarial prompts | 0 / 70 mutations | **VERIFIED** |
| **Zero Secret Leakage** | Reviewer keys and credentials never output | 0 / 120 leaked | **VERIFIED** |
| **Zero Customer PII Exposure** | Addresses, emails, risk scores suppressed | 0 / 120 leaked | **VERIFIED** |
| **Zero False Positives on Benign Queries** | Legitimate customer queries never blocked | 0 / 50 blocked (0% FP) | **VERIFIED** |
| **RBAC Enforcement** | Readonly auditors barred from action execution | 403 Forbidden enforced | **VERIFIED** |
