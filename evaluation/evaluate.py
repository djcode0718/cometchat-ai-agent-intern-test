"""CLI entrypoint for running Aster & Row AI agent evaluation suites."""

import argparse
import json
import sys
from pathlib import Path
from typing import List

from evaluation.harness import EvaluationHarness
from evaluation.models import SuiteResult


def print_suite_report(suite: SuiteResult) -> None:
    """Format and print an evaluation suite report to stdout."""
    print("\n" + "=" * 60)
    print("PHASE 4A BASELINE")
    print("=" * 60)

    print(f"\nVisible cases:\n  {suite.total_cases}")
    print(f"\nPassed:\n  {suite.passed_cases}")
    print(f"\nFailed:\n  {suite.failed_cases}")
    print(f"\nPass rate:\n  {suite.passed_cases}/{suite.total_cases} ({suite.pass_rate}%)")

    print("\n" + "-" * 60)
    print(f"{'CASE-ID':<35} {'STATUS':<10} {'DECISION':<10} {'HANDOFF'}")
    print("-" * 60)
    for res in suite.results:
        status_str = "PASS" if res.passed else "FAIL"
        handoff_str = "True" if res.handoff_recommended else "False"
        print(f"{res.case_id:<35} {status_str:<10} {res.decision_state:<10} {handoff_str}")

    print("\nCategory Breakdown:")
    print(f"  {'Category':<25} {'Passed':<10} {'Total':<10} {'Rate':<10}")
    print(f"  {'-'*23} {'-'*8} {'-'*8} {'-'*8}")
    for cat, stats in suite.category_breakdown.items():
        rate = round((stats["passed"] / stats["total"]) * 100, 1) if stats["total"] else 0.0
        print(f"  {cat:<25} {stats['passed']:<10} {stats['total']:<10} {rate}%")

    if suite.failed_cases > 0:
        print("\nFailures:")
        print("-" * 60)
        for res in suite.results:
            if not res.passed:
                print(f"\n[FAIL] Case ID: {res.case_id} (Category: {res.category})")
                print(f"       Decision State:   {res.decision_state}")
                print(f"       Handoff:          {res.handoff_recommended}")
                print(f"       Citations:        {res.citations}")
                print(f"       Failure Category: {res.failure_category}")
                for fail in res.failures:
                    print(f"       - Assertion: {fail.assertion_type}")
                    print(f"         Expected:  {fail.expected}")
                    print(f"         Actual:    {fail.actual}")
                    print(f"         Message:   {fail.message}")
    else:
        print("\nAll cases passed successfully!")
    print("=" * 60 + "\n")


def main() -> int:
    """CLI runner entry point."""
    parser = argparse.ArgumentParser(description="Evaluate Aster & Row AI Agent Baseline")
    parser.add_argument(
        "--suite",
        type=str,
        default="evaluation/visible_cases.json",
        help="Path to evaluation cases JSON file",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="evaluation/results/baseline.json",
        help="Path to save evaluation results JSON",
    )

    args = parser.parse_args()
    suite_path = Path(args.suite)
    if not suite_path.exists():
        fallback_path = Path("evaluation/visible-cases.json")
        if fallback_path.exists():
            suite_path = fallback_path
        else:
            print(f"Error: evaluation suite file not found at {suite_path}", file=sys.stderr)
            return 1

    harness = EvaluationHarness()
    cases = harness.load_cases(suite_path)
    suite_res = harness.run_suite("Visible Cases", cases)
    print_suite_report(suite_res)

    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(suite_res.model_dump(), f, indent=2)
        print(f"Baseline results saved to {args.output}")

    return 0 if suite_res.failed_cases == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
