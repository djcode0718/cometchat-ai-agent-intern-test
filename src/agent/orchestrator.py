"""Agent orchestrator connecting session management, routing, tool execution, decision making, and grounded LLM generation."""

import time
from contextlib import contextmanager
from typing import Any, Dict, Generator, Optional

from src.agent.decision import DecisionEngine
from src.agent.router import OrderIntent, Router
from src.agent.state import AgentDecision, AgentState, DecisionState, RouteType
from src.core.config import get_settings
from src.core.session import SessionManager
from src.knowledge.evidence import EvidencePack
from src.knowledge.resolver import KnowledgeResolver
from src.knowledge.service import ingest_knowledge_base
from src.llm.base import BaseLLMProvider
from src.llm.factory import get_llm_provider
from src.llm.models import GeneratedResponse, GroundedGenerationRequest
from src.llm.validator import OutputValidator
from src.observability.logging import get_logger
from src.observability.metrics import (
    AGENT_STAGE_DURATION_SECONDS,
    AGENT_TURNS_TOTAL,
    LLM_CALLS_TOTAL,
    LLM_FALLBACK_TOTAL,
    SECURITY_INJECTIONS_BLOCKED_TOTAL,
)
from src.agent.security_guard import evaluate_input_guard, REFUSAL_MESSAGE
from src.retrieval.base import BaseRetriever
from src.retrieval.bm25 import BM25Retriever
from src.retrieval.dense import DenseRetriever
from src.retrieval.embeddings import LocalEmbeddingService
from src.retrieval.hybrid import HybridRetriever
from src.tools.order_models import CustomerSafeOrder
from src.tools.orders import OrderRepository, get_order_repository
from src.approvals.models import ActionType
from src.approvals import get_approval_service

logger = get_logger("orchestrator")


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
        self.llm_provider = llm_provider or get_llm_provider()

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

    @contextmanager
    def _time_stage(
        self, stage_name: str, stage_timings: Dict[str, float]
    ) -> Generator[None, None, None]:
        """Context manager to measure and record stage execution duration without changing logic."""
        t0 = time.perf_counter()
        try:
            yield
        finally:
            duration_s = time.perf_counter() - t0
            stage_timings[stage_name] = round(duration_s * 1000, 2)
            try:
                AGENT_STAGE_DURATION_SECONDS.labels(stage=stage_name).observe(duration_s)
            except Exception:
                pass

    def process_turn(self, session_id: str, query: str) -> AgentState:
        """Process a single conversation turn and produce an authoritative, validated AgentState."""
        session = self.session_manager.get_or_create_session(session_id)
        clean_query = query.strip()
        turn_id = len(session.messages) + 1
        stage_timings_ms: Dict[str, float] = {}

        # 0. Deterministic Pre-Retrieval Input Security Guard
        is_attack, guard_category = evaluate_input_guard(clean_query)
        if is_attack:
            logger.warning(
                "security_guard_triggered",
                guard_category=guard_category,
                query_length=len(clean_query),
            )
            try:
                SECURITY_INJECTIONS_BLOCKED_TOTAL.labels(category=guard_category).inc()
            except Exception:
                pass

            decision = AgentDecision(
                state=DecisionState.HANDOFF,
                reason="Adversarial input pattern neutralized by deterministic security guard.",
                handoff_recommended=True,
                handoff_reason="Security guard triggered: Adversarial instruction override or exfiltration attempt.",
            )
            resp = GeneratedResponse(
                message=REFUSAL_MESSAGE,
                decision_state=DecisionState.HANDOFF,
                citations=[],
                handoff_recommended=True,
                is_fallback=False,
            )
            state = AgentState(
                session_id=session_id,
                turn_id=turn_id,
                raw_query=query,
                normalized_query=clean_query,
                route=RouteType.UNSUPPORTED,
                decision=decision,
                response=resp,
                handoff_recommended=True,
                handoff_reason=decision.handoff_reason,
            )
            session.messages.append(state)
            return state

        # 1. Routing & Entity Resolution
        with self._time_stage("routing", stage_timings_ms):
            route, order_intent, extracted_id, active_id = self.router.route(
                clean_query, session=session
            )

        safe_order: Optional[CustomerSafeOrder] = None
        evidence_pack: Optional[EvidencePack] = None

        # 2. Tool / Evidence Execution with graceful error boundaries
        with self._time_stage("retrieval", stage_timings_ms):
            try:
                if route == RouteType.ORDER:
                    if active_id:
                        safe_order = self.order_repository.lookup_order(active_id)
                        if safe_order:
                            # Persist active order ID to session
                            session.active_order_id = active_id
                    else:
                        safe_order = None

                elif route == RouteType.KNOWLEDGE:
                    top_k = get_settings().retrieval_top_k
                    raw_candidates = self.retriever.retrieve(clean_query, top_k=top_k)
                    evidence_pack = self.knowledge_resolver.resolve(clean_query, raw_candidates)
            except Exception as e:
                # Fallback evidence pack on tool/retrieval error
                evidence_pack = EvidencePack(
                    query=clean_query,
                    approved_evidence=[],
                    evidence_sufficient=False,
                    resolution_reason=f"Tool/retrieval failure encountered: {type(e).__name__}",
                    handoff_recommended=True,
                )

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
        with self._time_stage("decision", stage_timings_ms):
            decision: AgentDecision = self.decision_engine.decide(state)
            state.decision = decision
            state.handoff_recommended = decision.handoff_recommended
            state.handoff_reason = decision.handoff_reason

        # 4b. HITL Proposal Hook: If cancellation or address change requested and order is cancellable
        proposal_info = None
        is_address_change_req = "address" in clean_query.lower() and ("change" in clean_query.lower() or "update" in clean_query.lower())
        if (
            safe_order is not None
            and safe_order.is_cancellable
            and (order_intent == OrderIntent.CANCELLATION or is_address_change_req)
        ):
            try:
                approval_service = get_approval_service()
                action_type = (
                    ActionType.CANCELLATION
                    if order_intent == OrderIntent.CANCELLATION
                    else ActionType.ADDRESS_CHANGE
                )
                safe_snapshot = {
                    "order_id": safe_order.order_id,
                    "status": safe_order.status,
                    "is_cancellable": safe_order.is_cancellable,
                    "membership_tier": safe_order.membership_tier,
                }
                proposal = approval_service.create_proposal(
                    order_id=safe_order.order_id,
                    session_id=session_id,
                    action_type=action_type,
                    evidence_snapshot=safe_snapshot,
                )
                proposal_info = {"id": proposal.id, "status": proposal.status.value}
                # Keep decision_state ANSWER and supported_action cancellation_request_submitted
                decision.supported_action = "cancellation_request_submitted"
            except Exception as prop_err:
                logger.warning("hitl_proposal_creation_error", error=str(prop_err))

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
            proposal_info=proposal_info,
            citations=evidence_pack.citations if evidence_pack else [],
        )

        # 6. Execute Grounded Generation and Output Validation with timing
        generation_failed = False
        raw_output: Any = None
        with self._time_stage("generation", stage_timings_ms):
            try:
                raw_output = self.llm_provider.generate(gen_request)
                # FAULT-PRV-06: Validate that provider returned a valid GeneratedResponse
                if not isinstance(raw_output, GeneratedResponse):
                    logger.warning(
                        "provider_schema_error",
                        error="Provider did not return a GeneratedResponse object",
                        received_type=type(raw_output).__name__,
                    )
                    generation_failed = True
                    response = OutputValidator.build_fallback(
                        gen_request, reason="Provider generation returned invalid schema."
                    )
                else:
                    response = raw_output
                    try:
                        LLM_CALLS_TOTAL.labels(
                            provider=self.llm_provider.provider_name,
                            model=getattr(self.llm_provider, "primary_model", "default"),
                            outcome="success",
                        ).inc()
                    except Exception:
                        pass
            except Exception as e:
                generation_failed = True
                logger.error(
                    "provider_generation_error",
                    error=str(e),
                    error_type=type(e).__name__,
                )
                response = OutputValidator.build_fallback(
                    gen_request, reason=f"Provider generation failed: {type(e).__name__}"
                )
                try:
                    LLM_CALLS_TOTAL.labels(
                        provider=self.llm_provider.provider_name,
                        model=getattr(self.llm_provider, "primary_model", "default"),
                        outcome="failure",
                    ).inc()
                except Exception:
                    pass

        # Validate / record output
        with self._time_stage("validation", stage_timings_ms):
            if response.is_fallback:
                try:
                    LLM_FALLBACK_TOTAL.labels(
                        reason=response.fallback_reason or "unknown"
                    ).inc()
                except Exception:
                    pass

        state.response = response

        # Record Agent Turn Metric
        try:
            AGENT_TURNS_TOTAL.labels(
                route=route.value,
                decision_state=decision.state.value,
            ).inc()
        except Exception:
            pass

        # 7. Build Comprehensive, PII-Free Observability Trace
        trace_data: Dict[str, Any] = {
            "session_id": session_id,
            "turn_id": turn_id,
            "query": clean_query,
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
            "generation_failed": generation_failed,
            "generation_latency_ms": stage_timings_ms.get("generation", 0.0),
            "stage_timings_ms": stage_timings_ms,
            "is_fallback": response.is_fallback,
            "fallback_reason": response.fallback_reason,
            "citations": response.citation_strings,
            "proposal": proposal_info,
            "final_message": response.message,
        }

        # Attach safe LLM fallback chain telemetry if available
        if hasattr(self.llm_provider, "last_telemetry") and self.llm_provider.last_telemetry:
            trace_data["llm_telemetry"] = dict(self.llm_provider.last_telemetry)

        # Attach safe knowledge retrieval metadata (No sensitive/internal fields)
        if evidence_pack:
            trace_data["retrieval"] = {
                "approved_chunks": [e.chunk_id for e in evidence_pack.approved_evidence],
                "approved_count": len(evidence_pack.approved_evidence),
                "excluded_count": len(evidence_pack.excluded_evidence),
                "excluded_reasons": [ex.reason.value for ex in evidence_pack.excluded_evidence],
                "conflict_detected": evidence_pack.conflict_detected,
                "evidence_sufficient": evidence_pack.evidence_sufficient,
            }

        # Attach sanitized order summary (Strictly no customer name, email, address, notes, risk score)
        if safe_order:
            trace_data["safe_order"] = {
                "order_id": safe_order.order_id,
                "status": safe_order.status,
                "carrier": safe_order.carrier,
                "tracking_number": safe_order.tracking_number,
                "estimated_delivery": safe_order.estimated_delivery,
                "is_cancellable": safe_order.is_cancellable,
            }

        state.trace = trace_data

        # 8. Record user and assistant messages in session history
        session.add_message(role="user", content=clean_query)
        session.add_message(role="assistant", content=response.message)

        return state
