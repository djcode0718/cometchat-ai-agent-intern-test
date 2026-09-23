"""FastAPI REST API layer for Aster & Row AI Support Agent."""

import os
import uuid
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator

load_dotenv()

from src.agent.orchestrator import AgentOrchestrator
from src.agent.state import DecisionState, PublicAgentResponse


# ---------------------------------------------------------------------------
# Pydantic Request & Response Schemas
# ---------------------------------------------------------------------------

class HealthResponse(BaseModel):
    """Health check response."""
    status: str = "ok"


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

# Configure CORS
cors_origins_raw = os.getenv("CORS_ORIGINS", "http://localhost:5173,http://localhost:3000")
allowed_origins = [origin.strip() for origin in cors_origins_raw.split(",") if origin.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global orchestrator and safe trace cache
_orchestrator: Optional[AgentOrchestrator] = None
_session_traces: Dict[str, Dict[str, Any]] = {}


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
    """Ensure raw exception traces and secrets are never exposed to the client."""
    # HTTPExceptions should bubble with their own status and message
    if isinstance(exc, HTTPException):
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
    return JSONResponse(
        status_code=500,
        content={"detail": "Unable to safely process the request."},
    )


# ---------------------------------------------------------------------------
# API Endpoints
# ---------------------------------------------------------------------------

@app.get(
    "/health",
    response_model=HealthResponse,
    summary="Health check endpoint",
    description="Returns service health status without making any LLM or external calls.",
)
def health_check() -> HealthResponse:
    return HealthResponse(status="ok")


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
        _session_traces[session_id] = state.trace

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
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail="Unable to safely process the request.",
        ) from exc


@app.post(
    "/sessions/{session_id}/reset",
    response_model=ResetResponse,
    summary="Reset an isolated conversation session",
    description="Clears all conversation memory, active order contexts, and topics for the specified session.",
)
def reset_session_endpoint(session_id: str) -> ResetResponse:
    orchestrator = get_orchestrator()
    orchestrator.session_manager.clear_session(session_id)
    if session_id in _session_traces:
        del _session_traces[session_id]
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
