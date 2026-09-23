"""Domain models for raw orders, sanitization boundaries, and customer-safe representations."""

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# RAW INTERNAL MODELS (Strictly confined to repository & processing boundary)
# ---------------------------------------------------------------------------

class RawCustomer(BaseModel):
    """Raw customer details containing sensitive PII."""

    name: str = Field(..., description="Customer full name (PII)")
    email: str = Field(..., description="Customer email address (PII)")
    shipping_address: str = Field(..., description="Customer physical address (PII)")


class RawInternal(BaseModel):
    """Internal operational details containing sensitive or untrusted text."""

    risk_score: int = Field(..., description="Internal risk score")
    warehouse_note: str = Field(..., description="Internal warehouse note (Untrusted)")
    support_tags: List[str] = Field(default_factory=list, description="Internal support tags")


class RawOrderItem(BaseModel):
    """Raw order line item."""

    sku: str = Field(..., description="Item SKU code")
    name: str = Field(..., description="Item product name")
    quantity: int = Field(..., description="Item quantity ordered")
    final_sale: bool = Field(default=False, description="Whether item was final sale")


class RawOrder(BaseModel):
    """Complete raw order record as loaded from data storage."""

    order_id: str = Field(..., description="Canonical order ID (e.g. ORD-1001)")
    customer: RawCustomer = Field(..., description="Raw customer PII")
    membership_tier: str = Field(..., description="Membership tier: standard or trailplus")
    items: List[RawOrderItem] = Field(..., description="List of ordered items")
    placed_at: str = Field(..., description="ISO timestamp when order was placed")
    status: str = Field(..., description="Authoritative order status")
    status_updated_at: str = Field(..., description="ISO timestamp of last status update")
    shipped_at: Optional[str] = Field(default=None, description="ISO timestamp of shipment")
    delivered_at: Optional[str] = Field(default=None, description="ISO timestamp of delivery")
    carrier: Optional[str] = Field(default=None, description="Shipping carrier name")
    tracking_number: Optional[str] = Field(default=None, description="Carrier tracking number")
    estimated_delivery: Optional[str] = Field(
        default=None, description="Estimated delivery date (YYYY-MM-DD)"
    )
    customer_safe_message: Optional[str] = Field(
        default=None, description="Standard safe status message"
    )
    internal: RawInternal = Field(..., description="Internal sensitive metadata")


# ---------------------------------------------------------------------------
# CUSTOMER-SAFE MODELS (Safe for LLM prompt context & customer presentation)
# ---------------------------------------------------------------------------

class CustomerSafeOrderItem(BaseModel):
    """Safe representation of an ordered item (no internal SKUs or cost fields)."""

    name: str = Field(..., description="Product name")
    quantity: int = Field(..., description="Quantity ordered")
    final_sale: bool = Field(..., description="Final sale indicator")


class CustomerSafeOrder(BaseModel):
    """Sanitized and reconciled customer-safe order evidence."""

    order_id: str = Field(..., description="Order identifier")
    membership_tier: str = Field(..., description="Membership tier")
    items: List[CustomerSafeOrderItem] = Field(..., description="Customer-safe item list")
    placed_at: str = Field(..., description="Order placed timestamp")
    status: str = Field(..., description="Authoritative reconciled status")
    status_updated_at: str = Field(..., description="Status update timestamp")
    shipped_at: Optional[str] = Field(default=None, description="Shipment timestamp")
    delivered_at: Optional[str] = Field(default=None, description="Delivery timestamp")
    carrier: Optional[str] = Field(default=None, description="Active carrier name")
    tracking_number: Optional[str] = Field(default=None, description="Active tracking number")
    estimated_delivery: Optional[str] = Field(
        default=None, description="Active estimated delivery date or None if unavailable"
    )
    customer_safe_message: Optional[str] = Field(
        default=None, description="Safe operational message"
    )

    # Reconciled structured business fields
    is_cancellable: bool = Field(
        default=False,
        description="Whether order is currently eligible for cancellation request",
    )
    cancellation_ineligibility_reason: Optional[str] = Field(
        default=None,
        description="Reason why cancellation is not possible (e.g. status or window expired)",
    )
    requires_human_handoff: bool = Field(
        default=False,
        description="True if status is exception or operational issue requires human assistance",
    )
    handoff_reason: Optional[str] = Field(
        default=None,
        description="Reason for human handoff if required",
    )


class OrderDatasetSnapshot(BaseModel):
    """Metadata and records container for orders.json snapshot."""

    dataset_name: str
    snapshot_at: str
    orders: List[RawOrder]
