"""Tests for LLM provider abstraction and MockLLMProvider."""

from src.agent.state import DecisionState
from src.core.models import CitationSource, DocumentMetadata, KnowledgeChunk
from src.knowledge.evidence import ApprovedEvidence
from src.llm.mock import MockLLMProvider
from src.llm.models import GroundedGenerationRequest
from src.tools.order_models import CustomerSafeOrder, CustomerSafeOrderItem


def make_sample_request(
    decision_state: DecisionState = DecisionState.ANSWER,
    query: str = "How long do I have to return an item?",
) -> GroundedGenerationRequest:
    meta = DocumentMetadata(
        document_id="RET-2026-01",
        title="Returns Policy",
        status="active",
        effective_date="2026-04-01",
        audience="customer",
        policy_authority="official",
    )
    chunk = KnowledgeChunk(
        chunk_id="RET-2026-01::window",
        document_id="RET-2026-01",
        filename="01-returns-policy-current.md",
        heading="Standard return window",
        content="Standard return window is 30 calendar days from delivery.",
        metadata=meta,
    )
    appr = ApprovedEvidence(chunk=chunk, retrieval_score=1.0, retrieval_rank=1, retrieval_strategy="hybrid")

    return GroundedGenerationRequest(
        user_query=query,
        decision_state=decision_state,
        decision_reason="Sufficient approved evidence found.",
        approved_evidence=[appr],
        citations=[CitationSource(filename="01-returns-policy-current.md", heading="Standard return window")],
    )


def test_mock_provider_answer_generation():
    provider = MockLLMProvider()
    req = make_sample_request(DecisionState.ANSWER)
    resp = provider.generate(req)

    assert resp.decision_state == DecisionState.ANSWER
    assert "30 calendar days" in resp.message
    assert len(resp.citations) == 1
    assert resp.citations[0].filename == "01-returns-policy-current.md"
    assert resp.is_fallback is False


def test_mock_provider_clarify_generation():
    provider = MockLLMProvider()
    req = GroundedGenerationRequest(
        user_query="Where is my order?",
        decision_state=DecisionState.CLARIFY,
        decision_reason="Order ID missing.",
        suggested_clarification="Please provide your order ID (e.g., ORD-XXXX).",
    )
    resp = provider.generate(req)

    assert resp.decision_state == DecisionState.CLARIFY
    assert "order id" in resp.message.lower()
    assert resp.handoff_recommended is False


def test_mock_provider_conflict_generation():
    provider = MockLLMProvider()
    req = GroundedGenerationRequest(
        user_query="Can I wash Breeze Tumbler in dishwasher?",
        decision_state=DecisionState.CONFLICT,
        decision_reason="Official sources conflict.",
        citations=[
            CitationSource(filename="11-product-care.md", heading="Breeze Tumbler"),
            CitationSource(filename="12-breeze-tumbler-product-card.md", heading="Cleaning"),
        ],
        handoff_recommended=True,
    )
    resp = provider.generate(req)

    assert resp.decision_state == DecisionState.CONFLICT
    assert resp.handoff_recommended is True
    assert "11-product-care.md" in resp.message
    assert "12-breeze-tumbler-product-card.md" in resp.message


def test_mock_provider_custom_response_injection():
    provider = MockLLMProvider(
        custom_responses={"Custom query": "This is an injected mock response [01-returns-policy-current.md > Standard return window]."}
    )
    req = make_sample_request(DecisionState.ANSWER, query="Custom query")
    resp = provider.generate(req)

    assert "injected mock response" in resp.message
