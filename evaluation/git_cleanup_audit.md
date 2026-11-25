# Aster & Row — Git Cleanup & Changes Audit Report

**Generated Date**: 2026-11-25T19:45:00Z  
**Repository**: `cometchat-ai-agent-intern-test`  
**Current Branch**: `main`  
**Current HEAD**: `a4cfc0d54665d567d0a1be7158190769db1562e7`  
**Remote Configuration**: `origin https://github.com/djcode0718/cometchat-ai-agent-intern-test.git (fetch & push)`  
**Upstream Tracking**: `origin/main` (up to date with HEAD)  

---

## 1. Executive Summary & Inventory Overview

A complete audit of the Aster & Row codebase was conducted to distinguish relevant, production-grade application source code, automated test suites, critical reproducible evaluation benchmarks, and configuration files from temporary scratch scripts, zip archives, debug caches, and untracked backups.

- **Total Modified Tracked Files**: 12 files (including 1 compiled bytecode artifact `config.cpython-311.pyc` which must be untracked/reverted).
- **Total Untracked Files/Directories**: 100+ files across temporary evaluation stages, scratch scripts, zip backups, and campaign artifacts.
- **Identified Nested Repositories or Submodules**: None (`git submodule status` returned clean 0).
- **Security / Secret Leakage Scan**: 
  - `.env` is strictly ignored by `.gitignore` and has never been staged.
  - Candidate files scanned with regex patterns for OpenRouter (`sk-or-...`), Groq (`gsk_...`), OpenAI (`sk-...`), and Google AI keys.
  - Only test mock dummy keys (`sk-or-test-mock-key`) exist in `tests/test_openrouter.py`. Zero live secrets found in candidate source or test files.

---

## 2. File Classification Inventory

### Category A: Relevant Application Source (To Commit)
These files represent the core multi-model provider architecture (OpenRouter fallback chain, Groq integration, validator multi-chunk aggregation, intent routing hardening, decision engine security updates, and configuration loading).

1. `src/agent/decision.py` (Decision engine regex tightening & security extraction guard)
2. `src/agent/orchestrator.py` (Configurable `retrieval_top_k` injection)
3. `src/agent/router.py` (Intent disambiguation for personal vs policy order inquiries)
4. `src/core/config.py` (OpenRouter configuration settings, defaults, and environment loading)
5. `src/knowledge/conflict.py` (Conflict resolver hardening)
6. `src/llm/factory.py` (Factory support for `openrouter` and `groq` provider chains)
7. `src/llm/prompts.py` (System prompt template updates)
8. `src/llm/validator.py` (Task 1: Fallback multi-chunk aggregation with 1500 char boundary and citation alignment)
9. `src/llm/openrouter.py` (OpenRouter provider client with error retry, exponential backoff, and model fallback)
10. `src/llm/openrouter_chain.py` (Multi-tiered model fallback chain: OpenRouter primary -> candidate models -> Groq backup -> local fallback)

### Category B: Automated Tests (To Commit)
These files provide comprehensive regression, resilience, security, lifecycle, and E2E validation.

1. `tests/test_validator.py` (Unit tests for multi-chunk fallback aggregation, truncation, and deduplication)
2. `tests/test_openrouter.py` (Unit tests for OpenRouter provider and fallback chain under mock conditions)
3. `tests/test_campaign_e2e.py` (E2E-001 through E2E-010 customer journey tests)
4. `tests/test_campaign_provider_resilience.py` (PR-01 through PR-23 provider error handling and cascade tests)
5. `tests/test_campaign_adversarial.py` (ADV-001 through ADV-010 security and prompt injection tests)
6. `tests/test_campaign_api_reliability.py` (API-001 through API-011 fuzzing, concurrency, and session tests)
7. `tests/test_campaign_knowledge_lifecycle.py` (KB-001 through KB-008 ingestion, chunking, and supersession tests)

### Category C: Important Evaluation & Audit Artifacts (To Commit)
Retained reproducible evidence, reports, and official benchmark datasets.

#### C.1 Official Curated Benchmarks
1. `evaluation/answer_quality_v1/stage3_difficult_50_answerable.json` (Curated 50 difficult scenarios, SHA256: `ceb7e55f884cc053dec3409161b8c94db2de3ab11099c04db36ddf457f52d4ad`)
2. `evaluation/answer_quality_v1/stage3_standard_50_answerable.json` (Curated 50 standard scenarios, SHA256: `f28541dbc415ae820615a067cd0e99021f8cf317226fccdfdbdaf1c94073aa00`)

#### C.2 Consolidated Stage Reports & Audit Artifacts
3. `evaluation/reports/stage_08_consolidated_evaluation.md` (Consolidated evaluation across Stages 1–7)
4. `evaluation/reports/stage_08_summary_metrics.json` (Reconciled summary metrics)
5. `evaluation/reports/llm_provider_failure_investigation.md` (Diagnostic investigation of Groq API failures)
6. `evaluation/reports/stage3_difficult_50_dataset_audit.md` (Difficult 50 benchmark audit)
7. `evaluation/reports/stage3_difficult_50_task1_evaluation.md` (Task 1 fallback evaluation on Difficult 50)
8. `evaluation/reports/stage3_standard_50_dataset_audit.md` (Standard 50 benchmark audit)

#### C.3 Final Evaluation Evidence Packages
9. `evaluation/final_openrouter_50/evaluation_summary.md` (OpenRouter evaluation summary)
10. `evaluation/final_openrouter_50/evaluation_metrics.json` (OpenRouter evaluation metrics)
11. `evaluation/final_openrouter_50/reproducibility_manifest.json` (OpenRouter manifest)
12. `evaluation/final_standard_50/evaluation_summary.md` (Standard 50 evaluation summary)
13. `evaluation/final_standard_50/evaluation_metrics.json` (Standard 50 evaluation metrics)
14. `evaluation/final_standard_50/reproducibility_manifest.json` (Standard 50 manifest)

#### C.4 Campaign Verification Suite Evidence (`evaluation/testing/`)
15. `evaluation/testing/test_campaign_summary.md` (Executive summary & engineering readiness review)
16. `evaluation/testing/test_coverage_matrix.md` (Coverage architecture matrix)
17. `evaluation/testing/regression_report.md` (Full regression verification report)
18. `evaluation/testing/coverage_report.md` (Code coverage analysis report)
19. `evaluation/testing/coverage.json` (Machine-readable statement coverage)
20. `evaluation/testing/retrieval_analysis.md` (BM25 vs FAISS vs Hybrid RRF comparison)
21. `evaluation/testing/retrieval_metrics.json` (Retrieval metrics on both benchmarks)
22. `evaluation/testing/adversarial_analysis.md` (Security vulnerability analysis)
23. `evaluation/testing/adversarial_results.json` (Results for ADV-001 - ADV-010)
24. `evaluation/testing/performance_report.md` (Concurrency load and latency profiling report)
25. `evaluation/testing/performance_results.json` (Load test metrics across 1–25 concurrent users)
26. `evaluation/testing/knowledge_lifecycle_report.md` (Hot-reloading & supersession lifecycle report)
27. `evaluation/testing/knowledge_lifecycle_results.json` (Results for KB-001 - KB-008)
28. `evaluation/testing/api_reliability_results.json` (Results for API-001 - API-011)
29. `evaluation/testing/provider_results.json` (Results for PR-01 - PR-23)
30. `evaluation/testing/e2e_results.json` (Results for E2E-001 - E2E-010)
31. `evaluation/testing/reproducibility_manifest.json` (Comprehensive testing campaign manifest)

### Category D: Project Configuration (To Commit)
1. `.env.example` (Updated with OpenRouter provider configuration template)
2. `requirements.txt` (Added fastapi, uvicorn, coverage, pytest-cov)
3. `.gitignore` (Updated to ignore zip archives, code-context/, .cache/, .coverage, and temporary scratch files)

---

## 3. Files Excluded from Commit

### Excluded Temporary Artifacts & Caches:
- `src/core/__pycache__/config.cpython-311.pyc` (Binary bytecode; revert from git tracking)
- `.coverage` (Binary coverage database)
- `.cache/` (Local OpenRouter response cache)
- `evaluation/__pycache__/`, `tests/__pycache__/`, `scratch/__pycache__/`

### Excluded Zip Files & Redundant Copies:
- `code-context.zip` (2.2MB archive)
- `code-context/` (Extracted duplicated tree)
- `evaluation.zip` (445KB archive)
- `knowledge-base.zip` (12KB archive)
- `aster_row_synthetic_eval_v2/` (Superceded synthetic eval dataset)

### Excluded Scratch / Temporary Evaluator Scripts:
- `scratch/curate_stage3_difficult_50.py`
- `scratch/curate_standard_50_benchmark.py`
- `scratch/evaluate_agent_decision_v1.py`
- `scratch/evaluate_answer_quality_v1.py`
- `scratch/evaluate_difficult_50.py`
- `scratch/evaluate_retrieval_v2.py`
- `scratch/evaluate_security_adversarial_v1.py`
- `scratch/finalize_evaluation_artifacts.py`
- `scratch/generate_answer_quality_v1_dataset.py`
- `scratch/generate_retrieval_v2_dataset.py`
- `scratch/generate_stage_04_dataset.py`
- `scratch/generate_stage_05_dataset.py`
- `scratch/run_campaign_adversarial_and_api_tests.py`
- `scratch/run_campaign_e2e_and_provider_tests.py`
- `scratch/run_campaign_knowledge_lifecycle.py`
- `scratch/run_final_openrouter_evaluations.py`
- `scratch/run_offline_load_test.py`
- `scratch/run_retrieval_evaluation.py`
- `scratch/run_standard_50_evaluation.py`
- `scratch/test_standard_50_eval.py`

*(Note: These scratch scripts remain safe and undisturbed on disk in `scratch/`, but are omitted from git staging.)*

### Excluded Intermediate Historical Results:
- `evaluation/results/baseline_reproduced.json`
- `evaluation/results/novel_baseline_reproduced.json`
- `evaluation/results/stage3_difficult_50_task1_results.json`
- `evaluation/results_committed_backup/`
- `evaluation/agent_decision_v1/`
- `evaluation/retrieval_v2/`
- `evaluation/security_adversarial_v1/`
- `evaluation/fault_injection_v1/`
- `evaluation/load_v1/`
- Raw intermediate `.jsonl` trace dumps from earlier evaluation phases.

---

## 4. Working Tree & Remote Synchronization Status

- **Working Tree Cleanliness**: No tracked files will be discarded. Untracked temporary files and zip archives remain on the filesystem but are excluded by updated `.gitignore`.
- **Remote Synchronization**: `HEAD` is up to date with `origin/main`. No divergence detected. A standard fast-forward commit and push will succeed without force-pushing.
