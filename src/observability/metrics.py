"""Prometheus metrics definitions with strict label cardinality boundaries."""

import os
from prometheus_client import Counter, Gauge, Histogram

# Check if observability is enabled via environment
OBSERVABILITY_ENABLED = os.getenv("OBSERVABILITY_ENABLED", "true").lower() in ("true", "1", "yes")

# HTTP server metrics
HTTP_REQUESTS_TOTAL = Counter(
    "http_requests_total",
    "Total count of HTTP requests processed by endpoint and status.",
    ["method", "route", "status"],
)

HTTP_REQUEST_DURATION_SECONDS = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency in seconds from entry to response completion.",
    ["method", "route", "status"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0),
)

HTTP_REQUESTS_IN_FLIGHT = Gauge(
    "http_requests_in_flight",
    "Current number of HTTP requests executing concurrently.",
)

# Agent execution metrics
AGENT_TURNS_TOTAL = Counter(
    "agent_turns_total",
    "Total count of agent turns processed by route and decision state.",
    ["route", "decision_state"],
)

AGENT_STAGE_DURATION_SECONDS = Histogram(
    "agent_stage_duration_seconds",
    "Execution duration in seconds of internal agent stages.",
    ["stage"],
    buckets=(0.0005, 0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0),
)

# LLM provider metrics
LLM_CALLS_TOTAL = Counter(
    "llm_calls_total",
    "Total count of LLM provider invocations by provider, model, and outcome.",
    ["provider", "model", "outcome"],
)

LLM_FALLBACK_TOTAL = Counter(
    "llm_fallback_total",
    "Total count of deterministic fallbacks triggered by failure reason.",
    ["reason"],
)
