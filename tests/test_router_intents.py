"""Unit tests verifying deterministic order intent classification and routing."""

import pytest
from src.agent.router import Router
from src.agent.state import OrderIntent, RouteType
from src.core.models import Session


def test_router_cancellation_intent_family():
    """Verify distinct cancellation phrasing variants."""
    assert Router.detect_order_intent("Can you please halt shipment ORD-1001 before it leaves the warehouse?") == OrderIntent.CANCELLATION
    assert Router.detect_order_intent("Can you cancel that?") == OrderIntent.CANCELLATION
    assert Router.detect_order_intent("Can I cancel my pending order ORD-1001?") == OrderIntent.CANCELLATION
    assert Router.detect_order_intent("Stop shipment on ORD-1002 immediately") == OrderIntent.CANCELLATION


def test_router_damage_and_exception_family():
    """Verify damage, wrong item, crushed box, and formal dispute reports."""
    assert Router.detect_order_intent("You sent me the wrong color tumbler in order ORD-1003.") == OrderIntent.DAMAGE_EXCEPTION
    assert Router.detect_order_intent("My package ORD-1010 arrived completely crushed and broken.") == OrderIntent.DAMAGE_EXCEPTION
    assert Router.detect_order_intent("I want to file a formal dispute regarding a lost package ORD-1010.") == OrderIntent.DAMAGE_EXCEPTION
    assert Router.detect_order_intent("Item arrived broken in ORD-1005") == OrderIntent.DAMAGE_EXCEPTION


def test_router_return_refund_family():
    """Verify explicit return and refund inquiry phrasings."""
    assert Router.detect_order_intent("I want to return ORD-1006 because it doesn't fit.") == OrderIntent.RETURN_REFUND
    assert Router.detect_order_intent("What is the refund status?") == OrderIntent.RETURN_REFUND


def test_router_shipping_tracking_and_typo_family():
    """Verify carrier drop-off phrasing, delivery van, and common typos."""
    assert Router.detect_order_intent("Where is my package ORD-1003?") == OrderIntent.SHIPPING_TRACKING
    assert Router.detect_order_intent("Any idea when the delivery van will drop off my stuff for ORD-1005?") == OrderIntent.SHIPPING_TRACKING
    assert Router.detect_order_intent("Wher is my pakage ORD-1007") == OrderIntent.SHIPPING_TRACKING
    assert Router.detect_order_intent("Check my delivery") == OrderIntent.SHIPPING_TRACKING


def test_router_compound_inquiry_and_status_defaults():
    """Verify compound policy + order lookup queries identify order inquiry intents."""
    assert Router.detect_order_intent("What is the return policy, and where is my order ORD-1003?") in (OrderIntent.RETURN_REFUND, OrderIntent.STATUS)
    assert Router.detect_order_intent("Where is my order ORD-1002?") == OrderIntent.SHIPPING_TRACKING


def test_router_missing_id_order_lookup_routes_to_order():
    """Verify inquiries about order status without explicit ID route to ORDER for clarification."""
    route, intent, ext_id, act_id = Router.route("Check status of order")
    assert route == RouteType.ORDER
    assert intent == OrderIntent.STATUS
    assert ext_id is None

    route, intent, ext_id, act_id = Router.route("Check my delivery")
    assert route == RouteType.ORDER
    assert intent == OrderIntent.SHIPPING_TRACKING
    assert ext_id is None

    route, intent, ext_id, act_id = Router.route("Can you cancel that?")
    assert route == RouteType.ORDER
    assert intent == OrderIntent.CANCELLATION
    assert ext_id is None


def test_router_multi_turn_order_binding():
    """Verify active order session retention and pronoun binding."""
    session = Session(session_id="test_sess_01", active_order_id="ORD-1001")
    route, intent, ext_id, act_id = Router.route("When will it arrive?", session=session)
    assert route == RouteType.ORDER
    assert act_id == "ORD-1001"
