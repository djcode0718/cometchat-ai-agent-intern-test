# Phase 9 — Multi-Concurrency Performance Load Evaluation Report

**Evaluation Timestamp**: 2026-11-26T08:04:01.331196+00:00  
**Verified Git Commit**: `13859eadc43d982ee7a0b0d606513b7cebcde32e`  
**Harness**: `tests/test_performance_load_benchmarks.py` (`ThreadPoolExecutor` + FastAPI `TestClient`)  
**Raw Benchmark Artifact**: `evaluation/production_hardening_2026_11_26/performance_results.json`  
**Evaluation Scope**: Concurrency levels C=1, C=5, C=10, C=25, C=50 evaluated at **N=500 requests per tier** (2500 total requests evaluated).  

---

## 1. Executive Summary

To evaluate Aster & Row under multi-user concurrency, we conducted a multi-concurrency benchmark testing knowledge synthesis, order status retrieval, and transactional HITL approval creation across 5 concurrency tiers. Each tier ran a dedicated batch of N=500 requests.

### Key Performance Summary by Concurrency Tier (N=500 requests per tier)
| Concurrency (C) | Requests (N) | Run Duration (s) | Throughput (req/s) | Mean Latency (ms) | p50 Latency (ms) | p90 Latency (ms) | p95 Latency (ms) | p99 Latency (ms) | Error Rate (%) |
| :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **C=1** | 500 | 2.92 s | **170.97 req/s** | 5.84 ms | 7.01 ms | 8.96 ms | 10.64 ms | 12.30 ms | **0.00%** |
| **C=5** | 500 | 3.22 s | **155.35 req/s** | 32.08 ms | 37.95 ms | 51.74 ms | 65.71 ms | 217.91 ms | **0.00%** |
| **C=10** | 500 | 4.17 s | **119.96 req/s** | 82.76 ms | 82.74 ms | 152.21 ms | 195.50 ms | 358.46 ms | **0.00%** |
| **C=25** | 500 | 2.98 s | **167.91 req/s** | 146.39 ms | 174.69 ms | 315.82 ms | 336.33 ms | 428.83 ms | **0.00%** |
| **C=50** | 500 | 5.11 s | **97.80 req/s** | 497.33 ms | 518.96 ms | 976.62 ms | 1027.13 ms | 1135.27 ms | **0.00%** |

*Note on Run Duration*: Each tier ran a short-burst batch of 500 requests (taking between 2.9s and 5.1s per tier) under TestClient thread pool execution to measure concurrency scaling without artificial server saturation.

---

## 2. Analysis of Concurrency Scaling & Resiliency

### 1. Throughput Distribution Across Tiers
Peak throughput of **170.97 req/s** occurred at concurrency **C=1**, where single-threaded execution avoids Python GIL and connection pool contention. Under multi-threaded concurrency (C=5 to C=25), throughput remained between 119.96 and 167.91 req/s, and at C=50 settled at 97.80 req/s.

### 2. Latency Predictability
- Low concurrency (C=1 to C=5): Median response times remained under 40 ms.
- Medium concurrency (C=10 to C=25): Median response times scaled from 82.74 ms to 174.69 ms.
- High concurrency (C=50): Median response time was 518.96 ms, with p95 at 1,027.13 ms and p99 at 1,135.27 ms.

### 3. Zero Error Rate Under Load
Across all 5 concurrency tiers (2500 total requests), **error rate was strictly 0.00% (0 failures)**.
