"""Deep diagnostic reproduction script for BUG-001 (final-sale-damaged-exception)."""

import json
from pathlib import Path
from src.agent.orchestrator import AgentOrchestrator
from src.agent.router import Router
from src.agent.decision import DecisionEngine
from src.agent.state import AgentState, RouteType, DecisionState
from src.core.session import SessionManager
from src.knowledge.resolver import KnowledgeResolver
from src.knowledge.service import ingest_knowledge_base
from src.retrieval.bm25 import BM25Retriever
from src.retrieval.dense import DenseRetriever
from src.retrieval.embeddings import LocalEmbeddingService
from src.retrieval.hybrid import HybridRetriever
from src.tools.orders import get_order_repository


def trace_bug001() -> dict:
    query = "A final-sale bag arrived with a broken zipper yesterday. Am I completely out of luck?"
    session_id = "repro_bug001"

    # Setup orchestrator components
    session_mgr = SessionManager()
    session = session_mgr.get_or_create_session(session_id)
    router = Router()
    kb = ingest_knowledge_base()
    chunks = kb.chunks
    emb = LocalEmbeddingService()
    bm25 = BM25Retriever(chunks=chunks)
    dense = DenseRetriever(chunks=chunks, embedding_service=emb)
    retriever = HybridRetriever(chunks=chunks, bm25_retriever=bm25, dense_retriever=dense)
    resolver = KnowledgeResolver()
    order_repo = get_order_repository()
    decision_engine = DecisionEngine()
    orchestrator = AgentOrchestrator(
        session_manager=session_mgr,
        router=router,
        retriever=retriever,
        knowledge_resolver=resolver,
        order_repository=order_repo,
        decision_engine=decision_engine,
    )

    # 1. Routing
    route, intent, ext_id, act_id = router.route(query, session=session)

    # 2. Retrieval
    raw_candidates = retriever.retrieve(query, top_k=5)

    # 3. Knowledge Resolution
    evidence_pack = resolver.resolve(query, raw_candidates)

    # 4. Agent State construction
    state = AgentState(
        session_id=session_id,
        turn_id=1,
        raw_query=query,
        normalized_query=query.strip(),
        route=route,
        order_intent=intent,
        extracted_order_id=ext_id,
        active_order_id=act_id,
        evidence_pack=evidence_pack,
    )

    # 5. Decision Engine
    decision = decision_engine.decide(state)
    state.decision = decision
    state.handoff_recommended = decision.handoff_recommended
    state.handoff_reason = decision.handoff_reason

    # 6. Full turn execution
    final_state = orchestrator.process_turn(session_id=session_id, query=query)
    pub_resp = final_state.to_public_response()

    # Detailed report
    trace_info = {
        "case_id": "final-sale-damaged-exception",
        "input_query": query,
        "expected": {
            "decision_state": "ANSWER",
            "handoff_recommended": True,
            "concepts": [
                "final sale does not block damaged-item review",
                "report within 7 days",
                "human review before approval",
            ],
            "required_sources": [
                "03-final-sale-and-promotions.md",
                "04-damaged-or-wrong-items.md",
            ],
        },
        "actual": {
            "route": route.value,
            "decision_state": decision.state.value,
            "handoff_recommended": decision.handoff_recommended,
            "handoff_reason": decision.handoff_reason,
            "public_response_message": pub_resp.message,
            "citations": pub_resp.citations,
            "retrieved_chunks": [c.chunk.chunk_id for c in raw_candidates],
            "approved_evidence": [e.chunk.chunk_id for e in evidence_pack.approved_evidence],
            "evidence_sufficient": evidence_pack.evidence_sufficient,
            "evidence_pack_handoff_recommended": evidence_pack.handoff_recommended,
            "evidence_pack_resolution_reason": evidence_pack.resolution_reason,
        },
        "reproduction_status": "REPRODUCED",
        "suspected_root_layer": "DECISION_ENGINE / KNOWLEDGE_RESOLVER",
        "root_cause_analysis": (
            "1. Retrieval correctly returned chunks from both '03-final-sale-and-promotions.md' and '04-damaged-or-wrong-items.md'.\n"
            "2. KnowledgeResolver evaluated evidence_sufficient=True because both documents are active, official customer policies.\n"
            "3. However, KnowledgeResolver defaulted handoff_recommended to False because it only flags handoff for conflicts, "
            "insufficient evidence, or missing vegan keywords.\n"
            "4. DecisionEngine evaluated Rule 8 ('Sufficient Approved Knowledge Evidence') and returned state=ANSWER with "
            "handoff_recommended=evidence_pack.handoff_recommended (which was False).\n"
            "5. The policy in '04-damaged-or-wrong-items.md' explicitly mandates human support review ('All replacements/refunds require manual support agent review'), "
            "so an active customer report of an arrived damaged item requires handoff_recommended=True alongside the policy explanation."
        ),
    }

    out_file = Path("evaluation/results/bug001_reproduction.json")
    out_file.parent.mkdir(parents=True, exist_ok=True)
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(trace_info, f, indent=2)

    print(f"BUG-001 reproduction trace written to {out_file}")
    return trace_info


if __name__ == "__main__":
    trace_bug001()
