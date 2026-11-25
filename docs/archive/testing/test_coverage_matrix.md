# Test Coverage Matrix: Aster & Row AI Customer Support Agent

**Assessment Date**: 2026-11-25  
**Baseline Commit**: `a4cfc0d54665d567d0a1be7158190769db1562e7`  
**Test Suite Framework**: `pytest`, `pytest-asyncio`, `FastAPI TestClient`, `httpx`  

---

## 1. Component Architecture & Test Mapping

The following matrix documents the testing topology across all architectural layers of the Aster & Row system, classifying test coverage into:
- **Unit Tests**: Isolated unit tests exercising core functions, classes, and validators.
- **Integration Tests**: Tests verifying interactions between multiple components (e.g. Resolver + Authority, Router + Orchestrator).
- **End-to-End (E2E) Tests**: Full request-to-response turn simulations through FastAPI `TestClient` or `AgentOrchestrator`.
- **Failure-Path Tests**: Resilience against invalid inputs, missing keys, timeouts, network exceptions, and provider failover.
- **Performance Tests**: Latency percentiles, throughput (RPS), and concurrency behavior under load.

| Subsystem / Module | Source File | Unit | Integration | E2E | Failure Path | Performance | Existing Test Files |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :--- |
| **API Layer** | `src/api.py` | Yes | Yes | Yes | Yes | Yes | `tests/test_api.py`, `tests/test_campaign_e2e.py` |
| **Agent Orchestrator** | `src/agent/orchestrator.py` | Yes | Yes | Yes | Yes | Yes | `tests/test_orchestrator_generation.py`, `tests/test_agent_orchestrator_hardening.py` |
| **Router & Intent Engine** | `src/agent/router.py` | Yes | Yes | Yes | Yes | No | `tests/test_router.py`, `tests/test_customer_intents.py` |
| **Decision & Safety Engine** | `src/agent/decision.py` | Yes | Yes | Yes | Yes | No | `tests/test_decision.py`, `tests/test_agent_security.py` |
| **Conversation State** | `src/agent/state.py` | Yes | Yes | Yes | No | No | `tests/test_agent_multiturn.py` |
| **Core Configuration** | `src/core/config.py` | Yes | No | No | Yes | No | `tests/test_config.py` |
| **Core Domain Models** | `src/core/models.py` | Yes | No | No | Yes | No | `tests/test_models.py` |
| **Session Manager** | `src/core/session.py` | Yes | Yes | Yes | Yes | No | `tests/test_session.py` |
| **Knowledge Parser** | `src/knowledge/parser.py` | Yes | Yes | No | Yes | No | `tests/test_parser.py` |
| **Section-Aware Chunker**| `src/knowledge/chunker.py` | Yes | Yes | No | Yes | No | `tests/test_chunker.py` |
| **Knowledge Ingestion** | `src/knowledge/service.py` | Yes | Yes | No | Yes | No | `tests/test_ingestion.py`, `tests/test_campaign_knowledge_lifecycle.py` |
| **Policy Authority** | `src/knowledge/authority.py`| Yes | Yes | Yes | Yes | No | `tests/test_authority.py` |
| **Policy Supersession** | `src/knowledge/supersession.py`| Yes | Yes | Yes | Yes | No | `tests/test_supersession.py` |
| **Policy Conflict Engine**| `src/knowledge/conflict.py`| Yes | Yes | Yes | Yes | No | `tests/test_conflict.py` |
| **Evidence Formulation** | `src/knowledge/evidence.py`| Yes | Yes | Yes | Yes | No | `tests/test_evidence.py` |
| **Knowledge Resolver** | `src/knowledge/resolver.py`| Yes | Yes | Yes | Yes | No | `tests/test_resolver.py` |
| **BM25 Lexical Retriever**| `src/retrieval/bm25.py` | Yes | Yes | No | Yes | No | `tests/test_bm25.py` |
| **Dense Vector Retriever**| `src/retrieval/dense.py` | Yes | Yes | No | Yes | No | `tests/test_dense.py` |
| **Hybrid RRF Fusion** | `src/retrieval/hybrid.py` | Yes | Yes | Yes | Yes | Yes | `tests/test_hybrid.py`, `tests/test_rrf.py` |
| **Retrieval Benchmark** | `src/retrieval/benchmark.py`| Yes | Yes | No | No | No | `tests/test_retrieval_benchmark.py`, `tests/test_retrieval_metrics.py` |
| **LLM Output Validator** | `src/llm/validator.py` | Yes | Yes | Yes | Yes | No | `tests/test_validator.py` |
| **OpenRouter Provider** | `src/llm/openrouter.py` | Yes | Yes | Yes | Yes | No | `tests/test_openrouter.py`, `tests/test_campaign_provider_resilience.py` |
| **OpenRouter Fallback** | `src/llm/openrouter_chain.py`| Yes | Yes | Yes | Yes | No | `tests/test_openrouter.py`, `tests/test_campaign_provider_resilience.py` |
| **Groq Provider** | `src/llm/grok.py` (Groq)| Yes | Yes | No | Yes | No | `tests/test_llm_providers.py` |
| **LLM Factory** | `src/llm/factory.py` | Yes | Yes | Yes | Yes | No | `tests/test_llm_provider.py` |
| **Prompt Assembly** | `src/llm/prompts.py` | Yes | Yes | Yes | No | No | `tests/test_prompts.py` |
| **Order Repository** | `src/tools/orders.py` | Yes | Yes | Yes | Yes | No | `tests/test_orders.py` |
| **Order Sanitizer & PII**| `src/tools/sanitizer.py`| Yes | Yes | Yes | Yes | No | `tests/test_order_sanitization.py` |
| **Order Reconciler** | `src/tools/reconciler.py` | Yes | Yes | Yes | Yes | No | `tests/test_order_reconciliation.py` |
| **CLI Interface** | `src/cli.py` | Yes | Yes | No | Yes | No | `tests/test_cli.py` |

---

## 2. Identified Gaps & Target Campaign Plan

Based on the inspection of the baseline codebase and test files, the following test gaps were identified for this campaign:

1. **End-to-End Workflow Scenarios (E2E-001 through E2E-010)**:
   - Need formal end-to-end integration tests through the FastAPI test client covering standard factual queries, how-tos, multi-part inquiries, policy exceptions, unknown queries, provider failures, total failover, citation validation rejection, empty retrieval fallback, and idempotency / state isolation.
   - *Target*: Implemented in `tests/test_campaign_e2e.py` and output to `evaluation/testing/e2e_results.json`.
2. **Provider Response & Resilience Fault Matrix**:
   - Comprehensive test harness for all 20 HTTP error / malformed response conditions (JSON, plain text, empty, 400, 401, 402, 429, 500, 502, 503, timeouts, resets, long outputs, malformed citations).
   - Gated opt-in live test suite (`LIVE_LLM_TESTS=1`).
   - *Target*: Implemented in `tests/test_campaign_provider_resilience.py` and output to `evaluation/testing/provider_results.json`.
3. **Retrieval Benchmark & Diagnostic Suite**:
   - Standalone retrieval quality evaluation across both the Standard 50 and Difficult 50 benchmarks measuring Recall@K, Precision@K, MRR, and Hit Rate@K, comparing BM25, FAISS, and Hybrid.
   - *Target*: Implemented in `scratch/evaluate_retrieval_suite.py` and output to `evaluation/testing/retrieval_metrics.json` and `evaluation/testing/retrieval_analysis.md`.
4. **Adversarial, Security & Injection Suite**:
   - System instruction override attempts, synthetic poisoned document injection, PII extraction, and citation forgery.
   - *Target*: Implemented in `tests/test_campaign_adversarial.py` and output to `evaluation/testing/adversarial_results.json` and `evaluation/testing/adversarial_analysis.md`.
5. **API Reliability & Concurrency**:
   - Schema validation fuzzing, dependency loss (missing FAISS/KB/DB), and multi-threaded race condition tests.
   - *Target*: Implemented in `tests/test_campaign_api_reliability.py` and output to `evaluation/testing/api_reliability_results.json`.
6. **Knowledge Base Lifecycle & Re-indexing (KB-001 through KB-008)**:
   - Isolated document creation, update, deletion, supersession, and corruption tests in temporary fixtures.
   - *Target*: Implemented in `tests/test_campaign_knowledge_lifecycle.py` and output to `evaluation/testing/knowledge_lifecycle_results.json` and `evaluation/testing/knowledge_lifecycle_report.md`.
7. **Offline Performance & Concurrency Load Test**:
   - Controlled multi-concurrency benchmarking (1, 5, 10, 25 users) measuring p50, p95, p99, throughput, and resource utilization.
   - *Target*: Implemented in `scratch/run_offline_load_test.py` and output to `evaluation/testing/performance_results.json` and `evaluation/testing/performance_report.md`.
