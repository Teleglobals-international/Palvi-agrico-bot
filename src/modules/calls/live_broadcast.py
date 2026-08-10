"""
Live Call Broadcast — WebSocket pub/sub for real-time conversation display.

The Exotel WS handler publishes conversation events here.
Frontend clients subscribe via /ws/live/{call_sid} to receive them in real-time.
"""
import asyncio
import json
import logging
import time
from typing import Dict, Set
from fastapi import WebSocket

logger = logging.getLogger(__name__)


class LiveCallBroadcaster:
    """Manages WebSocket subscribers for live call conversation streaming."""

    def __init__(self):
        # call_sid -> set of connected frontend WebSocket clients
        self._subscribers: Dict[str, Set[WebSocket]] = {}
        # call_sid -> list of conversation events (for late-joining clients)
        self._history: Dict[str, list] = {}

    def subscribe(self, call_sid: str, ws: WebSocket):
        """Add a frontend client to a call's broadcast channel."""
        if call_sid not in self._subscribers:
            self._subscribers[call_sid] = set()
        self._subscribers[call_sid].add(ws)
        logger.info(f"[LIVE] Client subscribed to {call_sid} (total: {len(self._subscribers[call_sid])})")

    def unsubscribe(self, call_sid: str, ws: WebSocket):
        """Remove a frontend client from a call's broadcast channel."""
        if call_sid in self._subscribers:
            self._subscribers[call_sid].discard(ws)
            if not self._subscribers[call_sid]:
                del self._subscribers[call_sid]
            logger.info(f"[LIVE] Client unsubscribed from {call_sid}")

    def get_history(self, call_sid: str) -> list:
        """Get conversation history for late-joining clients."""
        return self._history.get(call_sid, [])

    async def publish(self, call_sid: str, event: dict):
        """Broadcast a conversation event to all subscribers of a call.

        Called by the Exotel WS handler whenever a new turn happens.
        """
        # Add timestamp
        event["timestamp"] = time.time()

        # Store in history
        if call_sid not in self._history:
            self._history[call_sid] = []
        self._history[call_sid].append(event)

        # Broadcast to subscribers
        subscribers = self._subscribers.get(call_sid, set()).copy()
        if not subscribers:
            return

        message = json.dumps(event)
        dead_connections = set()

        for ws in subscribers:
            try:
                await ws.send_text(message)
            except Exception:
                dead_connections.add(ws)

        # Clean up dead connections
        for ws in dead_connections:
            self.unsubscribe(call_sid, ws)

    async def publish_status(self, call_sid: str, status: str, **extra):
        """Publish a call status update (started, ended, etc.)."""
        event = {"type": "status", "status": status, "call_sid": call_sid, **extra}
        await self.publish(call_sid, event)

    async def publish_turn(self, call_sid: str, role: str, text: str, step: str = ""):
        """Publish a conversation turn (farmer said X, bot replied Y)."""
        event = {"type": "turn", "role": role, "text": text, "step": step}
        await self.publish(call_sid, event)

    def cleanup(self, call_sid: str):
        """Clean up a call's data after it ends (called after a delay)."""
        self._history.pop(call_sid, None)
        self._subscribers.pop(call_sid, None)


# Global singleton
broadcaster = LiveCallBroadcaster()
