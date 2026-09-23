"""Tests for deterministic query and entity routing."""

from src.agent.router import Router
from src.agent.state import OrderIntent, RouteType
from src.core.session import SessionManager


def test_route_knowledge_policy_questions():
    queries = [
        "How long do I have to return an unused backpack?",
        "What are the benefits of TrailPlus membership?",
        "Do you ship internationally to Canada?",
        "How should I clean the Breeze Tumbler?",
        "What is your warranty coverage on drinkware?",
    ]
    for query in queries:
        route, intent, extracted_id, active_id = Router.route(query)
        assert route == RouteType.KNOWLEDGE
        assert extracted_id is None


def test_route_order_with_explicit_id():
    route, intent, extracted_id, active_id = Router.route("Where is ORD-1007 and when should it arrive?")
    assert route == RouteType.ORDER
    assert intent == OrderIntent.SHIPPING_TRACKING
    assert extracted_id == "ORD-1007"
    assert active_id == "ORD-1007"


def test_route_order_with_lowercase_id():
    route, intent, extracted_id, active_id = Router.route("Can you check ord-1004 please?")
    assert route == RouteType.ORDER
    assert extracted_id == "ORD-1004"
    assert active_id == "ORD-1004"


def test_route_order_missing_id():
    route, intent, extracted_id, active_id = Router.route("Where is my order?")
    assert route == RouteType.ORDER
    assert intent == OrderIntent.SHIPPING_TRACKING
    assert extracted_id is None
    assert active_id is None


def test_route_arbitrary_numbers_not_order_ids():
    # Arbitrary raw numbers must not be treated as order IDs
    route, intent, extracted_id, active_id = Router.route("Is model 1001 covered under warranty?")
    assert route == RouteType.KNOWLEDGE
    assert extracted_id is None


def test_route_multiturn_followup_with_active_session():
    manager = SessionManager()
    session = manager.create_session("session-test-1", active_order_id="ORD-1007")

    # Follow-up referencing "it" with active session order
    route, intent, extracted_id, active_id = Router.route("When will it arrive?", session=session)
    assert route == RouteType.ORDER
    assert intent == OrderIntent.SHIPPING_TRACKING
    assert extracted_id is None
    assert active_id == "ORD-1007"


def test_route_explicit_order_id_overrides_session_active_id():
    manager = SessionManager()
    session = manager.create_session("session-test-2", active_order_id="ORD-1007")

    # Current message mentions ORD-1003 explicitly
    route, intent, extracted_id, active_id = Router.route("What about ORD-1003?", session=session)
    assert route == RouteType.ORDER
    assert extracted_id == "ORD-1003"
    assert active_id == "ORD-1003"
