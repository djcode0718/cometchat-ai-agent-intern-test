"""FastAPI REST API layer for Aster & Row AI Support Agent."""

import os
import uuid
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from pydantic import BaseModel, Field, field_validator

load_dotenv()

from src.agent.orchestrator import AgentOrchestrator
from src.agent.state import DecisionState, PublicAgentResponse
from src.approvals import get_approval_service
from src.approvals.auth import authenticate_reviewer
from src.approvals.models import ActionType, ProposalStatus
from src.approvals.schemas import (
    ApproveProposalRequest,
    AuditEventResponse,
    ProposalResponse,
    RejectProposalRequest,
)
from src.approvals.service import ConcurrencyConflictError, ProposalNotFoundError
from src.approvals.state_machine import InvalidTransition
from src.core.config import get_settings
from src.observability.integrations import init_sentry
from src.observability.logging import configure_logging, get_logger
from src.observability.request_context import RequestContextMiddleware
from src.observability.trace_cache import BoundedTTLCache

# Initialize logging and Sentry early
settings = get_settings()
configure_logging(app_env=settings.app_env, log_level=settings.log_level)
init_sentry()
logger = get_logger("api")


# ---------------------------------------------------------------------------
# Pydantic Request & Response Schemas
# ---------------------------------------------------------------------------

class HealthResponse(BaseModel):
    """Health check response."""
    status: str = "ok"


class ReadyResponse(BaseModel):
    """Readiness probe response."""
    status: str
    reasons: List[str] = Field(default_factory=list)


class ChatRequest(BaseModel):
    """Incoming user chat request."""
    session_id: Optional[str] = Field(
        default=None,
        max_length=128,
        description="Optional conversation session ID. A fresh ID is generated if omitted.",
    )
    message: str = Field(
        ...,
        min_length=1,
        max_length=4000,
        description="User customer support query.",
    )

    @field_validator("message")
    @classmethod
    def validate_non_empty_message(cls, v: str) -> str:
        trimmed = v.strip()
        if not trimmed:
            raise ValueError("Message cannot be empty or whitespace only.")
        return trimmed


class ChatResponse(BaseModel):
    """Validated public response contract matching PublicAgentResponse with optional safe order details."""
    session_id: str = Field(..., description="Unique conversation session ID")
    turn_id: int = Field(..., description="1-indexed turn ID in session")
    message: str = Field(..., description="Customer response message")
    decision_state: str = Field(..., description="Deterministic decision state")
    citations: List[str] = Field(default_factory=list, description="Approved citation list")
    handoff_recommended: bool = Field(default=False, description="Whether human support is recommended")
    handoff_reason: Optional[str] = Field(default=None, description="Reason for handoff if applicable")
    supported_action: Optional[str] = Field(default=None, description="Read-only action performed if any")
    is_fallback: bool = Field(default=False, description="Whether deterministic fallback was used")
    fallback_reason: Optional[str] = Field(default=None, description="Reason fallback was triggered")
    safe_order: Optional[Dict[str, Any]] = Field(default=None, description="Customer-safe order details if available")
    proposal: Optional[Dict[str, Any]] = Field(default=None, description="Optional proposal summary if action was submitted for review")


class ResetResponse(BaseModel):
    """Session reset response."""
    session_id: str
    status: str = "reset"


class TraceResponse(BaseModel):
    """Safe audit trace response."""
    session_id: str
    trace: Optional[Dict[str, Any]] = None


# ---------------------------------------------------------------------------
# FastAPI Application Factory & State
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Aster & Row AI Support API",
    description="Production-grade AI customer support API with deterministic policy authority and safe grounded generation.",
    version="1.0.0",
    docs_url="/docs",
    openapi_url="/openapi.json",
)

# 1. Request Context & Observability Middleware (First in chain)
app.add_middleware(RequestContextMiddleware)

# 2. Configure CORS
cors_origins_raw = os.getenv("CORS_ORIGINS", "http://localhost:5173,http://localhost:3000,http://localhost:4173,http://127.0.0.1:4173")
allowed_origins = [origin.strip() for origin in cors_origins_raw.split(",") if origin.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global orchestrator and safe trace cache with bounded TTL & LRU capacity
_orchestrator: Optional[AgentOrchestrator] = None
_session_traces = BoundedTTLCache(
    maxsize=int(os.getenv("SESSION_TRACE_MAXSIZE", "1000")),
    ttl_seconds=float(os.getenv("SESSION_TRACE_TTL_SECONDS", "3600.0")),
)


def get_orchestrator() -> AgentOrchestrator:
    """Retrieve or initialize the singleton AgentOrchestrator."""
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = AgentOrchestrator()
    return _orchestrator


def set_orchestrator(orchestrator: Optional[AgentOrchestrator]) -> None:
    """Set or override the active AgentOrchestrator (primarily for unit testing)."""
    global _orchestrator
    _orchestrator = orchestrator


# ---------------------------------------------------------------------------
# Global Exception Handlers
# ---------------------------------------------------------------------------

@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Ensure raw exception traces and secrets are never exposed to the client while logging structured errors."""
    request_id = getattr(request.state, "request_id", None) or request.headers.get("X-Request-ID", "unknown")

    # Pass through standard HTTPExceptions with their own status and detail
    if isinstance(exc, HTTPException):
        headers = {"X-Request-ID": request_id} if request_id != "unknown" else None
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail},
            headers=headers,
        )

    # Log internal error with full stack trace and request_id
    logger.error(
        "unhandled_server_exception",
        error=str(exc),
        error_type=type(exc).__name__,
        request_id=request_id,
        exc_info=True,
    )

    headers = {"X-Request-ID": request_id} if request_id != "unknown" else None
    return JSONResponse(
        status_code=500,
        content={
            "detail": "Unable to safely process the request.",
            "request_id": request_id,
        },
        headers=headers,
    )


# ---------------------------------------------------------------------------
# API Endpoints
# ---------------------------------------------------------------------------

@app.get(
    "/health",
    response_model=HealthResponse,
    summary="Health check endpoint",
    description="Dependency-free liveness probe returning service health status.",
)
def health_check() -> HealthResponse:
    return HealthResponse(status="ok")


@app.get(
    "/ready",
    response_model=ReadyResponse,
    summary="Readiness probe endpoint",
    description="Checks that knowledge base is loaded and retriever is initialized.",
)
def readiness_check() -> Any:
    reasons: List[str] = []
    try:
        settings = get_settings()
        kb_path = settings.knowledge_base_path
        if not kb_path.exists():
            reasons.append(f"Knowledge base path does not exist: {kb_path}")
        else:
            md_files = list(kb_path.glob("*.md"))
            if not md_files:
                reasons.append("Knowledge base directory contains no markdown documents.")

        orch = get_orchestrator()
        if not hasattr(orch, "retriever") or orch.retriever is None:
            reasons.append("Retriever is not initialized in orchestrator.")
    except Exception as e:
        reasons.append(f"Initialization check error: {str(e)}")

    if reasons:
        return JSONResponse(
            status_code=503,
            content={"status": "not_ready", "reasons": reasons},
        )
    return ReadyResponse(status="ready", reasons=[])


@app.get(
    "/metrics",
    summary="Prometheus metrics endpoint",
    description="Exposes Prometheus metrics in standard text format.",
)
def metrics_endpoint() -> Response:
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.post(
    "/chat",
    response_model=ChatResponse,
    summary="Process customer support conversation turn",
    description="Processes a multi-turn support query via deterministic policy authority and LLM generation.",
)
def chat_endpoint(request: ChatRequest) -> ChatResponse:
    orchestrator = get_orchestrator()

    session_id = (
        request.session_id.strip()
        if request.session_id and request.session_id.strip()
        else f"session-{uuid.uuid4().hex[:8]}"
    )

    try:
        state = orchestrator.process_turn(session_id, request.message)
    except Exception as exc:
        raise exc
    _session_traces.set(session_id, state.trace)

    public_resp: PublicAgentResponse = state.to_public_response()
    safe_order = state.trace.get("safe_order") if state.trace else None

    dec_state_str = (
        public_resp.decision_state.value
        if isinstance(public_resp.decision_state, DecisionState)
        else str(public_resp.decision_state)
    )

    return ChatResponse(
        session_id=public_resp.session_id,
        turn_id=public_resp.turn_id,
        message=public_resp.message,
        decision_state=dec_state_str,
        citations=public_resp.citations,
        handoff_recommended=public_resp.handoff_recommended,
        handoff_reason=public_resp.handoff_reason,
        supported_action=public_resp.supported_action,
        is_fallback=public_resp.is_fallback,
        fallback_reason=public_resp.fallback_reason,
        safe_order=safe_order,
        proposal=public_resp.proposal,
    )


@app.post(
    "/sessions/{session_id}/reset",
    response_model=ResetResponse,
    summary="Reset an isolated conversation session",
    description="Clears all conversation memory, active order contexts, and topics for the specified session.",
)
def reset_session_endpoint(session_id: str) -> ResetResponse:
    orchestrator = get_orchestrator()
    orchestrator.session_manager.clear_session(session_id)
    _session_traces.delete(session_id)
    return ResetResponse(session_id=session_id, status="reset")


@app.get(
    "/sessions/{session_id}/trace",
    response_model=TraceResponse,
    summary="Get sanitized audit trace for a session",
    description="Returns the sanitized observability trace of the last turn. Never exposes PII, secrets, or internal notes.",
)
def get_session_trace_endpoint(session_id: str) -> TraceResponse:
    trace = _session_traces.get(session_id)
    return TraceResponse(session_id=session_id, trace=trace)


# ---------------------------------------------------------------------------
# Human-in-the-Loop (HITL) Reviewer & Customer Proposal Endpoints
# ---------------------------------------------------------------------------

def _to_proposal_response(proposal, request_id: Optional[str] = None) -> ProposalResponse:
    """Helper converting ProposedActionModel to ProposalResponse without PII."""
    return ProposalResponse(
        id=proposal.id,
        order_id=proposal.order_id,
        session_id=proposal.session_id,
        action_type=proposal.action_type,
        status=proposal.status,
        version=proposal.version,
        created_at=proposal.created_at,
        expires_at=proposal.expires_at,
        decided_by=proposal.decided_by,
        decided_at=proposal.decided_at,
        decision_reason=proposal.decision_reason,
        evidence_snapshot=proposal.evidence_snapshot or {},
        request_id=request_id,
    )


@app.get(
    "/sessions/{session_id}/proposal",
    response_model=Optional[ProposalResponse],
    summary="Get active proposal for customer session",
    description="Returns the active proposal bound strictly to the calling customer's session_id.",
)
def get_customer_session_proposal(session_id: str, request: Request) -> Optional[ProposalResponse]:
    request_id = getattr(request.state, "request_id", None) or request.headers.get("X-Request-ID")
    approval_service = get_approval_service()
    proposals = approval_service.list(session_id=session_id, limit=1)
    if not proposals:
        raise HTTPException(status_code=404, detail="No proposal found for this session.")
    return _to_proposal_response(proposals[0], request_id=request_id)


@app.get(
    "/reviewer/proposals",
    response_model=List[ProposalResponse],
    summary="List proposals for human review",
    description="Lists customer action proposals filtered by status, with pagination.",
)
def list_reviewer_proposals(
    request: Request,
    status: Optional[ProposalStatus] = None,
    order_id: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    reviewer_id: str = Depends(authenticate_reviewer),
) -> List[ProposalResponse]:
    request_id = getattr(request.state, "request_id", None) or request.headers.get("X-Request-ID")
    approval_service = get_approval_service()
    proposals = approval_service.list(status=status, order_id=order_id, limit=limit, offset=offset)
    return [_to_proposal_response(p, request_id=request_id) for p in proposals]


@app.get(
    "/reviewer/proposals/{proposal_id}",
    response_model=ProposalResponse,
    summary="Get detailed proposal for review",
    description="Fetches a specific proposed action by ID. Lazily checks expiration.",
)
def get_reviewer_proposal(
    proposal_id: str,
    request: Request,
    reviewer_id: str = Depends(authenticate_reviewer),
) -> ProposalResponse:
    request_id = getattr(request.state, "request_id", None) or request.headers.get("X-Request-ID")
    approval_service = get_approval_service()
    proposal = approval_service.get(proposal_id)
    if not proposal:
        raise HTTPException(status_code=404, detail=f"Proposal {proposal_id} not found.")
    return _to_proposal_response(proposal, request_id=request_id)


@app.post(
    "/reviewer/proposals/{proposal_id}/approve",
    response_model=ProposalResponse,
    summary="Approve and execute a proposed action",
    description="Approve and atomically execute proposed action. Re-verifies order eligibility and enforces optimistic locking.",
)
def approve_reviewer_proposal(
    proposal_id: str,
    req_body: ApproveProposalRequest,
    request: Request,
    reviewer_id: str = Depends(authenticate_reviewer),
) -> ProposalResponse:
    request_id = getattr(request.state, "request_id", None) or request.headers.get("X-Request-ID")
    approval_service = get_approval_service()
    try:
        proposal = approval_service.approve(
            proposal_id=proposal_id,
            reviewer_id=reviewer_id,
            expected_version=req_body.version,
            reason=req_body.note,
            request_id=request_id,
        )
        return _to_proposal_response(proposal, request_id=request_id)
    except ProposalNotFoundError:
        raise HTTPException(status_code=404, detail=f"Proposal {proposal_id} not found.")
    except ConcurrencyConflictError as cce:
        raise HTTPException(status_code=409, detail=str(cce))
    except InvalidTransition as it:
        raise HTTPException(status_code=400, detail=str(it))


@app.post(
    "/reviewer/proposals/{proposal_id}/reject",
    response_model=ProposalResponse,
    summary="Reject a proposed action",
    description="Reject a proposed action. Requires a reason between 10 and 500 characters.",
)
def reject_reviewer_proposal(
    proposal_id: str,
    req_body: RejectProposalRequest,
    request: Request,
    reviewer_id: str = Depends(authenticate_reviewer),
) -> ProposalResponse:
    request_id = getattr(request.state, "request_id", None) or request.headers.get("X-Request-ID")
    approval_service = get_approval_service()
    try:
        proposal = approval_service.reject(
            proposal_id=proposal_id,
            reviewer_id=reviewer_id,
            reason=req_body.reason,
            expected_version=req_body.version,
            request_id=request_id,
        )
        return _to_proposal_response(proposal, request_id=request_id)
    except ProposalNotFoundError:
        raise HTTPException(status_code=404, detail=f"Proposal {proposal_id} not found.")
    except ConcurrencyConflictError as cce:
        raise HTTPException(status_code=409, detail=str(cce))
    except InvalidTransition as it:
        raise HTTPException(status_code=400, detail=str(it))
    except ValueError as ve:
        raise HTTPException(status_code=422, detail=str(ve))


@app.get(
    "/reviewer/audit",
    response_model=List[AuditEventResponse],
    summary="List immutable audit trail",
    description="Lists append-only audit events for compliance and security auditing.",
)
def get_reviewer_audit(
    request: Request,
    order_id: Optional[str] = None,
    proposal_id: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
    reviewer_id: str = Depends(authenticate_reviewer),
) -> List[AuditEventResponse]:
    approval_service = get_approval_service()
    events = approval_service.audit_repo.list_events(
        order_id=order_id,
        proposal_id=proposal_id,
        limit=limit,
        offset=offset,
    )
    return [
        AuditEventResponse(
            id=ev.id,
            order_id=ev.order_id,
            proposal_id=ev.proposal_id,
            action=ev.action,
            from_state=ev.from_state,
            to_state=ev.to_state,
            decided_by=ev.decided_by,
            reason=ev.reason,
            request_id=ev.request_id,
            timestamp=ev.timestamp,
        )
        for ev in events
    ]

