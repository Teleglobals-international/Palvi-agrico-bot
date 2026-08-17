"""
Conversation Manager - manages call sessions and conversation state.
Uses in-memory store with optional Redis backing for production.
"""

from datetime import datetime
from typing import Dict, List, Optional, Any

import structlog

from app.core.exceptions import ConversationNotFoundError
from app.shared.models import (
    CallDirection,
    CallStatus,
    ConversationMessage,
    ConversationRole,
    ConversationSession,
    IndustryType,
)
from app.shared.utils import generate_session_id

logger = structlog.get_logger(__name__)


class ConversationManager:
    """
    Manages conversation sessions for all active calls.
    Stores message history and session metadata.
    """

    def __init__(self):
        self._sessions: Dict[str, ConversationSession] = {}

    def create_session(
        self,
        industry: IndustryType,
        direction: CallDirection,
        call_sid: Optional[str] = None,
        caller_number: Optional[str] = None,
        callee_number: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ConversationSession:
        """
        Create a new conversation session.

        Args:
            industry: The industry type for this call.
            direction: Inbound or outbound.
            call_sid: Exotel call SID.
            caller_number: Caller's phone number.
            callee_number: Callee's phone number.
            metadata: Additional metadata.

        Returns:
            The created ConversationSession.
        """
        session_id = generate_session_id()

        session = ConversationSession(
            session_id=session_id,
            industry=industry,
            direction=direction,
            call_sid=call_sid,
            caller_number=caller_number,
            callee_number=callee_number,
            metadata=metadata or {},
        )

        self._sessions[session_id] = session

        logger.info(
            "session_created",
            session_id=session_id,
            industry=industry.value,
            direction=direction.value,
            call_sid=call_sid,
        )

        return session

    def get_session(self, session_id: str) -> ConversationSession:
        """
        Retrieve a session by ID.

        Args:
            session_id: The session identifier.

        Returns:
            The ConversationSession.

        Raises:
            ConversationNotFoundError: If session does not exist.
        """
        session = self._sessions.get(session_id)
        if session is None:
            raise ConversationNotFoundError(session_id)
        return session

    def get_session_by_call_sid(self, call_sid: str) -> Optional[ConversationSession]:
        """
        Find a session by Exotel call SID.

        Args:
            call_sid: The Exotel call SID.

        Returns:
            The session if found, None otherwise.
        """
        for session in self._sessions.values():
            if session.call_sid == call_sid:
                return session
        return None

    def add_message(
        self,
        session_id: str,
        role: ConversationRole,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ConversationMessage:
        """
        Add a message to a session's conversation history.

        Args:
            session_id: The session to add the message to.
            role: Who sent the message (user, agent, system).
            content: The message text.
            metadata: Optional message metadata.

        Returns:
            The created ConversationMessage.
        """
        session = self.get_session(session_id)

        message = ConversationMessage(
            role=role,
            content=content,
            timestamp=datetime.utcnow(),
            metadata=metadata,
        )

        session.messages.append(message)

        logger.debug(
            "message_added",
            session_id=session_id,
            role=role.value,
            content_length=len(content),
        )

        return message

    def get_messages(self, session_id: str) -> List[ConversationMessage]:
        """Get all messages for a session."""
        session = self.get_session(session_id)
        return session.messages

    def update_status(self, session_id: str, status: CallStatus) -> None:
        """
        Update the call status for a session.

        Args:
            session_id: The session to update.
            status: The new call status.
        """
        session = self.get_session(session_id)
        session.status = status

        if status in (CallStatus.COMPLETED, CallStatus.FAILED, CallStatus.NO_ANSWER):
            session.ended_at = datetime.utcnow()

        logger.info(
            "session_status_updated",
            session_id=session_id,
            status=status.value,
        )

    def end_session(self, session_id: str) -> ConversationSession:
        """
        End a session and mark it as completed.

        Args:
            session_id: The session to end.

        Returns:
            The ended session.
        """
        session = self.get_session(session_id)
        session.status = CallStatus.COMPLETED
        session.ended_at = datetime.utcnow()

        logger.info(
            "session_ended",
            session_id=session_id,
            total_messages=len(session.messages),
            duration_seconds=(
                (session.ended_at - session.started_at).total_seconds()
                if session.ended_at and session.started_at
                else None
            ),
        )

        return session

    def cleanup_expired_sessions(self, max_age_seconds: int = 3600) -> int:
        """
        Remove sessions older than max_age_seconds.

        Args:
            max_age_seconds: Maximum session age in seconds.

        Returns:
            Number of sessions removed.
        """
        now = datetime.utcnow()
        expired = []

        for session_id, session in self._sessions.items():
            age = (now - session.started_at).total_seconds()
            if age > max_age_seconds:
                expired.append(session_id)

        for session_id in expired:
            del self._sessions[session_id]

        if expired:
            logger.info("sessions_cleaned_up", count=len(expired))

        return len(expired)
