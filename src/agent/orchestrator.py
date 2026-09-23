"""Agent orchestrator connecting session management, routing, tool execution, decision making, and grounded LLM generation."""

from typing import Any, Dict, Optional

from src.agent.decision import DecisionEngine
from src.agent.router import Router
from src.agent.state import AgentDecision, AgentState, RouteType
from src.core.session import SessionManager
from src.knowledge.evidence import EvidencePack
from src.knowledge.resolver import KnowledgeResolver
from src.knowledge.service import ingest_knowledge_base
from src.llm.base import BaseLLMProvider
from src.llm.models import GeneratedResponse, GroundedGenerationRequest
from src.llm.provider import FlexibleLLMProvider
from src.retrieval.base import BaseRetriever
from src.retrieval.bm25 import BM25Retriever
from src.retrieval.dense import DenseRetriever
from src.retrieval.embeddings import LocalEmbeddingService
from src.retrieval.hybrid import HybridRetriever
from src.tools.order_models import CustomerSafeOrder
from src.tools.orders import OrderRepository, get_order_repository


class AgentOrchestrator:
    """Coordinates deterministic routing, knowledge/order retrieval, decision generation, and grounded LLM response."""

    def __init__(
        self,
        session_manager: Optional[SessionManager] = None,
        router: Optional[Router] = None,
        retriever: Optional[BaseRetriever] = None,
        knowledge_resolver: Optional[KnowledgeResolver] = None,
        order_repository: Optional[OrderRepository] = None,
        decision_engine: Optional[DecisionEngine] = None,
        llm_provider: Optional[BaseLLMProvider] = None,
    ) -> None:
        self.session_manager = session_manager or SessionManager()
        self.router = router or Router()
        self.knowledge_resolver = knowledge_resolver or KnowledgeResolver()
        self.order_repository = order_repository or get_order_repository()
        self.decision_engine = decision_engine or DecisionEngine()
        self.llm_provider = llm_provider or FlexibleLLMProvider()

        # Initialize default hybrid retriever if not injected
        if retriever is not None:
            self.retriever = retriever
        else:
            chunks = ingest_knowledge_base().chunks
            emb = LocalEmbeddingService()
            bm25 = BM25Retriever(chunks=chunks)
            dense = DenseRetriever(chunks=chunks, embedding_service=emb)
            self.retriever = HybridRetriever(
                chunks=chunks, bm25_retriever=bm25, dense_retriever=dense
            )

    def process_turn(self, session_id: str, query: str) -> AgentState:
        """Process a single conversation turn and produce an authoritative, validated AgentState."""
        session = self.session_manager.get_or_create_session(session_id)
        clean_query = query.strip()
        turn_id = len(session.messages) + 1

        # 1. Routing & Entity Resolution
        route, order_intent, extracted_id, active_id = self.router.route(
            clean_query, session=session
        )

        safe_order: Optional[CustomerSafeOrder] = None
        evidence_pack: Optional[EvidencePack] = None

        # 2. Tool / Evidence Execution
        if route == RouteType.ORDER:
            if active_id:
                safe_order = self.order_repository.lookup_order(active_id)
                if safe_order:
                    # Persist active order ID to session
                    session.active_order_id = active_id
            else:
                safe_order = None

        elif route == RouteType.KNOWLEDGE:
            raw_candidates = self.retriever.retrieve(clean_query, top_k=5)
            evidence_pack = self.knowledge_resolver.resolve(clean_query, raw_candidates)

        # 3. Construct Initial Agent State
        state = AgentState(
            session_id=session_id,
            turn_id=turn_id,
            raw_query=query,
            normalized_query=clean_query,
            route=route,
            order_intent=order_intent,
            extracted_order_id=extracted_id,
            active_order_id=active_id,
            evidence_pack=evidence_pack,
            customer_safe_order=safe_order,
        )

        # 4. Generate Deterministic Decision
        decision: AgentDecision = self.decision_engine.decide(state)
        state.decision = decision
        state.handoff_recommended = decision.handoff_recommended
        state.handoff_reason = decision.handoff_reason

        # 5. Build Grounded Generation Request
        gen_request = GroundedGenerationRequest(
            user_query=clean_query,
            decision_state=decision.state,
            decision_reason=decision.reason,
            approved_evidence=evidence_pack.approved_evidence if evidence_pack else [],
            conflict_evidence=evidence_pack.conflict_evidence if evidence_pack else [],
            customer_safe_order=safe_order,
            suggested_clarification=decision.suggested_clarification,
            handoff_recommended=decision.handoff_recommended,
            handoff_reason=decision.handoff_reason,
            supported_action=decision.supported_action,
            citations=evidence_pack.citations if evidence_pack else [],
        )

        # 6. Execute Grounded Generation and Output Validation
        response: GeneratedResponse = self.llm_provider.generate(gen_request)
        state.response = response

        # 7. Build Observability Trace
        state.trace = {
            "session_id": session_id,
            "turn_id": turn_id,
            "route": route.value,
            "order_intent": order_intent.value if order_intent else None,
            "extracted_order_id": extracted_id,
            "active_order_id": active_id,
            "decision_state": decision.state.value,
            "decision_reason": decision.reason,
            "handoff_recommended": response.handoff_recommended,
            "handoff_reason": decision.handoff_reason,
            "supported_action": response.supported_action,
            "provider": self.llm_provider.provider_name,
            "is_fallback": response.is_fallback,
            "fallback_reason": response.fallback_reason,
            "citations": response.citation_strings,
            "final_message": response.message,
            "order_status": safe_order.status if safe_order else None,
        }

        # 8. Record user and assistant messages in session history
        session.add_message(role="user", content=clean_query)
        session.add_message(role="assistant", content=response.message)

        return state
