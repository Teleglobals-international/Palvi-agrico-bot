"""
Custom exception classes for the application.
"""

from typing import Optional, Any


class BaseAppException(Exception):
    """Base exception for the application."""

    def __init__(
        self,
        message: str,
        status_code: int = 500,
        detail: Optional[Any] = None,
    ):
        self.message = message
        self.status_code = status_code
        self.detail = detail
        super().__init__(self.message)


class ExotelConnectionError(BaseAppException):
    """Raised when Exotel connection fails."""

    def __init__(self, message: str = "Failed to connect to Exotel"):
        super().__init__(message=message, status_code=502)


class ExotelWebhookError(BaseAppException):
    """Raised when Exotel webhook processing fails."""

    def __init__(self, message: str = "Webhook processing failed"):
        super().__init__(message=message, status_code=400)


class AgentNotFoundError(BaseAppException):
    """Raised when requested agent/industry is not found."""

    def __init__(self, agent_type: str):
        super().__init__(
            message=f"Agent not found for industry: {agent_type}",
            status_code=404,
        )


class LLMServiceError(BaseAppException):
    """Raised when LLM service fails."""

    def __init__(self, message: str = "LLM service unavailable"):
        super().__init__(message=message, status_code=503)


class ConversationNotFoundError(BaseAppException):
    """Raised when conversation session is not found."""

    def __init__(self, session_id: str):
        super().__init__(
            message=f"Conversation not found: {session_id}",
            status_code=404,
        )


class RateLimitExceededError(BaseAppException):
    """Raised when rate limit is exceeded."""

    def __init__(self):
        super().__init__(
            message="Rate limit exceeded. Please try again later.",
            status_code=429,
        )



