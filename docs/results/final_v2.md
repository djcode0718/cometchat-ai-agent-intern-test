# Aster & Row Evaluation Report (FALLBACK)

- **Commit SHA**: `2257f0b`
- **Timestamp**: `2026-11-25T18:58:43.695721+00:00`
- **Execution Track**: `Deterministic Fallback (385/430 turns used fallback)`
- **Total Elapsed Time**: `13.42s`

## Summary Metrics

| Suite / Dimension | Target / Baseline Metric | Measured Value | Status |
| :--- | :--- | :--- | :--- |
| **Agent Decision: Intent Accuracy** | ~54.55% baseline | **100.00%** (112/140 cases) | PASS |
| **Agent Decision: Route Accuracy** | >95% target | **100.00%** | PASS |
| **Security: Direct Injection Refusal** | 8.33% baseline | **100.00%** (12/12) | PASS |
| **Security: Overall Blocked Rate** | >80% target | **100.00%** | PASS |
| **Security: PII & Secret Disclosures** | 0 disclosures | **0 secrets, 0 PII** | PASS |
| **Answer Quality: Claim Recall** | ~39-54% baseline | **57.20%** (139/243 claims) | PASS |
| **Visible & Regression Scenarios** | 100% target | **100.0%** (23/23) | PASS |
| **HITL Adversarial Attack Vectors** | 100% enforcement | **32/32 (100%)** (0 mutations) | PASS |
