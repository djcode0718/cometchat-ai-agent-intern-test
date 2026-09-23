"""Deterministic mock LLM provider for offline testing and evaluation."""

from typing import Callable, Dict, Optional, Union

from src.agent.state import DecisionState
from src.llm.base import BaseLLMProvider
from src.llm.models import GeneratedResponse, GroundedGenerationRequest
from src.llm.validator import OutputValidator


class MockLLMProvider(BaseLLMProvider):
    """Deterministic mock provider that produces grounded responses without network calls."""

    def __init__(
        self,
        custom_responses: Optional[Dict[str, str]] = None,
        raw_text_hook: Optional[Callable[[GroundedGenerationRequest], str]] = None,
    ) -> None:
        self.custom_responses = custom_responses or {}
        self.raw_text_hook = raw_text_hook

    @property
    def provider_name(self) -> str:
        return "mock"

    def generate(self, request: GroundedGenerationRequest) -> GeneratedResponse:
        """Generate response using scripted logic or fallback, validated through OutputValidator."""
        # 1. If an injected hook exists, use it
        if self.raw_text_hook is not None:
            raw_text = self.raw_text_hook(request)
            validation = OutputValidator.validate(raw_text, request)
            return validation.repaired_response or OutputValidator.build_fallback(request)

        # 2. If a custom matching response exists, use it
        query_key = request.user_query.strip()
        if query_key in self.custom_responses:
            raw_text = self.custom_responses[query_key]
            validation = OutputValidator.validate(raw_text, request)
            return validation.repaired_response or OutputValidator.build_fallback(request)

        # 3. Default Grounded Generation Logic
        raw_text = self._synthesize_grounded_text(request)
        validation = OutputValidator.validate(raw_text, request)
        return validation.repaired_response or OutputValidator.build_fallback(request)

    def _synthesize_grounded_text(self, request: GroundedGenerationRequest) -> str:
        """Synthesize natural-language text following decision state and approved evidence."""
        state = request.decision_state

        if state == DecisionState.CLARIFY:
            return (
                request.suggested_clarification
                or "Please provide your order ID (e.g., ORD-XXXX) so I can assist you."
            )

        elif state == DecisionState.CONFLICT:
            return (
                "Official Aster & Row guidance contains conflicting instructions for cleaning the Breeze Tumbler: "
                "the Product Care Guide ([11-product-care.md > Breeze Tumbler]) states that the stainless-steel body must be hand-washed, "
                "while the Breeze Tumbler Product Information ([12-breeze-tumbler-product-card.md > Cleaning]) states that all components are dishwasher safe. "
                "Because current official documents conflict, we recommend hand-washing the body or confirming with customer support."
            )

        elif state == DecisionState.ABSTAIN:
            return (
                "The available Aster & Row policy and product documentation is insufficient to answer this request reliably. "
                "I recommend contacting our customer support team for assistance."
            )

        elif state == DecisionState.HANDOFF:
            if request.handoff_reason and "confidential" in request.handoff_reason.lower():
                return "Customer personal details, internal notes, and risk scores are confidential and cannot be disclosed. Please contact customer support if you need assistance with your account."
            if request.customer_safe_order and request.customer_safe_order.requires_human_handoff:
                return f"Order {request.customer_safe_order.order_id} has an operational exception ({request.customer_safe_order.customer_safe_message or 'shipment exception'}) requiring support review. Please contact customer support for assistance."
            return (
                request.suggested_clarification
                or "This request requires assistance from our customer support team. Please connect with a support specialist."
            )

        # state == DecisionState.ANSWER
        if request.customer_safe_order:
            order = request.customer_safe_order
            if order.status == "cancelled":
                return f"Order {order.order_id} is cancelled and will not be shipped."
            if order.status == "returned":
                return f"Order {order.order_id} was returned and has been processed."
            if order.status == "delivered":
                return f"Order {order.order_id} was delivered on {order.delivered_at or 'August 10, 2026'}."
            if order.status in ("shipped", "delayed"):
                eta_str = f"Estimated delivery is {order.estimated_delivery}." if order.estimated_delivery else "A delivery estimate is not currently available."
                return f"Order {order.order_id} is {order.status} with {order.carrier or 'the carrier'} (Tracking: {order.tracking_number or 'unavailable'}). {eta_str}"
            return f"Order {order.order_id} is currently {order.status}. {order.customer_safe_message or ''}".strip()

        # Knowledge Q&A
        if request.approved_evidence:
            sentences = []
            citations = []
            for item in request.approved_evidence:
                sentences.append(item.content)
                if item.citation_str not in citations:
                    citations.append(item.citation_str)
            citations_str = " ".join(citations)
            return f"{' '.join(sentences)} {citations_str}".strip()

        return "Please contact customer support for assistance with your request."
