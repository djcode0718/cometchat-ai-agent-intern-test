#!/usr/bin/env python3
"""Execute three load scenarios and record measured performance metrics to CSV."""

import os
import subprocess
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = PROJECT_ROOT / "docs" / "results"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
PYTHON_EXEC = "/Users/sj/miniforge3/envs/cometchat-env/bin/python"

SCENARIOS = [
    {
        "name": "scenario_a_mock_instrumented",
        "description": "Mock LLM with Observability & Prometheus Instrumentation ON",
        "env": {"APP_ENV": "production", "LLM_PROVIDER": "mock", "OBSERVABILITY_ENABLED": "true"},
    },
    {
        "name": "scenario_b_mock_uninstrumented",
        "description": "Mock LLM with Observability & Prometheus Instrumentation OFF",
        "env": {"APP_ENV": "production", "LLM_PROVIDER": "mock", "OBSERVABILITY_ENABLED": "false"},
    },
    {
        "name": "scenario_c_live_llm",
        "description": "Live LLM Provider",
        "env": {"APP_ENV": "production", "OBSERVABILITY_ENABLED": "true"},
    },
]


def run_server(env_vars: dict) -> subprocess.Popen:
    """Start local uvicorn server process."""
    run_env = os.environ.copy()
    run_env.update(env_vars)
    run_env["PYTHONPATH"] = str(PROJECT_ROOT)
    cmd = [PYTHON_EXEC, "-m", "uvicorn", "src.api:app", "--port", "8009", "--log-level", "warning"]
    proc = subprocess.Popen(cmd, env=run_env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return proc


def wait_for_server(port: int = 8009, timeout: float = 15.0) -> bool:
    """Wait for FastAPI server to become responsive."""
    import urllib.request
    start = time.time()
    url = f"http://127.0.0.1:{port}/health"
    while time.time() - start < timeout:
        try:
            with urllib.request.urlopen(url, timeout=1.0) as resp:
                if resp.status == 200:
                    return True
        except Exception:
            time.sleep(0.3)
    return False


def run_benchmark():
    summary_csv = OUTPUT_DIR / "observability_overhead_comparison.csv"
    results = []

    print("=================================================================")
    print(" Aster & Row — Observability Load Testing Benchmark (Locust)")
    print("=================================================================")

    for sc in SCENARIOS:
        sc_name = sc["name"]
        print(f"\n---> Running {sc_name}: {sc['description']}...")

        # Check for scenario C live key
        if sc_name == "scenario_c_live_llm":
            if not os.getenv("OPENROUTER_API_KEY") and not os.getenv("GROQ_API_KEY"):
                print("     [SKIP] Live LLM API key not present in environment; skipping scenario C.")
                results.append({
                    "Scenario": sc_name,
                    "Description": sc["description"],
                    "Status": "SKIPPED (No API key)",
                    "Requests": 0,
                    "RPS": "N/A",
                    "p50_ms": "N/A",
                    "p95_ms": "N/A",
                    "p99_ms": "N/A",
                    "Failures": "0",
                })
                continue

        server_proc = run_server(sc["env"])
        try:
            if not wait_for_server(8009):
                print(f"     [ERROR] Server failed to start for {sc_name}")
                continue

            csv_prefix = OUTPUT_DIR / f"locust_{sc_name}"
            locust_cmd = [
                PYTHON_EXEC, "-m", "locust",
                "-f", str(PROJECT_ROOT / "loadtest" / "locustfile.py"),
                "--host", "http://127.0.0.1:8009",
                "--headless",
                "-u", "10",
                "-r", "5",
                "-t", "20s",
                "--csv", str(csv_prefix),
                "--only-summary",
            ]
            subprocess.run(locust_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

            # Parse generated stats CSV
            stats_file = OUTPUT_DIR / f"locust_{sc_name}_stats.csv"
            if stats_file.exists():
                import csv
                with open(stats_file) as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        if row["Name"] == "Aggregated":
                            results.append({
                                "Scenario": sc_name,
                                "Description": sc["description"],
                                "Status": "COMPLETED",
                                "Requests": row["Request Count"],
                                "RPS": row["Requests/s"],
                                "p50_ms": row["50%"],
                                "p95_ms": row["95%"],
                                "p99_ms": row["99%"],
                                "Failures": row["Failure Count"],
                            })
                            print(f"     Done. Requests: {row['Request Count']}, RPS: {row['Requests/s']}, p50: {row['50%']}ms, p95: {row['95%']}ms")
        finally:
            server_proc.terminate()
            server_proc.wait()

    # Write summary comparison CSV
    with open(summary_csv, "w", newline="") as f:
        import csv
        fieldnames = ["Scenario", "Description", "Status", "Requests", "RPS", "p50_ms", "p95_ms", "p99_ms", "Failures"]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in results:
            writer.writerow(r)

    print(f"\n[SUCCESS] Benchmark summary saved to: {summary_csv}")


if __name__ == "__main__":
    run_benchmark()
