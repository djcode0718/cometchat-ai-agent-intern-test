# Aster & Row — Knowledge Retrieval Evaluation: BM25 vs Dense vs Hybrid

**Document Version:** 1.0.0  
**Audit Date:** 2026-11-26  
**Auditor:** Automated Engineering Evaluation Harness  
**Branch:** `feat/aster-row-production-hardening`  
**Test Suite:** `tests/test_routing_guard_retrieval_benchmarks.py`  
**Artifact Data:** `evaluation/production_hardening_2026_11_26/retrieval_results.json`  
**Knowledge Base:** 12 authoritative Markdown documents (`knowledge/*.md`) chunked into verified policy fragments  

---

## 1. Executive Summary

Grounding conversational AI responses in verified corporate policy is essential for preventing hallucinations in customer support. Aster & Row evaluates three distinct information retrieval architectures:
1. **BM25 Retriever:** Sparse keyword matching optimized for exact domain terms (SKUs, policy codes like `RET-2026-01`, numeric limits like `30 days`, `45 days`).
2. **Dense Semantic Retriever:** Cosine similarity over 384-dimensional dense vectors using `sentence-transformers/all-MiniLM-L6-v2`.
3. **Hybrid Retriever:** Reciprocal Rank Fusion (RRF) combining sparse BM25 and dense semantic ranks with rank penalty $k = 60$.

### Key Empirical Findings
- **Hybrid Recall@1:** **91.67%** (vs 83.33% for BM25 and 83.33% for Dense).
- **Hybrid Recall@3:** **100.00%** (vs 91.67% for BM25 and 100.00% for Dense).
- **Hybrid Recall@5:** **100.00%** (12 / 12 benchmark cases retrieved all target ground-truth policy chunks).
- **Hybrid Mean Reciprocal Rank (MRR):** **0.9444** (highest ranking precision across all strategies).
- **Mean Retrieval Latency:** **5.16 ms** (Hybrid RRF), compared to 0.19 ms (BM25) and 6.63 ms (Dense).
- **Citation Validity Rate:** **100.00%** (100% of generated response citations link to extant, verified knowledge base chunk IDs).

---

## 2. Benchmark Comparison Table

All retrievers were evaluated over the authoritative curated benchmark cases (`src/retrieval/benchmark.py`) covering complex policy exceptions, domestic shipping thresholds, international delivery times, warranty exclusions, and product care guidelines:

| Strategy | Recall@1 | Recall@3 | Recall@5 | MRR | Mean Latency (ms) | Citation Validity |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **BM25 (Sparse)** | 83.33% | 91.67% | 91.67% | 0.8750 | **0.19 ms** | 100.00% |
| **Dense (Semantic)** | 83.33% | 100.00% | 100.00% | 0.9167 | 6.63 ms | 100.00% |
| **Hybrid (RRF Fusion)** | **91.67%** | **100.00%** | **100.00%** | **0.9444** | **5.16 ms** | **100.00%** |

---

## 3. Analysis & Strategy Comparison

### 3.1 Why Hybrid Outperforms Individual Strategies
- **Exact Numeric Matching:** When a customer asks about a specific duration (e.g. "within 30 days" or "within 45 days for TrailPlus"), Dense embeddings occasionally rank general membership descriptions above specific return window clauses. BM25 directly scores exact lexical tokens.
- **Conceptual Paraphrasing:** When a customer asks "Can I return a final sale item that arrived damaged?", the user does not use the exact phrase "shipping exception reporting window". Dense vector similarity maps "damaged" and "defective" to `04-damaged-or-wrong-items.md`.
- **RRF Synergy:** By combining reciprocal ranks ($RRF\_score = \frac{1}{60 + rank_{bm25}} + \frac{1}{60 + rank_{dense}}$), chunks supported by *both* lexical precision and semantic relevance are boosted to Rank 1. This lifts Recall@1 from 83.33% to 91.67% and achieves an MRR of 0.9444.

### 3.2 Citation Validity & Anti-Hallucination Invariant
Every retrieved chunk emitted into the agent's prompt contains an immutable `chunk_id` (e.g. `RET-2026-01::standard-return-window`). The post-generation output validator (`src/llm/validator.py`) inspects the LLM's response:
- Any citation string not present in the pre-approved evidence pack is automatically stripped.
- If the LLM generates claims contradictory to approved evidence, the fallback engine replaces the output with verified policy text.
- Verified Citation Validity across the suite is **100.00%**.
