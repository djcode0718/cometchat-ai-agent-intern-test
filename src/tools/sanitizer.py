"""Data sanitization layer for stripping PII and internal fields from order data."""

from typing import List
from src.tools.order_models import (
    CustomerSafeOrderItem,
    RawOrder,
    RawOrderItem,
)


class OrderSanitizer:
    """Structurally removes customer PII and internal metadata from raw orders."""

    @staticmethod
    def sanitize_items(items: List[RawOrderItem]) -> List[CustomerSafeOrderItem]:
        """Convert raw order items to customer-safe items without internal SKUs."""
        return [
            CustomerSafeOrderItem(
                name=item.name,
                quantity=item.quantity,
                final_sale=item.final_sale,
            )
            for item in items
        ]

    @classmethod
    def sanitize_to_dict(cls, raw_order: RawOrder) -> dict:
        """Produce an intermediate dictionary strictly devoid of customer PII and internal fields.

        Explicitly deletes customer PII (name, email, address) and internal fields (risk_score,
        warehouse_note, support_tags), ensuring untrusted text and prompt injections never survive.
        """
        safe_items = cls.sanitize_items(raw_order.items)

        return {
            "order_id": raw_order.order_id,
            "membership_tier": raw_order.membership_tier,
            "items": safe_items,
            "placed_at": raw_order.placed_at,
            "status": raw_order.status,
            "status_updated_at": raw_order.status_updated_at,
            "shipped_at": raw_order.shipped_at,
            "delivered_at": raw_order.delivered_at,
            "carrier": raw_order.carrier,
            "tracking_number": raw_order.tracking_number,
            "estimated_delivery": raw_order.estimated_delivery,
            "customer_safe_message": raw_order.customer_safe_message,
        }
