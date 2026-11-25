# Stage 3 Answer Quality, Groundedness, and Citation Evaluation (`answer_quality_v1`)

## 1. Directory Overview

This directory contains the complete evaluation dataset, execution traces, claim-level audits, citation verifications, and aggregate metrics for **Stage 3: Answer Quality, Groundedness, and Citation Evaluation**.

Evaluation is structured across distinct tracks:
- `fallback_baseline`: 150 benchmark scenarios evaluated through the production deterministic fallback generator (`OutputValidator.build_fallback()`).
- `controlled_test`: 10 synthetic test fixtures validating that the evaluation rubric and citation auditor accurately discriminate between grounded, hallucinated, superseded, and adversarial responses.
- `live_llm`: Marked as **BLOCKED / Awaiting Explicit Approval** under Rule 9 (no paid external API calls without explicit authorization).

---

## 2. Artifact Manifest

| File | Format | Description |
| :--- | :--- | :--- |
| `annotation_guide.md` | Markdown | Comprehensive 7-dimension scoring rubric (0–4 scale), claim decomposition rules, and citation verification protocol. |
| `dataset.json` | JSON | Master 150-scenario benchmark covering 15 distinct categories, required claims, forbidden claims, and expected citations. |
| `raw_results.jsonl` | JSON Lines | Complete turn-level execution traces from `AgentOrchestrator`, including latency, decision states, and retrieved evidence chunks. |
| `claim_level_results.jsonl` | JSON Lines | Atomic claim decompositions, support verifications against retrieved evidence, and contradiction flags. |
| `citation_audit.json` | JSON | Granular document existence, section resolution, authority, supersession, and auto-attachment metrics. |
| `metrics.json` | JSON | Summary scores across all 7 rubric dimensions, claim-level recall, and citation audit statistics. |
| `per_case_results.csv` | CSV | Flat tabular export of per-case scores, latencies, and citation counts for spreadsheet analysis. |
| `error_analysis.md` | Markdown | Root cause analysis of observed failure modes (chunk #0 truncation, PII masking, auto-attached citation masking). |
| `run_metadata.json` | JSON | Reproducibility metadata, including git commit hash, python environment, and execution timestamp. |
| `README.md` | Markdown | This documentation and reproduction guide. |

---

## 3. Key Findings Summary

- **Composite Mean Rubric Score**: **2.69 / 4.0**
- **Dimension Averages**:
  - `factual_correctness`: 1.92 / 4.0
  - `groundedness`: 2.96 / 4.0
  - `citation_precision`: 0.93 / 4.0
  - `citation_completeness`: 3.47 / 4.0
  - `completeness`: 1.95 / 4.0
  - `abstention_quality`: 3.60 / 4.0
  - `conflict_handling`: 4.00 / 4.0
- **Citation Audit**:
  - Total Citations Analyzed: 603
  - Valid Document Rate: 100.0% (all documents exist in `knowledge-base/`)
  - Auto-Attached Citation Rate: **100.0%** (all attached by validator/fallback logic, 0% model-generated)
  - Superseded Document Citation Rate: 0.0% (superseded docs successfully filtered at retrieval)
- **Claim Recall**: **39.1%** (severe bottleneck caused by fallback engine only extracting chunk #0).

---

## 4. Single-Command Reproduction

To regenerate the dataset, execute the evaluation pipeline, and rebuild all artifacts:

```bash
# Activate virtual environment
conda activate cometchat-env

# 1. Regenerate 150-case benchmark dataset
PYTHONPATH=. python scratch/generate_answer_quality_v1_dataset.py

# 2. Run evaluation engine and regenerate all deliverables
PYTHONPATH=. python scratch/evaluate_answer_quality_v1.py
```
