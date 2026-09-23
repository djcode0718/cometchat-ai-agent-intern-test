"""Deterministic intent and entity router for multi-turn sessions."""

import re
from typing import Optional, Tuple

from src.agent.state import OrderIntent, RouteType
from src.core.models import Session
from src.tools.normalizer import extract_candidate_order_id

# Regex patterns for order-related phrasing
ORDER_KEYWORDS_PATTERN = re.compile(
    r"\b(order|package|shipment|tracking|track|delivery|arrive|arriving|get here|cancel|cancellation|status)\b",
    re.IGNORECASE,
)
ORDER_FOLLOWUP_PATTERN = re.compile(
    r"\b(it|that|this order|the package|my package|the shipment)\b",
    re.IGNORECASE,
)
CANCELLATION_PATTERN = re.compile(r"\b(cancel|cancellation|stop order)\b", re.IGNORECASE)
SHIPPING_TRACKING_PATTERN = re.compile(
    r"\b(where is|track|tracking|arrive|arriving|get here|when will|carrier|eta|in transit)\b",
    re.IGNORECASE,
)
DAMAGE_EXCEPTION_PATTERN = re.compile(
    r"\b(damaged|broken|defective|wrong item|incorrect item|exception)\b",
    re.IGNORECASE,
)
RETURN_REFUND_PATTERN = re.compile(
    r"\b(return|refund|exchange|send back)\b",
    re.IGNORECASE,
)
PRIVACY_PROMPT_PATTERN = re.compile(
    r"\b(email|address|risk score|warehouse note|internal note|hidden prompt|system prompt|system instruction|secret|credentials)\b",
    re.IGNORECASE,
)


class Router:
    """Routes incoming queries to KNOWLEDGE, ORDER, or UNSUPPORTED with multi-turn entity resolution."""

    @staticmethod
    def detect_order_intent(query: str) -> OrderIntent:
        """Classify specific order intent."""
        if CANCELLATION_PATTERN.search(query):
            return OrderIntent.CANCELLATION
        if DAMAGE_EXCEPTION_PATTERN.search(query):
            return OrderIntent.DAMAGE_EXCEPTION
        if RETURN_REFUND_PATTERN.search(query):
            return OrderIntent.RETURN_REFUND
        if SHIPPING_TRACKING_PATTERN.search(query):
            return OrderIntent.SHIPPING_TRACKING
        return OrderIntent.STATUS

    @classmethod
    def route(
        cls,
        query: str,
        session: Optional[Session] = None,
    ) -> Tuple[RouteType, Optional[OrderIntent], Optional[str], Optional[str]]:
        """Determine routing, intent, extracted order ID, and resolved active order ID.

        Returns:
            (route, order_intent, extracted_order_id, active_order_id)
        """
        extracted_id = extract_candidate_order_id(query)
        session_active_id = session.active_order_id if session else None

        # 1. Explicit Order ID present in query -> ORDER route
        if extracted_id:
            intent = cls.detect_order_intent(query)
            return RouteType.ORDER, intent, extracted_id, extracted_id

        # 2. Query contains order keywords or follow-up pronouns referencing an active order
        has_order_keywords = bool(ORDER_KEYWORDS_PATTERN.search(query))
        has_followup_pronoun = bool(ORDER_FOLLOWUP_PATTERN.search(query))

        if session_active_id and (has_order_keywords or has_followup_pronoun):
            # Check if query is actually a generic policy question vs order-specific follow-up
            # e.g., "Where is ORD-1007?" followed by "When will it arrive?" -> ORDER with active ID
            intent = cls.detect_order_intent(query)
            return RouteType.ORDER, intent, None, session_active_id

        # 3. Query is about an order status/lookup but missing an order ID
        if has_order_keywords and any(
            phrase in query.lower()
            for phrase in [
                "where is my order", "track my order", "order status",
                "when will my order", "cancel my order", "check my order",
                "where is my package", "where's my order"
            ]
        ):
            intent = cls.detect_order_intent(query)
            return RouteType.ORDER, intent, None, None

        # 4. Default to Knowledge / Policy routing
        return RouteType.KNOWLEDGE, None, None, session_active_id
