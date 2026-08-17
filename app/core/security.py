"""
Security utilities: rate limiting and request validation.
"""

import time
from typing import Dict
from collections import defaultdict

import structlog

from app.core.exceptions import RateLimitExceededError

logger = structlog.get_logger(__name__)


class InMemoryRateLimiter:
    """
    Simple in-memory rate limiter using sliding window.
    For production with multiple instances, use Redis-based rate limiting.
    """

    def __init__(self, max_requests: int = 60, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._requests: Dict[str, list] = defaultdict(list)

    def check_rate_limit(self, identifier: str) -> bool:
        """
        Check if the identifier has exceeded the rate limit.

        Args:
            identifier: Unique identifier (IP, API key, etc.)

        Returns:
            True if within limit.

        Raises:
            RateLimitExceededError if limit exceeded.
        """
        now = time.time()
        window_start = now - self.window_seconds

        # Clean old entries
        self._requests[identifier] = [
            ts for ts in self._requests[identifier] if ts > window_start
        ]

        if len(self._requests[identifier]) >= self.max_requests:
            logger.warning("rate_limit_exceeded", identifier=identifier)
            raise RateLimitExceededError()

        self._requests[identifier].append(now)
        return True


# Global rate limiter instance
rate_limiter = InMemoryRateLimiter()
