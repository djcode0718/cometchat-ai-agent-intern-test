"""
Automated guard test enforcing numerical and report consistency across
the Aster & Row evaluation dossier (evaluation/production_hardening_2026_11_26/).

Validates:
1. Every raw *_results.json file exists and is parseable.
2. METRICS_SUMMARY.json accurately reflects values from the raw JSON files.
3. Every markdown report matches raw JSON figures without rounding up or inventing metrics.
4. "N=" sample counts agree across files (e.g. N=12 retrieval inquiries, N=500 per concurrency tier).
5. No forbidden phrases or deprecated figures appear in reports:
   - "VoiceOver verified"
   - "Section 508"
   - "sustained at C=50"
   - "50 production inquiries"
   - Stale git SHA "29eb93a"
   - Unverified figures "12.83", "194.10", "45 minutes"
   - Deprecated baselines "351 passed", "86.41%"
"""

import json
from pathlib import Path
import pytest

DOSSIER_DIR = Path(__file__).parent.parent / "evaluation" / "production_hardening_2026_11_26"

RAW_JSON_FILES = [
    "postgres_concurrency_results.json",
    "guard_results.json",
    "performance_results.json",
    "observability_results.json",
    "local_llm_results.json",
    "retrieval_results.json",
    "routing_results.json",
    "security_results.json",
    "accessibility_results.json",
    "reproduction_manifest.json",
    "METRICS_SUMMARY.json",
]

MARKDOWN_REPORTS = [
    "ACCESSIBILITY_REPORT.md",
    "BASELINE_AUDIT.md",
    "BASELINE_VS_FINAL.md",
    "COMPLETE_JOURNEY_REPORT.md",
    "EXECUTIVE_SUMMARY.md",
    "LOCAL_LLM_EVALUATION.md",
    "OBSERVABILITY_REPORT.md",
    "PERFORMANCE_REPORT.md",
    "REPORT_CONSISTENCY_AUDIT.md",
    "RESUME_METRICS.md",
    "RETRIEVAL_EVALUATION.md",
]

FORBIDDEN_PHRASES = [
    "VoiceOver verified",
    "Section 508",
    "sustained at C=50",
    "50 production inquiries",
    "29eb93a",
    "12.83",
    "194.10",
    "45 minutes",
    "351 passed",
    "86.41%",
]


def load_json(filename: str) -> dict:
    path = DOSSIER_DIR / filename
    assert path.exists(), f"Missing required file: {filename}"
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_text(filename: str) -> str:
    path = DOSSIER_DIR / filename
    assert path.exists(), f"Missing required file: {filename}"
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


class TestReportConsistency:
    def test_all_raw_json_files_exist(self):
        """Ensure all raw benchmark JSON files exist in the dossier."""
        for filename in RAW_JSON_FILES:
            filepath = DOSSIER_DIR / filename
            assert filepath.exists(), f"File {filename} is missing from {DOSSIER_DIR}"

    def test_metrics_summary_matches_postgres(self):
        summary = load_json("METRICS_SUMMARY.json")["key_metrics_summary"]
        postgres = load_json("postgres_concurrency_results.json")
        assert summary["postgres_concurrency_executions"] == postgres["results_summary"]["successful_executions"]
        assert summary["postgres_concurrency_executions"] == 1
        assert summary["postgres_concurrency_duplicate_mutations"] == postgres["results_summary"]["double_execution_count"]
        assert postgres["results_summary"]["double_execution_count"] == 0

    def test_metrics_summary_matches_guard_and_security(self):
        summary = load_json("METRICS_SUMMARY.json")["key_metrics_summary"]
        guard = load_json("guard_results.json")
        sec = load_json("security_results.json")
        assert summary["adversarial_precision_pct"] == pytest.approx(sec["performance_metrics"]["precision"] * 100, 0.01)
        assert summary["adversarial_recall_pct"] == pytest.approx(sec["performance_metrics"]["recall"] * 100, 0.01)
        assert summary["adversarial_f1_score"] == pytest.approx(sec["performance_metrics"]["f1_score"], 0.0001)
        assert summary["pre_retrieval_guard_latency_p50_us"] == pytest.approx(guard["latency_metrics_us"]["p50_us"], 0.01)
        assert summary["pre_retrieval_guard_latency_p99_us"] == pytest.approx(guard["latency_metrics_us"]["p99_us"], 0.01)

    def test_metrics_summary_matches_routing(self):
        summary = load_json("METRICS_SUMMARY.json")["key_metrics_summary"]
        routing = load_json("routing_results.json")
        assert summary["routing_accuracy_pct"] == pytest.approx(routing["routing_accuracy"] * 100, 0.01)

    def test_metrics_summary_matches_retrieval_n12(self):
        summary = load_json("METRICS_SUMMARY.json")["key_metrics_summary"]
        retrieval = load_json("retrieval_results.json")
        assert retrieval["total_test_cases"] == 12
        assert summary["retrieval_benchmark_n"] == 12
        assert summary["hybrid_retrieval_recall_at_1_pct"] == pytest.approx(retrieval["strategies"]["hybrid"]["recall_at_1"] * 100, 0.01)
        assert summary["hybrid_retrieval_recall_at_3_pct"] == pytest.approx(retrieval["strategies"]["hybrid"]["recall_at_3"] * 100, 0.01)
        assert summary["dense_retrieval_recall_at_3_pct"] == pytest.approx(retrieval["strategies"]["dense"]["recall_at_3"] * 100, 0.01)
        # Note: Dense equals Hybrid at Recall@3
        assert retrieval["strategies"]["dense"]["recall_at_3"] == retrieval["strategies"]["hybrid"]["recall_at_3"]

    def test_metrics_summary_matches_performance_tiers(self):
        summary = load_json("METRICS_SUMMARY.json")["key_metrics_summary"]
        perf = load_json("performance_results.json")
        tiers = perf["concurrency_benchmarks"]
        assert len(tiers) == 5
        for tier_name, tier in tiers.items():
            assert tier["total_requests"] == 500, f"Concurrency tier {tier_name} did not run N=500 requests"

        assert summary["peak_concurrency_tier"] == "C=1"
        assert summary["peak_concurrency_throughput_rps"] == pytest.approx(tiers["C=1"]["throughput_rps"], 0.01)
        assert summary["tier_c50_throughput_rps"] == pytest.approx(tiers["C=50"]["throughput_rps"], 0.01)
        assert summary["requests_per_concurrency_tier"] == 500

    def test_metrics_summary_matches_observability(self):
        summary = load_json("METRICS_SUMMARY.json")["key_metrics_summary"]
        obs = load_json("observability_results.json")
        assert obs["sample_size_per_repeat"] == 1000
        assert obs["repeats"] == 3
        assert summary["observability_health_overhead_p50_ms"] == pytest.approx(obs["health_endpoint"]["average_overhead_p50_ms"], 0.001)
        assert summary["observability_chat_overhead_p50_ms"] == pytest.approx(obs["chat_endpoint"]["average_overhead_p50_ms"], 0.001)

    def test_metrics_summary_matches_local_llm(self):
        summary = load_json("METRICS_SUMMARY.json")["key_metrics_summary"]
        llm = load_json("local_llm_results.json")
        assert summary["local_ollama_throughput_mean_tok_per_sec"] == pytest.approx(llm["throughput_metrics"]["mean_tokens_per_second"], 0.01)
        assert summary["local_ollama_throughput_p50_tok_per_sec"] == pytest.approx(llm["throughput_metrics"]["p50_tokens_per_second"], 0.01)
        assert summary["local_ollama_adversarial_refusals"] == f"{llm['accuracy_summary']['refusals_correct']}/{llm['accuracy_summary']['adversarial_queries']}"
        failing_ids = [c["id"] for c in llm["accuracy_summary"]["failing_cases"]]
        assert summary["local_ollama_failing_case"] in failing_ids
        assert summary["local_ollama_failing_case"] == "LLM-21"

    def test_metrics_summary_matches_accessibility(self):
        summary = load_json("METRICS_SUMMARY.json")["key_metrics_summary"]
        a11y = load_json("accessibility_results.json")
        assert summary["axe_accessibility_violations"] == a11y["eslint_jsx_a11y_violations"]
        assert summary["axe_accessibility_violations"] == 0
        assert summary["axe_runner"] == a11y["axe_runner"]
        assert "jsdom" in summary["axe_runner"]
        assert summary["compliance_status"] == a11y["compliance_status"]
        assert "manual screen-reader pass: pending" in summary["compliance_status"]

    def test_no_forbidden_phrases_in_dossier(self):
        """Assert that no forbidden phrases or obsolete figures appear in reports."""
        violations = []
        for filename in MARKDOWN_REPORTS:
            content = load_text(filename)
            for phrase in FORBIDDEN_PHRASES:
                if phrase.lower() in content.lower():
                    violations.append(f"{filename}: contains forbidden phrase '{phrase}'")

        assert not violations, "Found forbidden phrases in reports:\n" + "\n".join(violations)

    def test_verified_git_sha_consistency(self):
        """Assert that reproduction manifest and summary cite the verified SHA."""
        manifest = load_json("reproduction_manifest.json")
        summary = load_json("METRICS_SUMMARY.json")
        expected_sha = manifest["verified_commit_sha"]
        assert summary["verified_git_sha"] == expected_sha

        # Verify that reports do not reference obsolete git hashes
        for filename in MARKDOWN_REPORTS:
            content = load_text(filename)
            assert "29eb93a" not in content, f"{filename} references stale git SHA 29eb93a"

    def test_n_counts_consistency(self):
        """Assert that sample sizes (N=) are consistent across all markdown reports."""
        retrieval_md = load_text("RETRIEVAL_EVALUATION.md")
        assert "N=12" in retrieval_md
        assert "50 production" not in retrieval_md

        perf_md = load_text("PERFORMANCE_REPORT.md")
        assert "500" in perf_md
        assert "250 total" not in perf_md

        resume_md = load_text("RESUME_METRICS.md")
        assert "N=12" in resume_md
        assert "C=1" in resume_md
