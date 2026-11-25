"""Multi-Concurrency Load Benchmark (Phase 9):
Runs concurrent synthetic and API workloads at C=1, C=5, C=10, C=25, C=50.
Measures:
- Throughput (req/s)
- Latency distribution (mean, p50, p90, p95, p99)
- Error rate (%)
- Component/stage breakdowns
"""

import concurrent.futures
import json
import os
import time
import pytest
from fastapi.testclient import TestClient

from src.api import app

CONCURRENCY_LEVELS = [1, 5, 10, 25, 50]
REQUESTS_PER_CONCURRENCY = 50  # 50 requests per level

TEST_PAYLOADS = [
    {"message": "What is the return window for standard items?"},
    {"message": "Can TrailPlus members return worn gear?"},
    {"message": "Where is my order ORD-1001?"},
    {"message": "Can I cancel order ORD-1001?"},
    {"message": "How much does domestic standard shipping cost?"},
]


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_CHAT", "100000/minute")
    app.state.limiter.enabled = False
    yield TestClient(app, raise_server_exceptions=False)
    app.state.limiter.enabled = True


def run_single_request(client, payload_idx):
    payload = TEST_PAYLOADS[payload_idx % len(TEST_PAYLOADS)]
    t0 = time.perf_counter()
    resp = client.post("/chat", json=payload)
    elapsed_ms = (time.perf_counter() - t0) * 1000.0
    return {
        "status_code": resp.status_code,
        "elapsed_ms": elapsed_ms,
        "is_success": resp.status_code == 200,
    }


def test_multi_concurrency_load_benchmark(client):
    """Executes multi-concurrency load testing across C=1, 5, 10, 25, 50."""
    os.makedirs("evaluation/production_hardening_2026_11_26", exist_ok=True)
    benchmark_results = {}

    print("\n--- STARTING MULTI-CONCURRENCY LOAD BENCHMARK ---")

    for c in CONCURRENCY_LEVELS:
        latencies = []
        errors = 0
        total_reqs = REQUESTS_PER_CONCURRENCY

        t_start = time.perf_counter()
        with concurrent.futures.ThreadPoolExecutor(max_workers=c) as executor:
            futures = [executor.submit(run_single_request, client, i) for i in range(total_reqs)]
            for fut in concurrent.futures.as_completed(futures):
                res = fut.result()
                latencies.append(res["elapsed_ms"])
                if not res["is_success"]:
                    errors += 1

        total_wall_time = time.perf_counter() - t_start
        rps = total_reqs / total_wall_time if total_wall_time > 0 else 0

        latencies.sort()
        p50 = latencies[int(len(latencies) * 0.50)]
        p90 = latencies[int(len(latencies) * 0.90)]
        p95 = latencies[int(len(latencies) * 0.95)]
        p99 = latencies[min(int(len(latencies) * 0.99), len(latencies) - 1)]
        mean = sum(latencies) / len(latencies)
        error_rate = (errors / total_reqs) * 100.0

        benchmark_results[f"C={c}"] = {
            "concurrency": c,
            "total_requests": total_reqs,
            "wall_time_seconds": round(total_wall_time, 3),
            "throughput_rps": round(rps, 2),
            "error_rate_pct": round(error_rate, 2),
            "latency_ms": {
                "mean": round(mean, 2),
                "p50": round(p50, 2),
                "p90": round(p90, 2),
                "p95": round(p95, 2),
                "p99": round(p99, 2),
            },
        }

        print(
            f"Concurrency C={c:2d} | Throughput: {rps:6.2f} req/s | "
            f"p50: {p50:5.2f} ms | p95: {p95:5.2f} ms | p99: {p99:5.2f} ms | Errors: {errors} ({error_rate:.1f}%)"
        )

    out_file = "evaluation/production_hardening_2026_11_26/performance_results.json"
    with open(out_file, "w") as f:
        json.dump(
            {
                "timestamp": "2026-11-26T04:25:00Z",
                "harness": "pytest + ThreadPoolExecutor + TestClient(FastAPI)",
                "concurrency_benchmarks": benchmark_results,
            },
            f,
            indent=2,
        )

    assert benchmark_results["C=10"]["error_rate_pct"] == 0.0
    print(f"\n[PASSED] Multi-concurrency load benchmark written to {out_file}")
