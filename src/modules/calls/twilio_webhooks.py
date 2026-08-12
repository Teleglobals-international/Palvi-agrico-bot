"""
Twilio Webhooks — Status Callback + TwiML endpoints + Webhook conversation mode.

POST /voice/status      — Twilio POSTs call status updates here.
POST /voice/twiml-stream — Returns TwiML to connect to Media Stream WebSocket.
POST /voice/outbound    — First webhook when outbound call is answered (webhook mode).
POST /voice/incoming    — Ongoing conversation turns via <Gather> speech (webhook mode).
"""
import logging
import re
from fastapi import APIRouter, Request
from fastapi.responses import PlainTextResponse, Response

from src.config.settings import settings
from src.infra.db.session_manager import SessionManager
from src.modules.calls.live_broadcast import broadcaster
from src.core.callFlow.state_machine import process_turn
from src.core.callFlow.scripts import GREETING, NO_INPUT_RESPONSE, THANK_YOU
from src.adapters.tts.sarvam_tts import synthesize_speech_to_url

logger = logging.getLogger(__name__)
router = APIRouter()
session_manager = SessionManager()


# ═══════════════════════════════════════════════════════════════
# STREAM MODE — WebSocket Media Streams (paid accounts)
# ═══════════════════════════════════════════════════════════════

@router.post("/twiml-stream")
@router.get("/twiml-stream")
async def twiml_stream():
    """
    Return TwiML that connects the call to our WebSocket Media Stream.
    Twilio fetches this URL when the call is answered.
    """
    twiml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Response>'
        f'<Connect><Stream url="{settings.PUBLIC_WSS_URL}/media-stream" /></Connect>'
        '</Response>'
    )
    logger.info(f"[TWILIO] Serving TwiML: Stream -> {settings.PUBLIC_WSS_URL}/media-stream")
    return Response(content=twiml, media_type="text/xml")


# ═══════════════════════════════════════════════════════════════
# WEBHOOK MODE — <Gather> + <Play> (works on trial accounts)
# ═══════════════════════════════════════════════════════════════

@router.post("/outbound")
async def handle_outbound(request: Request):
    """
    First webhook when outbound call is answered (webhook mode).

    Twilio fetches this URL when the farmer picks up.
    Returns TwiML with greeting audio <Play> + <Gather input="speech">
    to listen for farmer's first response.
    """
    form = await request.form()
    call_sid = form.get("CallSid", "unknown")
    from_number = form.get("From", "")
    to_number = form.get("To", "")

    logger.info(f"[TWILIO WEBHOOK] Outbound call answered: CallSid={call_sid}, To={to_number}")

    # Create session — start at ask_availability (greeting is played now)
    session = session_manager.get_or_create(call_sid, from_number, to_number, "outbound-api")
    session["step"] = "ask_availability"
    session["conversation"] = [{"role": "bot", "text": GREETING}]
    session_manager.update(call_sid, session)

    # Broadcast call started + greeting to live WebSocket
    import asyncio
    asyncio.ensure_future(broadcaster.publish_status(call_sid, "started"))
    asyncio.ensure_future(broadcaster.publish_turn(call_sid, "bot", GREETING, "ask_availability"))

    # Generate greeting audio URL
    audio_url = await synthesize_speech_to_url(GREETING)

    # Return TwiML: Play greeting + Gather speech
    return _build_twiml_response(audio_url, GREETING, call_sid)


@router.post("/incoming")
async def handle_incoming(request: Request):
    """
    Handle ongoing conversation turns (webhook mode).

    Receives SpeechResult from Twilio's <Gather>, processes through
    the state machine, generates TTS audio, returns TwiML with
    <Play> + <Gather> for next turn.
    """
    form = await request.form()
    call_sid = form.get("CallSid", request.query_params.get("call_sid", "unknown"))
    speech_result = form.get("SpeechResult", "")
    no_input = request.query_params.get("no_input", "false")

    logger.info(f"[TWILIO WEBHOOK] Incoming: CallSid={call_sid}, Speech='{speech_result[:50]}', NoInput={no_input}")

    # Get or recover session
    session = session_manager.get_or_create(call_sid, "", "", "outbound-api")

    # Handle no input (farmer didn't speak)
    if no_input == "true" or (not speech_result and no_input != "false"):
        count = int(session.get("no_input_count", 0)) + 1
        session["no_input_count"] = count
        session_manager.update(call_sid, session)

        logger.info(f"[TWILIO WEBHOOK] No input #{count} for CallSid={call_sid}")

        if count >= 3:
            # Too many silent turns — end call
            session_manager.end_session(call_sid)
            return await _respond(THANK_YOU, call_sid, hangup=True)

        return await _respond(NO_INPUT_RESPONSE, call_sid)

    # Reset no-input counter on valid speech
    session["no_input_count"] = 0

    # Process through state machine
    bot_reply = await process_turn(speech_result, session)
    if not bot_reply:
        bot_reply = "सर, जरा पुन्हा सांगा."

    # Track conversation
    if speech_result:
        session["conversation"] = session.get("conversation", [])
        session["conversation"].append({"role": "farmer", "text": speech_result})
    session["conversation"] = session.get("conversation", [])
    session["conversation"].append({"role": "bot", "text": bot_reply})
    session_manager.update(call_sid, session)

    # Broadcast live conversation to frontend WebSocket
    import asyncio
    step = session.get("step", "")
    if speech_result:
        asyncio.ensure_future(broadcaster.publish_turn(call_sid, "farmer", speech_result, step))
    asyncio.ensure_future(broadcaster.publish_turn(call_sid, "bot", bot_reply, step))

    logger.info(f"[TWILIO WEBHOOK] Bot reply: '{bot_reply[:60]}', Step={session.get('step')}")

    # Check if call should end
    if session.get("should_close"):
        session_manager.end_session(call_sid)
        return await _respond(bot_reply, call_sid, hangup=True)

    return await _respond(bot_reply, call_sid)


# ═══════════════════════════════════════════════════════════════
# HELPERS — TwiML generation
# ═══════════════════════════════════════════════════════════════

def _split_for_playback(text: str) -> list:
    """Split long text at natural sentence boundaries for sequential playback."""
    # First check for explicit [[SPLIT]] markers
    if "[[SPLIT]]" in text:
        parts = [p.strip() for p in text.split("[[SPLIT]]") if p.strip()]
        if parts:
            return parts

    # Split at '. ' or '। ' or after complete sentences
    sentences = re.split(r'(?<=\.)\s+|(?<=।)\s+', text)

    # Group short sentences together (aim for ~100-150 chars per chunk)
    result = []
    current = ""
    for s in sentences:
        if len(current) + len(s) < 150:
            current += (" " if current else "") + s
        else:
            if current:
                result.append(current)
            current = s
    if current:
        result.append(current)

    return result if result else [text]


async def _respond(text: str, call_sid: str, hangup: bool = False) -> Response:
    """Generate TwiML response. Serves pre-cached audio as-is, splits only uncached long text."""
    from src.adapters.tts.sarvam_tts import get_cached_audio
    import hashlib

    # Check if the FULL text is already pre-cached (scripted responses)
    text_hash = hashlib.md5(text.encode()).hexdigest()
    is_precached = get_cached_audio(text_hash) is not None

    # Always split on [[SPLIT]] markers regardless of cache status
    if "[[SPLIT]]" in text:
        parts = [p.strip() for p in text.split("[[SPLIT]]") if p.strip()]
    elif is_precached or len(text) <= 150:
        # Serve as single audio — already cached at startup or short enough
        parts = [text]
    else:
        # Long uncached text (Claude response) — split for sequential playback
        parts = _split_for_playback(text)

    # Generate audio URLs for all parts
    play_elements = ""
    for part in parts:
        part = part.strip()
        if part:
            audio_url = await synthesize_speech_to_url(part)
            if audio_url:
                safe_url = audio_url.replace("&", "&amp;")
                play_elements += f'<Play>{safe_url}</Play>'
            else:
                safe_text = part.replace("&", "&amp;").replace("<", "&lt;")
                play_elements += f'<Say language="mr-IN">{safe_text}</Say>'

    if not play_elements:
        safe_text = text.replace("&", "&amp;").replace("<", "&lt;")
        play_elements = f'<Say language="mr-IN">{safe_text}</Say>'

    base_url = settings.BASE_URL.rstrip("/")
    action = f"{base_url}/api/voice/incoming?call_sid={call_sid}"
    no_input_url = f"{base_url}/api/voice/incoming?call_sid={call_sid}&amp;no_input=true"

    if hangup:
        twiml = f'<?xml version="1.0" encoding="UTF-8"?><Response>{play_elements}<Hangup/></Response>'
    else:
        # Determine timeout based on audio length (longer responses need more time)
        timeout = "15" if len(text) > 200 else "10"
        twiml = (
            '<?xml version="1.0" encoding="UTF-8"?><Response>'
            f'{play_elements}'
            f'<Gather input="speech" action="{action}" method="POST" speechTimeout="4" language="mr-IN" timeout="{timeout}">'
            '</Gather>'
            f'<Redirect method="POST">{no_input_url}</Redirect></Response>'
        )

    return Response(content=twiml, media_type="text/xml")


def _build_twiml_response(
    audio_url: str, text: str, call_sid: str, hangup: bool = False
) -> Response:
    """Build TwiML XML response (used for greeting/short responses)."""
    base_url = settings.BASE_URL.rstrip("/")
    action = f"{base_url}/api/voice/incoming?call_sid={call_sid}"
    no_input_url = f"{base_url}/api/voice/incoming?call_sid={call_sid}&amp;no_input=true"

    # Build Play or Say element
    if audio_url:
        safe_url = audio_url.replace("&", "&amp;")
        play_element = f'<Play>{safe_url}</Play>'
    else:
        # Fallback to <Say> if TTS fails
        safe_text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        play_element = f'<Say language="mr-IN">{safe_text}</Say>'

    if hangup:
        twiml = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            f'<Response>{play_element}<Hangup/></Response>'
        )
    else:
        twiml = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<Response>'
            f'{play_element}'
            f'<Gather input="speech" action="{action}" method="POST" '
            f'speechTimeout="3" language="mr-IN" timeout="10">'
            '</Gather>'
            f'<Redirect method="POST">{no_input_url}</Redirect>'
            '</Response>'
        )

    return Response(content=twiml, media_type="text/xml")


# ═══════════════════════════════════════════════════════════════
# STATUS CALLBACK — shared by both modes
# ═══════════════════════════════════════════════════════════════

@router.post("/status")
async def handle_status(request: Request):
    """
    Handle Twilio StatusCallback.

    Twilio POSTs: CallSid, CallStatus (completed|busy|no-answer|failed),
    CallDuration, Timestamp, etc.
    """
    try:
        form = await request.form()
        call_sid = form.get("CallSid", "unknown")
        call_status = form.get("CallStatus", "")
        duration = form.get("CallDuration", "")

        logger.info(f"[TWILIO STATUS] CallSid={call_sid}, Status={call_status}, Duration={duration}s")

        # End session if call completed
        if call_status in ("completed", "failed", "busy", "no-answer"):
            import asyncio
            asyncio.ensure_future(broadcaster.publish_status(call_sid, "ended"))
            session_manager.end_session(call_sid)

    except Exception as e:
        logger.error(f"[TWILIO STATUS ERROR] {e}")

    return PlainTextResponse("OK", status_code=200)
