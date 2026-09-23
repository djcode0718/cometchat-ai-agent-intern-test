"""Tests for order status reconciliation, stale ETA suppression, and business rule enforcement."""

from src.tools.orders import get_order_repository


def test_cancelled_order_stale_eta_suppression():
    """ORD-1004 is cancelled but had raw stale carrier and ETA fields.

    Authoritative status must suppress stale tracking/ETA so it never claims the order is arriving.
    """
    repo = get_order_repository()
    order = repo.lookup_order("ORD-1004")

    assert order is not None
    assert order.status == "cancelled"
    assert order.carrier is None
    assert order.tracking_number is None
    assert order.estimated_delivery is None
    assert order.is_cancellable is False


def test_returned_order_stale_data_suppression():
    """ORD-1008 is returned and should not report active delivery/transit ETA."""
    repo = get_order_repository()
    order = repo.lookup_order("ORD-1008")

    assert order is not None
    assert order.status == "returned"
    assert order.carrier is None
    assert order.tracking_number is None
    assert order.estimated_delivery is None


def test_shipped_order_without_eta_not_invented():
    """ORD-1011 has status 'shipped' but no estimated_delivery. Must preserve None/unavailable."""
    repo = get_order_repository()
    order = repo.lookup_order("ORD-1011")

    assert order is not None
    assert order.status == "shipped"
    assert order.carrier == "Canada Post"
    assert order.tracking_number == "AR1011CA00001"
    assert order.estimated_delivery is None


def test_pending_order_within_cancellation_window():
    """ORD-1001 was placed at 11:45:00Z and snapshot is 12:00:00Z (15 min elapsed).

    Within 30 min window -> is_cancellable should be True.
    """
    repo = get_order_repository()
    order = repo.lookup_order("ORD-1001")

    assert order is not None
    assert order.status == "pending"
    assert order.is_cancellable is True
    assert order.cancellation_ineligibility_reason is None


def test_processing_order_cancellation_ineligible():
    """ORD-1002 has entered 'processing'. Cannot be cancelled through standard cancellation."""
    repo = get_order_repository()
    order = repo.lookup_order("ORD-1002")

    assert order is not None
    assert order.status == "processing"
    assert order.is_cancellable is False
    assert order.cancellation_ineligibility_reason is not None


def test_exception_order_triggers_handoff():
    """ORD-1010 has status 'exception' which requires human support review."""
    repo = get_order_repository()
    order = repo.lookup_order("ORD-1010")

    assert order is not None
    assert order.status == "exception"
    assert order.requires_human_handoff is True
    assert order.handoff_reason is not None


def test_delayed_order_preserves_carrier_and_updated_eta():
    """ORD-1005 has status 'delayed' with active carrier and ETA."""
    repo = get_order_repository()
    order = repo.lookup_order("ORD-1005")

    assert order is not None
    assert order.status == "delayed"
    assert order.carrier == "FedEx"
    assert order.tracking_number == "7810000001005"
    assert order.estimated_delivery == "2026-08-20"
    assert order.is_cancellable is False


def test_delivered_order_state():
    """ORD-1006 has status 'delivered' with confirmed delivery timestamp."""
    repo = get_order_repository()
    order = repo.lookup_order("ORD-1006")

    assert order is not None
    assert order.status == "delivered"
    assert order.delivered_at == "2026-08-10T19:05:00Z"
    assert order.carrier == "UPS"


def test_final_sale_item_flag_preservation():
    """ORD-1009 contains a final sale item. Safe item representation must reflect final_sale=True."""
    repo = get_order_repository()
    order = repo.lookup_order("ORD-1009")

    assert order is not None
    assert len(order.items) == 1
    assert order.items[0].final_sale is True
