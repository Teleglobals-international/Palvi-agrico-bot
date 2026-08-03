"""
Session Manager — DynamoDB-backed call session storage.

Manages active call sessions with conversation state.
Uses in-memory cache for speed, async DynamoDB writes.
"""
import time
import logging
import asyncio
import boto3

from src.config.settings import settings

logger = logging.getLogger(__name__)


class SessionManager:
    def __init__(self):
        dynamodb = boto3.resource("dynamodb", region_name=settings.AWS_REGION)
        self.table = dynamodb.Table(settings.DYNAMODB_SESSION_TABLE)
        self._cache = {}  # In-memory cache for active sessions

    def get_or_create(self, call_sid: str, from_number: str, to_number: str, direction: str) -> dict:
        """Get existing session or create new one. Uses in-memory cache only during active calls."""
        if call_sid in self._cache:
            return self._cache[call_sid]

        # Create new session — start with standard dialect
        # Dialect will be detected from farmer's first spoken response
        user_phone = to_number if direction == "outbound-api" else from_number

        session = {
            "call_sid": call_sid,
            "user_phone": user_phone,
            "from_number": from_number,
            "to_number": to_number,
            "direction": direction,
            "dialect": "marathwada",
            "dialect_locked": False,
            "step": "greet",
            "crop": "",
            "acres": "",
            "wants_cytoboost": "",
            "wants_pump": "",
            "wants_tarpaulin": "",
            "address": "",
            "started_at": int(time.time()),
            "should_close": False,
        }
        self._cache[call_sid] = session
        # Save to DynamoDB in background (don't block the response)
        asyncio.ensure_future(self._save_async(call_sid, session))
        return session

    def update(self, call_sid: str, updates: dict):
        """Update session in memory. DynamoDB save is deferred."""
        if call_sid in self._cache:
            self._cache[call_sid].update(updates)

    def end_session(self, call_sid: str):
        """Mark session as ended. Save final state to DynamoDB."""
        session = self._cache.pop(call_sid, None)
        if session:
            asyncio.ensure_future(self._save_final_async(call_sid, session))

    async def _save_async(self, call_sid: str, session: dict):
        """Save session to DynamoDB asynchronously (non-blocking)."""
        try:
            await asyncio.get_event_loop().run_in_executor(
                None, self._save_sync, call_sid, session
            )
        except Exception as e:
            logger.error(f"[SESSION] Async save error: {e}")

    async def _save_final_async(self, call_sid: str, session: dict):
        """Save final session state to DynamoDB."""
        try:
            await asyncio.get_event_loop().run_in_executor(
                None, self._save_final_sync, call_sid, session
            )
        except Exception as e:
            logger.error(f"[SESSION] Final save error: {e}")

    def _save_sync(self, call_sid: str, session: dict):
        """Synchronous DynamoDB write (run in thread pool)."""
        try:
            self.table.put_item(Item={
                "call_sid": call_sid,
                "session_data": session,
                "ttl": int(time.time()) + 86400,
            })
        except Exception as e:
            logger.error(f"[SESSION] Save error: {e}")

    def _save_final_sync(self, call_sid: str, session: dict):
        """Save final session with completed status."""
        try:
            self.table.put_item(Item={
                "call_sid": call_sid,
                "session_data": session,
                "status": "completed",
                "ttl": int(time.time()) + 86400,
            })
        except Exception as e:
            logger.error(f"[SESSION] Final save error: {e}")
