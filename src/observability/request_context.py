"""ASGI Middleware for X-Request-ID validation, propagation, and structlog contextvars binding."""

import json
import re
import time
import uuid
from typing import Callable

from fastapi import HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp
import structlog
from structlog.contextvars import bind_contextvars, clear_contextvars

from src.observability.logging import get_logger
from src.observability.metrics import (
    HTTP_REQUEST_DURATION_SECONDS,
    HTTP_REQUESTS_IN_FLIGHT,
    HTTP_REQUESTS_TOTAL,
)

# Request ID validation pattern: 8 to 64 alphanumeric characters, dots, underscores, or hyphens
REQUEST_ID_REGEX = re.compile(r"^[A-Za-z0-9._-]{8,64}$")
logger = get_logger("http_access")


def get_route_template(request: Request) -> str:
    """Extract low-cardinality route template (e.g. /sessions/{session_id}/reset) or fallback to normalized path."""
    for route in request.app.routes:
        match, _ = route.matches(request.scope)
        if match.name == "FULL" and hasattr(route, "path"):
            return route.path
    # Fallback: if no route matched (e.g. 404), return normalized path without raw UUIDs
    path = request.url.path
    # Mask path elements that look like UUIDs or order IDs to protect label cardinality
    path = re.sub(r"/[a-f0-9\-]{32,36}", "/{id}", path)
    path = re.sub(r"/ORD-?\d+", "/{order_id}", path)
    return path


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Middleware enforcing Request ID handling, contextvars binding, access logs, and metrics."""

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Validate or generate Request ID
        incoming_id = request.headers.get("X-Request-ID", "").strip()
        if incoming_id and REQUEST_ID_REGEX.match(incoming_id):
            request_id = incoming_id
        else:
            request_id = str(uuid.uuid4())

        # Store on request.state so endpoints/handlers can read it
        request.state.request_id = request_id

        # Bind contextvars for structlog so all logs in this task carry request_id
        clear_contextvars()
        bind_contextvars(request_id=request_id)

        method = request.method
        HTTP_REQUESTS_IN_FLIGHT.inc()
        start_time = time.perf_counter()

        response: Response
        status_code = 500
        route_template = ""
        try:
            response = await call_next(request)
            status_code = response.status_code
            route_template = get_route_template(request)
            response.headers["X-Request-ID"] = request_id
            return response
        except Exception as exc:
            route_template = get_route_template(request)
            status_code = getattr(exc, "status_code", 500)

            # Log exception with stack trace and request_id
            logger.error(
                "unhandled_server_exception",
                error=str(exc),
                error_type=type(exc).__name__,
                request_id=request_id,
                route=route_template,
                exc_info=True,
            )

            # Return safe error response without leaking internal exception text
            if isinstance(exc, HTTPException):
                return Response(
                    content=exc.detail if isinstance(exc.detail, str) else str(exc.detail),
                    status_code=exc.status_code,
                    headers={"X-Request-ID": request_id, "content-type": "application/json"},
                )

            import json
            err_body = json.dumps({
                "detail": "Unable to safely process the request.",
                "request_id": request_id,
            })
            return Response(
                content=err_body,
                status_code=500,
                headers={"X-Request-ID": request_id, "content-type": "application/json"},
            )
        finally:
            latency_seconds = time.perf_counter() - start_time
            latency_ms = round(latency_seconds * 1000, 2)

            HTTP_REQUESTS_IN_FLIGHT.dec()

            if not route_template:
                route_template = get_route_template(request)

            # Record Prometheus metrics (labels: method, route, status)
            status_str = str(status_code)
            HTTP_REQUESTS_TOTAL.labels(
                method=method, route=route_template, status=status_str
            ).inc()
            HTTP_REQUEST_DURATION_SECONDS.labels(
                method=method, route=route_template, status=status_str
            ).observe(latency_seconds)

            # Access log: one clean line per request; NEVER log request bodies
            if route_template != "/health" and route_template != "/metrics":
                logger.info(
                    "http_request_finished",
                    method=method,
                    route=route_template,
                    status=status_code,
                    latency_ms=latency_ms,
                    request_id=request_id,
                )

            clear_contextvars()
