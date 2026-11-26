# Phase 6 — Hybrid Knowledge Retrieval Strategy Evaluation Report

**Evaluation Timestamp**: 2026-11-26T08:03:40.999411+00:00  
**Verified Git Commit**: `13859eadc43d982ee7a0b0d606513b7cebcde32e`  
**Evaluation Scope**: N=12 standard benchmark queries across 53 policy knowledge chunks  
**Raw Benchmark Artifact**: `evaluation/production_hardening_2026_11_26/retrieval_results.json`  

---

## 1. Executive Summary

Aster & Row implements a hybrid retrieval architecture combining an inverted index (Rank-BM25) with a dense semantic vector index (SentenceTransformer `all-MiniLM-L6-v2`) via Reciprocal Rank Fusion (RRF).

### Strategy Performance Comparison (N=12 queries)
| Strategy | Recall@1 | Recall@3 | Recall@5 | MRR | Mean Latency | Citation Validity |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **BM25 Only** | 83.33% | 91.67% | 91.67% | 0.875 | 0.61 ms | 100.0% |
| **Dense Only (MiniLM)** | 83.33% | 100.00% | 100.00% | 0.9167 | 7.21 ms | 100.0% |
| **Hybrid (BM25 + Dense RRF)**| **91.67%** | **100.00%** | **100.00%** | **0.9444** | 5.27 ms | **100.0%** |

---

## 2. Technical Findings & Recall Analysis

1. **Dense Equals Hybrid at Recall@3**:
   Both Dense retrieval alone and Hybrid fusion achieve identical **100.00% Recall@3** (12 / 12) and **100.00% Recall@5**.
2. **Hybrid Advantage at Recall@1**:
   The sole measured advantage of Hybrid fusion over Dense retrieval on this N=12 dataset is on Recall@1:
   - Hybrid achieves **91.67% Recall@1** (11 of 12 cases rank the golden chunk first).
   - Dense achieves **83.33% Recall@1** (10 of 12 cases rank the golden chunk first).
   - Hybrid boosts the top rank on exactly **1 of 12 cases** due to exact keyword reinforcement from BM25.
3. **Citation Validity**:
   All 3 strategies maintained **100.00% citation validity**, ensuring that every retrieved chunk mapped to active policy documents without hallucinated paths.
