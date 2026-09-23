"""Comprehensive integration and hardening tests for Phase 3C AgentOrchestrator."""

import pytest

from src.agent.orchestrator import AgentOrchestrator
from src.agent.state import DecisionState, PublicAgentResponse, RouteType
from src.core.session import SessionManager
from src.knowledge.service import ingest_knowledge_base
from src.llm.base import BaseLLMProvider, LLMGenerationError
from src.llm.mock import MockLLMProvider
from src.retrieval.base import BaseRetriever
from src.retrieval.bm25 import BM25Retriever
from src.retrieval.dense import DenseRetriever
from src.retrieval.embeddings import LocalEmbeddingService
from src.retrieval.hybrid import HybridRetriever
from src.retrieval.models import RetrievalResult
from src.tools.orders import get_order_repository


@pytest.fixture(scope="module")
def shared_orchestrator():
    """Create a shared orchestrator with real hybrid retriever and MockLLMProvider."""
    chunks = ingest_knowledge_base().chunks
    emb = LocalEmbeddingService()
    bm25 = BM25Retriever(chunks=chunks)
    dense = DenseRetriever(chunks=chunks, embedding_service=emb)
    retriever = HybridRetriever(chunks=chunks, bm25_retriever=bm25, dense_retriever=dense)

    session_mgr = SessionManager()
    order_repo = get_order_repository()
    llm = MockLLMProvider()

    return AgentOrchestrator(
        session_manager=session_mgr,
        retriever=retriever,
        order_repository=order_repo,
        llm_provider=llm,
    )


def test_public_agent_response_contract(shared_orchestrator):
    """Verify state.to_public_response() returns typed PublicAgentResponse without exposing raw internals."""
    state = shared_orchestrator.process_turn("s_pub_1", "What is the return window for standard items?")
    pub_resp = state.to_public_response()

    assert isinstance(pub_resp, PublicAgentResponse)
    assert pub_resp.session_id == "s_pub_1"
    assert pub_resp.turn_id == 1
    assert pub_resp.decision_state == DecisionState.ANSWER
    assert len(pub_resp.message) > 0
    assert len(pub_resp.citations) > 0
    assert pub_resp.handoff_recommended is False
    assert pub_resp.is_fallback is False


def test_observability_trace_fields_and_timing(shared_orchestrator):
    """Verify trace captures latency, provider, retrieval metadata, and zero PII."""
    state = shared_orchestrator.process_turn("s_trace_1", "Where is ORD-1007?")
    trace = state.trace

    assert trace["session_id"] == "s_trace_1"
    assert trace["turn_id"] == 1
    assert trace["route"] == "ORDER"
    assert trace["extracted_order_id"] == "ORD-1007"
    assert "generation_latency_ms" in trace
    assert isinstance(trace["generation_latency_ms"], float)
    assert trace["generation_failed"] is False
    assert "safe_order" in trace
    assert trace["safe_order"]["order_id"] == "ORD-1007"
    assert trace["safe_order"]["carrier"] == "UPS"

    # Strictly verify absence of PII and internal operational fields in trace
    trace_str = str(trace).lower()
    for forbidden in ["ava morgan", "ava.morgan@example.test", "220 king street", "risk_score", "fraud review", "warehouse_note"]:
        assert forbidden not in trace_str, f"Found forbidden internal term '{forbidden}' in trace"


def test_session_isolation(shared_orchestrator):
    """Verify two concurrent sessions maintain completely isolated order contexts and message histories."""
    # Session A inquires about ORD-1001
    state_a1 = shared_orchestrator.process_turn("session_A", "What is the status of ORD-1001?")
    assert state_a1.active_order_id == "ORD-1001"

    # Session B inquires about ORD-1003
    state_b1 = shared_orchestrator.process_turn("session_B", "Check order ORD-1003")
    assert state_b1.active_order_id == "ORD-1003"

    # Session A follow-up without order ID
    state_a2 = shared_orchestrator.process_turn("session_A", "When will it arrive?")
    assert state_a2.active_order_id == "ORD-1001"
    assert "ORD-1001" in state_a2.response.message

    # Session B follow-up without order ID
    state_b2 = shared_orchestrator.process_turn("session_B", "What carrier is it using?")
    assert state_b2.active_order_id == "ORD-1003"
    assert "Canada Post" in state_b2.response.message or "ORD-1003" in state_b2.response.message

    # Verify session histories are isolated
    session_a = shared_orchestrator.session_manager.get_session("session_A")
    session_b = shared_orchestrator.session_manager.get_session("session_B")
    assert len(session_a.messages) == 4
    assert len(session_b.messages) == 4
    assert all("ORD-1003" not in msg.content for msg in session_a.messages)
    assert all("ORD-1001" not in msg.content for msg in session_b.messages)


def test_retriever_failure_handled_gracefully():
    """Verify that an unexpected retriever exception does not crash orchestrator and routes safely to handoff."""
    class BrokenRetriever(BaseRetriever):
        @property
        def strategy_name(self):
            return "broken"

        def retrieve(self, query: str, top_k: int = 5):
            raise RuntimeError("Index corrupted / retrieval service unavailable")

    orchestrator = AgentOrchestrator(
        retriever=BrokenRetriever(),
        llm_provider=MockLLMProvider(),
    )

    state = orchestrator.process_turn("s_broken_ret", "What is your return policy?")
    assert state.decision.state in (DecisionState.ABSTAIN, DecisionState.HANDOFF)
    assert state.response.handoff_recommended is True
    assert len(state.response.message) > 0


def test_order_repository_missing_or_anomalous_handled_gracefully(shared_orchestrator):
    """Verify non-existent order ID gracefully routes to HANDOFF with polite support message."""
    state = shared_orchestrator.process_turn("s_unknown_ord", "Status of ORD-9999?")
    assert state.route == RouteType.ORDER
    assert state.customer_safe_order is None
    assert state.decision.state == DecisionState.HANDOFF
    assert state.response.handoff_recommended is True
    assert "support" in state.response.message.lower() or "not found" in state.response.message.lower()


def test_llm_provider_generation_failure_handled_gracefully():
    """Verify that provider exception triggers deterministic fallback and sets trace generation_failed=True."""
    class FailingProvider(BaseLLMProvider):
        @property
        def provider_name(self) -> str:
            return "failing-api-provider"

        def generate(self, request):
            raise LLMGenerationError("API connection reset")

    orchestrator = AgentOrchestrator(llm_provider=FailingProvider())
    state = orchestrator.process_turn("s_fail_llm", "What is the standard return window?")

    assert state.response.is_fallback is True
    assert state.trace["generation_failed"] is True
    assert state.trace["provider"] == "failing-api-provider"
    assert len(state.response.message.strip()) > 0
    assert "30" in state.response.message or "support" in state.response.message.lower()
