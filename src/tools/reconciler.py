"""Deterministic status reconciliation and business rule processing for orders."""

from datetime import datetime
from typing import Optional

from src.tools.order_models import CustomerSafeOrder, RawOrder
from src.tools.sanitizer import OrderSanitizer

# Standard cancellation window duration in seconds (30 minutes)
CANCELLATION_WINDOW_SECONDS = 30 * 60


def parse_iso_timestamp(ts_str: Optional[str]) -> Optional[datetime]:
    """Parse standard ISO 8601 timestamp with UTC timezone handling."""
    if not ts_str:
        return None
    cleaned = ts_str.replace("Z", "+00:00")
    return datetime.fromisoformat(cleaned)


class StatusReconciler:
    """Reconciles authoritative order status with potentially stale tracking fields and business rules."""

    @classmethod
    def reconcile(
        cls, raw_order: RawOrder, snapshot_time_str: Optional[str] = None
    ) -> CustomerSafeOrder:
        """Transform raw order into a sanitized, reconciled CustomerSafeOrder instance."""
        sanitized_data = OrderSanitizer.sanitize_to_dict(raw_order)
        status = raw_order.status.lower().strip()

        # Base fields initialized from sanitized dictionary
        carrier = sanitized_data["carrier"]
        tracking_number = sanitized_data["tracking_number"]
        estimated_delivery = sanitized_data["estimated_delivery"]
        requires_human_handoff = False
        handoff_reason = None
        is_cancellable = False
        cancellation_ineligibility_reason = None

        # -------------------------------------------------------------------
        # 1. Authoritative Status Precedence & Stale Field Suppression
        # -------------------------------------------------------------------
        if status in ("cancelled", "returned"):
            # Suppress stale tracking, carrier, and ETA from prior system states
            carrier = None
            tracking_number = None
            estimated_delivery = None
            is_cancellable = False
            cancellation_ineligibility_reason = f"Order is already {status}"

        elif status == "exception":
            requires_human_handoff = True
            handoff_reason = "Shipment has an operational exception requiring human support review"
            is_cancellable = False
            cancellation_ineligibility_reason = (
                "Order has an operational exception requiring support review"
            )

        elif status in ("processing", "shipped", "delayed", "delivered"):
            is_cancellable = False
            cancellation_ineligibility_reason = (
                f"Order has entered {status} and can no longer be cancelled through the standard process"
            )

        elif status == "pending":
            # ---------------------------------------------------------------
            # 2. Deterministic Cancellation Window Calculation
            # ---------------------------------------------------------------
            placed_dt = parse_iso_timestamp(raw_order.placed_at)
            snapshot_dt = parse_iso_timestamp(snapshot_time_str)

            if placed_dt and snapshot_dt:
                elapsed_seconds = (snapshot_dt - placed_dt).total_seconds()
                if 0 <= elapsed_seconds <= CANCELLATION_WINDOW_SECONDS:
                    is_cancellable = True
                    cancellation_ineligibility_reason = None
                else:
                    is_cancellable = False
                    cancellation_ineligibility_reason = (
                        "Cancellation window (30 minutes from placement) has expired"
                    )
            else:
                # If timestamps cannot be compared, order is pending
                is_cancellable = True
                cancellation_ineligibility_reason = None

        # Build and return immutable CustomerSafeOrder model
        return CustomerSafeOrder(
            order_id=sanitized_data["order_id"],
            membership_tier=sanitized_data["membership_tier"],
            items=sanitized_data["items"],
            placed_at=sanitized_data["placed_at"],
            status=raw_order.status,
            status_updated_at=sanitized_data["status_updated_at"],
            shipped_at=sanitized_data["shipped_at"],
            delivered_at=sanitized_data["delivered_at"],
            carrier=carrier,
            tracking_number=tracking_number,
            estimated_delivery=estimated_delivery,
            customer_safe_message=sanitized_data["customer_safe_message"],
            is_cancellable=is_cancellable,
            cancellation_ineligibility_reason=cancellation_ineligibility_reason,
            requires_human_handoff=requires_human_handoff,
            handoff_reason=handoff_reason,
        )
