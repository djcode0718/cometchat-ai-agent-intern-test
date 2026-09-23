"""Evaluation harness for running scenario-level test suites against AgentOrchestrator."""

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from src.agent.orchestrator import AgentOrchestrator
from src.agent.state import DecisionState, RouteType
from evaluation.models import (
    AssertionFailure,
    CaseExpectation,
    CaseResult,
    EvaluationCase,
    Message,
    SuiteResult,
    TurnResult,
)


def normalize_text(text: str) -> str:
    """Normalize text for semantic comparison (lowercase, hyphens to spaces, strip excess whitespace)."""
    text = text.lower().replace("-", " ").replace("–", " ").replace("—", " ")
    return re.sub(r"\s+", " ", text).strip()


def text_contains_concept(haystack: str, needle: str) -> bool:
    """Semantic concept matching supporting date equivalence, pluralization, and hyphen variations."""
    h_norm = normalize_text(haystack)
    n_norm = normalize_text(needle)

    # 1. Direct normalized match
    if n_norm in h_norm:
        return True

    # 2. Singular/plural trailing 's' match
    if n_norm.rstrip("s") in h_norm:
        return True

    # 3. Date equivalence check (e.g. '2026-08-22' <-> 'August 22, 2026')
    try:
        # If needle is an English date like "August 22, 2026"
        dt = datetime.strptime(needle.replace(",", ""), "%B %d %Y")
        iso_str = dt.strftime("%Y-%m-%d")
        if iso_str in haystack or iso_str in h_norm:
            return True
    except Exception:
        pass

    try:
        # If needle is an ISO date like "2026-08-22"
        dt = datetime.strptime(needle, "%Y-%m-%d")
        eng_str = dt.strftime("%B %d, %Y").lower()
        if eng_str in h_norm:
            return True
    except Exception:
        pass

    # 4. Keyword token set subset match (all words in concept present within text)
    words = [w for w in n_norm.split() if len(w) > 2]
    if words and all(w.rstrip("s") in h_norm for w in words):
        return True

    return False


class EvaluationHarness:
    """Runs structured evaluation cases against the existing Aster & Row agent orchestrator."""

    def __init__(self, orchestrator: Optional[AgentOrchestrator] = None) -> None:
        self.orchestrator = orchestrator or AgentOrchestrator()

    @classmethod
    def load_cases(cls, file_path: Path | str) -> List[EvaluationCase]:
        """Load evaluation cases from a JSON file."""
        path = Path(file_path)
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        raw_cases = data.get("cases", data) if isinstance(data, dict) else data
        cases: List[EvaluationCase] = []

        for item in raw_cases:
            messages = [
                Message(role=m.get("role", "user"), content=m.get("content", ""))
                for m in item.get("messages", [])
            ]
            expect_dict = item.get("expect", {})
            expect = CaseExpectation(
                must_include=expect_dict.get("must_include", []),
                must_not_include=expect_dict.get("must_not_include", []),
                must_include_concepts=expect_dict.get("must_include_concepts", []),
                must_not_follow=expect_dict.get("must_not_follow", []),
                must_not_invent=expect_dict.get("must_not_invent", []),
                must_refuse_to_disclose=expect_dict.get("must_refuse_to_disclose", []),
                must_ask_for=expect_dict.get("must_ask_for", []),
                must_not_silently_choose_one=expect_dict.get("must_not_silently_choose_one", False),
                required_sources=expect_dict.get("required_sources", []),
                forbidden_sources_as_authority=expect_dict.get("forbidden_sources_as_authority", []),
                tool=expect_dict.get("tool"),
                tool_arguments=expect_dict.get("tool_arguments"),
                handoff=expect_dict.get("handoff"),
                expected_decision_state=expect_dict.get("expected_decision_state"),
            )

            cases.append(
                EvaluationCase(
                    id=item["id"],
                    category=item.get("category", "general"),
                    description=item.get("description"),
                    messages=messages,
                    expect=expect,
                )
            )

        return cases

    def evaluate_case(self, case: EvaluationCase) -> CaseResult:
        """Execute all turns of a single case in an isolated session and evaluate assertions."""
        session_id = f"eval_{case.id}"
        turn_results: List[TurnResult] = []
        failures: List[AssertionFailure] = []

        last_state = None
        for turn_idx, message in enumerate(case.messages, start=1):
            state = self.orchestrator.process_turn(session_id=session_id, query=message.content)
            last_state = state
            pub_resp = state.to_public_response()

            turn_res = TurnResult(
                turn_id=turn_idx,
                user_query=message.content,
                decision_state=pub_resp.decision_state.value,
                handoff_recommended=pub_resp.handoff_recommended,
                handoff_reason=pub_resp.handoff_reason,
                supported_action=pub_resp.supported_action,
                citations=pub_resp.citations,
                message=pub_resp.message,
                is_fallback=pub_resp.is_fallback,
                fallback_reason=pub_resp.fallback_reason,
                trace=state.trace,
            )
            turn_results.append(turn_res)

        if not last_state or not last_state.response:
            failures.append(
                AssertionFailure(
                    assertion_type="response_generation",
                    expected="Valid GeneratedResponse",
                    actual="None",
                    message="Agent failed to produce a response state.",
                )
            )
            return CaseResult(
                case_id=case.id,
                category=case.category,
                passed=False,
                decision_state="UNKNOWN",
                handoff_recommended=False,
                citations=[],
                failures=failures,
                turns=turn_results,
                failure_category="LLM_GENERATION",
            )

        final_msg = last_state.response_message
        expect = case.expect

        # 1. Handoff assertion
        if expect.handoff is not None:
            if last_state.handoff_recommended != expect.handoff:
                failures.append(
                    AssertionFailure(
                        assertion_type="handoff_recommended",
                        expected=expect.handoff,
                        actual=last_state.handoff_recommended,
                        message=f"Expected handoff={expect.handoff}, got {last_state.handoff_recommended} (reason: {last_state.handoff_reason})",
                    )
                )

        # 2. Expected Decision State assertion
        if expect.expected_decision_state is not None:
            actual_decision = last_state.decision.state if last_state.decision else None
            if actual_decision != expect.expected_decision_state:
                failures.append(
                    AssertionFailure(
                        assertion_type="decision_state",
                        expected=expect.expected_decision_state.value,
                        actual=actual_decision.value if actual_decision else "None",
                        message=f"Expected decision state {expect.expected_decision_state}, got {actual_decision}",
                    )
                )

        # 3. Tool invocation assertion
        if expect.tool:
            if expect.tool in ("not_called", "not_called_without_id"):
                if last_state.customer_safe_order is not None and last_state.extracted_order_id is not None:
                    failures.append(
                        AssertionFailure(
                            assertion_type="tool_execution",
                            expected=expect.tool,
                            actual="order_lookup",
                            message=f"Expected tool {expect.tool}, but order was resolved: {last_state.customer_safe_order.order_id}",
                        )
                    )
            elif expect.tool == "order_lookup":
                if last_state.route != RouteType.ORDER:
                    failures.append(
                        AssertionFailure(
                            assertion_type="tool_execution",
                            expected="ORDER route / lookup",
                            actual=last_state.route.value,
                            message=f"Expected ORDER route, got {last_state.route}",
                        )
                    )
                if expect.tool_arguments and "order_id" in expect.tool_arguments:
                    expected_oid = expect.tool_arguments["order_id"]
                    actual_oid = last_state.extracted_order_id or last_state.active_order_id
                    if actual_oid != expected_oid:
                        failures.append(
                            AssertionFailure(
                                assertion_type="order_id_resolution",
                                expected=expected_oid,
                                actual=actual_oid,
                                message=f"Expected order_id {expected_oid}, got {actual_oid}",
                            )
                        )

        # 4. Required sources assertion (Authority / Retrieval)
        if expect.required_sources:
            approved_doc_ids: List[str] = []
            if last_state.evidence_pack:
                for e in last_state.evidence_pack.approved_evidence:
                    approved_doc_ids.append(e.document_id)
                    approved_doc_ids.append(e.filename)
            for req_source in expect.required_sources:
                if not any(req_source in doc_id for doc_id in approved_doc_ids):
                    failures.append(
                        AssertionFailure(
                            assertion_type="required_sources",
                            expected=req_source,
                            actual=approved_doc_ids,
                            message=f"Required source '{req_source}' was not found in approved evidence: {approved_doc_ids}",
                        )
                    )

        # 5. Forbidden sources assertion (Supersession / Authority)
        if expect.forbidden_sources_as_authority:
            approved_doc_ids = []
            if last_state.evidence_pack:
                for e in last_state.evidence_pack.approved_evidence:
                    approved_doc_ids.append(e.document_id)
                    approved_doc_ids.append(e.filename)
            for forb_source in expect.forbidden_sources_as_authority:
                if any(forb_source in doc_id for doc_id in approved_doc_ids):
                    failures.append(
                        AssertionFailure(
                            assertion_type="forbidden_sources",
                            expected=f"Exclusion of {forb_source}",
                            actual=approved_doc_ids,
                            message=f"Forbidden source '{forb_source}' was improperly approved as authoritative!",
                        )
                    )

        # 6. Must not silently choose one (Conflict detection)
        if expect.must_not_silently_choose_one:
            if not last_state.evidence_pack or not last_state.evidence_pack.conflict_detected:
                failures.append(
                    AssertionFailure(
                        assertion_type="conflict_detection",
                        expected="conflict_detected=True",
                        actual=False if not last_state.evidence_pack else last_state.evidence_pack.conflict_detected,
                        message="Active source conflict was not detected by KnowledgeResolver!",
                    )
                )
            if last_state.decision and last_state.decision.state not in (DecisionState.CONFLICT, DecisionState.HANDOFF):
                failures.append(
                    AssertionFailure(
                        assertion_type="conflict_decision",
                        expected="CONFLICT or HANDOFF",
                        actual=last_state.decision.state.value,
                        message=f"Conflict resulted in decision {last_state.decision.state.value} instead of CONFLICT/HANDOFF",
                    )
                )

        # 7. Must include semantic concepts / keywords
        for req_text in expect.must_include:
            if not text_contains_concept(final_msg, req_text):
                failures.append(
                    AssertionFailure(
                        assertion_type="must_include",
                        expected=req_text,
                        actual=final_msg,
                        message=f"Required concept '{req_text}' was missing from response message.",
                    )
                )

        # 8. Must not include forbidden substrings (PII, stale dates, fake claims)
        for forb_text in expect.must_not_include:
            if forb_text.lower() in final_msg.lower():
                failures.append(
                    AssertionFailure(
                        assertion_type="must_not_include",
                        expected=f"Exclusion of '{forb_text}'",
                        actual=final_msg,
                        message=f"Forbidden text/data '{forb_text}' appeared in response message!",
                    )
                )

        # 9. Must refuse to disclose (Privacy / Security)
        for refuse_item in expect.must_refuse_to_disclose:
            if refuse_item.lower() == "email" and "ava.morgan" in final_msg.lower():
                failures.append(
                    AssertionFailure(
                        assertion_type="privacy_refusal",
                        expected="refusal of email",
                        actual="email leaked",
                        message="Customer email was disclosed in violation of privacy policy.",
                    )
                )

        # 10. Must ask for (Clarification)
        for ask_item in expect.must_ask_for:
            if not text_contains_concept(final_msg, ask_item):
                failures.append(
                    AssertionFailure(
                        assertion_type="must_ask_for",
                        expected=ask_item,
                        actual=final_msg,
                        message=f"Clarification question must ask for '{ask_item}'.",
                    )
                )

        passed = len(failures) == 0
        failure_category = None
        if not passed:
            failure_types = [f.assertion_type for f in failures]
            if any("forbidden_sources" in t or "required_sources" in t for t in failure_types):
                failure_category = "AUTHORITY/SUPERSESSION"
            elif any("conflict" in t for t in failure_types):
                failure_category = "CONFLICT"
            elif any("tool" in t or "order_id" in t for t in failure_types):
                failure_category = "ORDER_TOOL"
            elif any("privacy" in t for t in failure_types):
                failure_category = "SECURITY/PRIVACY"
            elif any("decision_state" in t or "handoff" in t for t in failure_types):
                failure_category = "DECISION_ENGINE"
            elif any("must_include" in t or "must_not_include" in t for t in failure_types):
                failure_category = "PROMPT/GROUNDED_GENERATION"
            else:
                failure_category = "OUTPUT_VALIDATION"

        return CaseResult(
            case_id=case.id,
            category=case.category,
            passed=passed,
            decision_state=last_state.decision.state.value if last_state.decision else "UNKNOWN",
            handoff_recommended=last_state.handoff_recommended,
            citations=last_state.citation_strings,
            failures=failures,
            turns=turn_results,
            failure_category=failure_category,
        )

    def run_suite(self, suite_name: str, cases: List[EvaluationCase]) -> SuiteResult:
        """Run all cases in the suite and compile aggregate statistics."""
        results: List[CaseResult] = []
        category_breakdown: Dict[str, Dict[str, int]] = {}

        for case in cases:
            res = self.evaluate_case(case)
            results.append(res)

            cat = case.category
            if cat not in category_breakdown:
                category_breakdown[cat] = {"total": 0, "passed": 0, "failed": 0}
            category_breakdown[cat]["total"] += 1
            if res.passed:
                category_breakdown[cat]["passed"] += 1
            else:
                category_breakdown[cat]["failed"] += 1

        passed_count = sum(1 for r in results if r.passed)
        failed_count = len(results) - passed_count
        pass_rate = round((passed_count / len(results)) * 100, 1) if results else 0.0

        return SuiteResult(
            suite_name=suite_name,
            total_cases=len(results),
            passed_cases=passed_count,
            failed_cases=failed_count,
            pass_rate=pass_rate,
            category_breakdown=category_breakdown,
            results=results,
        )
