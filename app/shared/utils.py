"""
Shared utility functions.
"""

import uuid
from datetime import datetime
from typing import Optional

import structlog

logger = structlog.get_logger(__name__)


def generate_session_id() -> str:
    """Generate a unique session ID."""
    return str(uuid.uuid4())


def get_current_timestamp() -> datetime:
    """Get current UTC timestamp."""
    return datetime.utcnow()


def sanitize_phone_number(phone: str) -> str:
    """
    Sanitize and normalize a phone number.

    Args:
        phone: Raw phone number string.

    Returns:
        Normalized phone number with + prefix.
    """
    cleaned = "".join(c for c in phone if c.isdigit() or c == "+")
    if not cleaned.startswith("+"):
        cleaned = f"+{cleaned}"
    return cleaned


def truncate_text(text: str, max_length: int = 500) -> str:
    """Truncate text to max length with ellipsis."""
    if len(text) <= max_length:
        return text
    return text[:max_length - 3] + "..."


def mask_sensitive_data(data: str, visible_chars: int = 4) -> str:
    """Mask sensitive data, showing only last N characters."""
    if len(data) <= visible_chars:
        return "*" * len(data)
    return "*" * (len(data) - visible_chars) + data[-visible_chars:]
