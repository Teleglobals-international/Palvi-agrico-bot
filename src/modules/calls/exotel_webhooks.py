"""
Exotel Passthru & Status Webhook Routes.

Exotel uses call flows configured in the dashboard (Voicebot Applet for WebSocket streaming).
These routes handle:
- POST /voice/status — Exotel StatusCallback after call completes
- POST /voice/passthru — Exotel Passthru applet webhook (post-Voicebot routing)
"""
import logging
from fastapi import APIRouter, Request
from fastapi.responses import PlainTextResponse

from src.infra.db.session_manager import SessionManager

logger = logging.getLogger(__name__)
router = APIRouter()
session_manager = SessionManager()


@router.post("/status")
async def handle_status(request: Request):
    """
    Handle Exotel StatusCallback.

    Exotel POSTs: CallSid, Status (completed|failed|busy|no-answer),
    RecordingUrl (if enabled), DateUpdated, etc.
    """
    try:
        form = await request.form()
        call_sid = form.get("CallSid", "unknown")
        status = form.get("Status", "")
        recording_url = form.get("RecordingUrl", "")

        logger.info(f"[EXOTEL STATUS] CallSid={call_sid}, Status={status}")

        if recording_url:
            logger.info(f"[EXOTEL STATUS] RecordingUrl={recording_url}")

        # End session if call completed
        if status in ("completed", "failed", "busy", "no-answer"):
            session_manager.end_session(call_sid)

    except Exception as e:
        logger.error(f"[EXOTEL STATUS ERROR] {e}")

    return PlainTextResponse("OK", status_code=200)


@router.get("/passthru")
async def handle_passthru(request: Request):
    """
    Handle Exotel Passthru applet (GET request after Voicebot Applet ends).

    Exotel sends stream metadata: Stream[StreamSID], Stream[Status],
    Stream[Duration], Stream[RecordingUrl], Stream[DisconnectedBy], etc.

    Return 200 to continue flow normally, or route based on session state.
    """
    try:
        params = dict(request.query_params)
        call_sid = params.get("CallSid", "unknown")
        stream_sid = params.get("Stream[StreamSID]", "")
        stream_status = params.get("Stream[Status]", "")
        disconnected_by = params.get("Stream[DisconnectedBy]", "")
        duration = params.get("Stream[Duration]", "")

        logger.info(
            f"[EXOTEL PASSTHRU] CallSid={call_sid}, StreamSid={stream_sid}, "
            f"Status={stream_status}, DisconnectedBy={disconnected_by}, Duration={duration}s"
        )

    except Exception as e:
        logger.error(f"[EXOTEL PASSTHRU ERROR] {e}")

    # Return 200 OK to let the call flow continue to the next applet
    return PlainTextResponse("OK", status_code=200)
