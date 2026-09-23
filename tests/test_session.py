"""Tests for in-memory session management and isolation."""

from src.core.session import SessionManager


def test_session_creation_and_retrieval():
    manager = SessionManager()
    session = manager.create_session("session-1")
    assert session.session_id == "session-1"
    assert len(session.messages) == 0

    retrieved = manager.get_session("session-1")
    assert retrieved is session


def test_session_isolation():
    manager = SessionManager()
    s1 = manager.create_session("session-1")
    s2 = manager.create_session("session-2")

    manager.add_message("session-1", role="user", content="Hello from user 1")
    manager.update_active_order_id("session-1", "ORD-1001")

    # Assert session-2 was not mutated
    assert len(s1.messages) == 1
    assert s1.active_order_id == "ORD-1001"
    assert len(s2.messages) == 0
    assert s2.active_order_id is None


def test_session_message_history():
    manager = SessionManager()
    s = manager.get_or_create_session("session-test")

    manager.add_message("session-test", "user", "What is my order status?")
    manager.add_message("session-test", "assistant", "Please provide your order ID.")
    manager.add_message("session-test", "user", "ORD-1007")

    assert len(s.messages) == 3
    assert s.messages[0].role == "user"
    assert s.messages[1].role == "assistant"
    assert s.messages[2].content == "ORD-1007"


def test_session_clear_and_reset():
    manager = SessionManager()
    manager.create_session("s1")
    manager.create_session("s2")
    assert len(manager.list_sessions()) == 2

    assert manager.clear_session("s1") is True
    assert manager.get_session("s1") is None
    assert len(manager.list_sessions()) == 1

    manager.reset_all()
    assert len(manager.list_sessions()) == 0
