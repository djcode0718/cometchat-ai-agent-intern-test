"""In-memory session manager supporting multi-turn conversation state."""

import uuid
from typing import Dict, List, Optional

from src.core.models import Message, MessageRole, Session


class SessionManager:
    """Manages isolated in-memory user sessions."""

    def __init__(self) -> None:
        self._sessions: Dict[str, Session] = {}

    def create_session(
        self,
        session_id: Optional[str] = None,
        active_order_id: Optional[str] = None,
        current_topic: Optional[str] = None,
    ) -> Session:
        """Create and store a new isolated session."""
        sid = session_id or str(uuid.uuid4())
        session = Session(
            session_id=sid,
            active_order_id=active_order_id,
            current_topic=current_topic,
        )
        self._sessions[sid] = session
        return session

    def get_session(self, session_id: str) -> Optional[Session]:
        """Retrieve an existing session by ID, or None if not found."""
        return self._sessions.get(session_id)

    def get_or_create_session(self, session_id: Optional[str] = None) -> Session:
        """Retrieve an existing session or create a new one if it does not exist."""
        if session_id and session_id in self._sessions:
            return self._sessions[session_id]
        return self.create_session(session_id=session_id)

    def add_message(
        self,
        session_id: str,
        role: MessageRole,
        content: str,
        metadata: Optional[dict] = None,
    ) -> Message:
        """Add a message to a session's conversation history."""
        session = self.get_or_create_session(session_id)
        return session.add_message(role=role, content=content, metadata=metadata)

    def update_active_order_id(
        self, session_id: str, order_id: Optional[str]
    ) -> Optional[Session]:
        """Update active order ID for session tracking."""
        session = self.get_session(session_id)
        if session:
            session.active_order_id = order_id
        return session

    def update_current_topic(
        self, session_id: str, topic: Optional[str]
    ) -> Optional[Session]:
        """Update active conversation topic."""
        session = self.get_session(session_id)
        if session:
            session.current_topic = topic
        return session

    def clear_session(self, session_id: str) -> bool:
        """Remove a session completely. Returns True if removed, False otherwise."""
        if session_id in self._sessions:
            del self._sessions[session_id]
            return True
        return False

    def list_sessions(self) -> List[str]:
        """List all active session IDs."""
        return list(self._sessions.keys())

    def reset_all(self) -> None:
        """Reset all sessions (useful for tests)."""
        self._sessions.clear()
