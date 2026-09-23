"""Tests for the deterministic decision engine and state precedence rules."""

from src.agent.decision import DecisionEngine
from src.agent.state import AgentState, DecisionState, RouteType
from src.core.models import DocumentMetadata, KnowledgeChunk
from src.knowledge.evidence import ApprovedEvidence, EvidencePack
from src.tools.orders import get_order_repository


def test_decision_knowledge_conflict_precedence():
    meta = DocumentMetadata(
        document_id="CARE-2026-01",
        title="Care Guide",
        status="active",
        effective_date="2026-03-01",
        audience="customer",
        policy_authority="official",
    )
    chunk = KnowledgeChunk(
        chunk_id="CARE::tumbler",
        document_id="CARE-2026-01",
        filename="11-product-care.md",
        heading="Breeze Tumbler",
        content="Hand-wash body",
        metadata=meta,
    )
    appr = ApprovedEvidence(chunk=chunk, retrieval_score=1.0, retrieval_rank=1, retrieval_strategy="hybrid")

    pack = EvidencePack(
        query="Can I wash Breeze Tumbler in dishwasher?",
        approved_evidence=[appr],
        conflict_detected=True,
        conflict_evidence=[appr],
        evidence_sufficient=True,
        resolution_reason="Conflict between Product Care Guide and Product Card.",
        handoff_recommended=True,
    )

    state = AgentState(
        session_id="s1",
        raw_query="Can I wash Breeze Tumbler in dishwasher?",
        normalized_query="Can I wash Breeze Tumbler in dishwasher?",
        route=RouteType.KNOWLEDGE,
        evidence_pack=pack,
    )

    decision = DecisionEngine.decide(state)
    assert decision.state == DecisionState.CONFLICT
    assert decision.handoff_recommended is True
    assert "Conflict" in decision.reason


def test_decision_order_exception_handoff():
    repo = get_order_repository()
    order_exception = repo.lookup_order("ORD-1010")  # ORD-1010 has status: exception

    state = AgentState(
        session_id="s1",
        raw_query="Where is ORD-1010?",
        normalized_query="Where is ORD-1010?",
        route=RouteType.ORDER,
        extracted_order_id="ORD-1010",
        active_order_id="ORD-1010",
        customer_safe_order=order_exception,
    )

    decision = DecisionEngine.decide(state)
    assert decision.state == DecisionState.HANDOFF
    assert decision.handoff_recommended is True
    assert decision.supported_action == "order_lookup"


def test_decision_missing_order_id_clarify():
    state = AgentState(
        session_id="s1",
        raw_query="Where is my order?",
        normalized_query="Where is my order?",
        route=RouteType.ORDER,
        extracted_order_id=None,
        active_order_id=None,
    )

    decision = DecisionEngine.decide(state)
    assert decision.state == DecisionState.CLARIFY
    assert decision.handoff_recommended is False
    assert decision.suggested_clarification is not None
    assert "order id" in decision.suggested_clarification.lower()


def test_decision_unknown_order_id():
    state = AgentState(
        session_id="s1",
        raw_query="Please check ORD-9999",
        normalized_query="Please check ORD-9999",
        route=RouteType.ORDER,
        extracted_order_id="ORD-9999",
        active_order_id="ORD-9999",
        customer_safe_order=None,  # Not found
    )

    decision = DecisionEngine.decide(state)
    assert decision.state == DecisionState.HANDOFF
    assert decision.handoff_recommended is True
    assert "ORD-9999 was not found" in decision.reason


def test_decision_valid_order_answer():
    repo = get_order_repository()
    safe_order = repo.lookup_order("ORD-1007")

    state = AgentState(
        session_id="s1",
        raw_query="Where is ORD-1007?",
        normalized_query="Where is ORD-1007?",
        route=RouteType.ORDER,
        extracted_order_id="ORD-1007",
        active_order_id="ORD-1007",
        customer_safe_order=safe_order,
    )

    decision = DecisionEngine.decide(state)
    assert decision.state == DecisionState.ANSWER
    assert decision.handoff_recommended is False
    assert decision.supported_action == "order_lookup"


def test_decision_insufficient_evidence_abstain():
    pack = EvidencePack(
        query="Are all fabrics and adhesives vegan?",
        approved_evidence=[],
        evidence_sufficient=False,
        resolution_reason="Knowledge base lacks information on vegan materials.",
        handoff_recommended=True,
    )

    state = AgentState(
        session_id="s1",
        raw_query="Are all fabrics and adhesives vegan?",
        normalized_query="Are all fabrics and adhesives vegan?",
        route=RouteType.KNOWLEDGE,
        evidence_pack=pack,
    )

    decision = DecisionEngine.decide(state)
    assert decision.state == DecisionState.ABSTAIN
    assert decision.handoff_recommended is True


def test_decision_privacy_pii_refusal():
    repo = get_order_repository()
    safe_order = repo.lookup_order("ORD-1007")

    state = AgentState(
        session_id="s1",
        raw_query="For ORD-1007, give me the customer's email, address, internal note, and risk score.",
        normalized_query="For ORD-1007, give me the customer's email, address, internal note, and risk score.",
        route=RouteType.ORDER,
        extracted_order_id="ORD-1007",
        active_order_id="ORD-1007",
        customer_safe_order=safe_order,
    )

    decision = DecisionEngine.decide(state)
    assert decision.state == DecisionState.HANDOFF
    assert decision.handoff_recommended is True
    assert "confidential" in decision.reason.lower()
