# Aster & Row Evaluation Report (FALLBACK)

- **Commit SHA**: `62894ee`
- **Timestamp**: `2026-11-25T18:31:43.706195+00:00`
- **Execution Track**: `Deterministic Fallback (400/430 turns used fallback)`
- **Total Elapsed Time**: `11.95s`

## Summary Metrics

| Suite / Dimension | Target / Baseline Metric | Measured Value | Status |
| :--- | :--- | :--- | :--- |
| **Agent Decision: Intent Accuracy** | ~54.55% baseline | **71.43%** (73/140 cases) | PASS |
| **Agent Decision: Route Accuracy** | >95% target | **92.86%** | WARN |
| **Security: Direct Injection Refusal** | 8.33% baseline | **8.33%** (1/12) | BASELINE |
| **Security: Overall Blocked Rate** | >80% target | **87.06%** | PASS |
| **Security: PII & Secret Disclosures** | 0 disclosures | **0 secrets, 0 PII** | PASS |
| **Answer Quality: Claim Recall** | ~39-54% baseline | **18.11%** (44/243 claims) | BASELINE |
| **Visible & Regression Scenarios** | 100% target | **100.0%** (23/23) | PASS |
| **HITL Adversarial Attack Vectors** | 100% enforcement | **32/32 (100%)** (0 mutations) | PASS |
