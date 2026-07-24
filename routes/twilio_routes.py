"""Twilio Voice Webhook — with Sarvam TTS."""
import logging
import hashlib
import time
from fastapi import APIRouter, Request
from fastapi.responses import Response

from app.config import settings
from services.session_manager import SessionManager
from services.sarvam_tts import synthesize_speech_to_url, get_cached_audio
from orchestrator.graph import process_turn

logger = logging.getLogger(__name__)
router = APIRouter()
session_manager = SessionManager()


@router.post("/incoming")
async def handle_voice(request: Request):
    """Handle all Twilio voice webhooks."""
    try:
        form = await request.form()
        call_sid = form.get("CallSid", "unknown")
        from_number = form.get("From", "")
        to_number = form.get("To", "")
        speech_result = form.get("SpeechResult", "")
        call_status = form.get("CallStatus", "")
        direction = form.get("Direction", "outbound-api")
        no_input = request.query_params.get("no_input", "false")
        dialect = request.query_params.get("dialect", "")

        logger.info(f"[VOICE] CallSid={call_sid}, From={from_number}, Speech={speech_result or 'None'}")

        if call_status in ("completed", "busy", "no-answer", "failed", "canceled"):
            return Response(content='<?xml version="1.0" encoding="UTF-8"?><Response></Response>', media_type="text/xml")

        session = session_manager.get_or_create(call_sid, from_number, to_number, direction)

        if dialect and dialect in ("marathwada", "vidarbha"):
            session["dialect"] = dialect
            session_manager.update(call_sid, session)

        from orchestrator.graph import get_responses
        responses = get_responses(session.get("dialect", "marathwada"))

        if no_input == "true":
            count = int(session.get("no_input_count", 0)) + 1
            session["no_input_count"] = count
            session_manager.update(call_sid, session)
            if count >= 3:
                return await _respond(responses["thank_you"], call_sid, hangup=True)
            return await _respond(responses["no_input"], call_sid)

        session["no_input_count"] = 0
        user_text = speech_result or ""

        t_start = time.time()
        bot_reply = await process_turn(user_text, session)
        t_claude = time.time()

        if not bot_reply:
            bot_reply = responses["not_understood"]

        # Track conversation
        if "conversation" not in session:
            session["conversation"] = []
        if user_text:
            session["conversation"].append({"role": "farmer", "text": user_text})
        session["conversation"].append({"role": "bot", "text": bot_reply})
        session_manager.update(call_sid, session)

        logger.info(f"[BOT] Reply: '{bot_reply[:60]}'")
        logger.info(f"[TIMING] Claude: {t_claude - t_start:.2f}s")

        if session.get("should_close"):
            session_manager.end_session(call_sid)
            resp = await _respond(bot_reply, call_sid, hangup=True)
            logger.info(f"[TIMING] Total turn: {time.time() - t_start:.2f}s")
            return resp

        resp = await _respond(bot_reply, call_sid)
        logger.info(f"[TIMING] Total turn: {time.time() - t_start:.2f}s (Claude={t_claude - t_start:.2f}s, TTS={time.time() - t_claude:.2f}s)")
        return resp

    except Exception as e:
        logger.error(f"[ERROR] {e}")
        return Response(
            content='<?xml version="1.0" encoding="UTF-8"?><Response><Say language="hi-IN">माफ करा, तांत्रिक अडचण आली.</Say></Response>',
            media_type="text/xml"
        )


@router.post("/outbound")
async def handle_outbound(request: Request):
    return await handle_voice(request)


@router.post("/status")
async def handle_status():
    return Response(content="OK", status_code=200)


async def _respond(text: str, call_sid: str, hangup: bool = False) -> Response:
    """Generate TwiML. Auto-splits long text into multiple Play elements."""
    try:
        base_url = settings.BASE_URL.rstrip("/")

        # Check for explicit multi-part response
        if text.startswith("[[MULTI]]"):
            parts = text.replace("[[MULTI]]", "").split("[[SPLIT]]")
        else:
            # Check if already cached as single audio (pre-cached responses)
            import hashlib as hl
            text_hash = hl.md5(text.encode()).hexdigest()
            if get_cached_audio(text_hash):
                # Already cached — use as single audio, no splitting
                parts = [text]
            elif len(text) > 120:
                # Not cached and long — split for reliable playback
                parts = _split_long_text(text)
            else:
                parts = [text]

        # Generate audio for all parts (in parallel for speed)
        import asyncio
        audio_tasks = []
        for part in parts:
            part = part.strip()
            if part:
                audio_tasks.append(synthesize_speech_to_url(part))

        urls = await asyncio.gather(*audio_tasks) if audio_tasks else []

        play_elements = ""
        for url in urls:
            if url:
                safe_url = url.replace("&", "&amp;")
                play_elements += f"<Play>{safe_url}</Play>"

        # Determine timeout based on response length
        timeout = "20" if len(text) > 300 else "15" if len(text) > 200 else "10" if len(text) > 100 else "7"

        if not play_elements:
            safe_text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            play_elements = f'<Say language="mr-IN">{safe_text}</Say>'

        if hangup:
            twiml = f'<?xml version="1.0" encoding="UTF-8"?><Response>{play_elements}<Hangup/></Response>'
        else:
            action = f"{base_url}/voice/incoming?call_sid={call_sid}"
            no_input = f"{base_url}/voice/incoming?call_sid={call_sid}&amp;no_input=true"
            twiml = (
                '<?xml version="1.0" encoding="UTF-8"?><Response>'
                f'<Gather input="speech" action="{action}" method="POST" speechTimeout="2" speechModel="phone_call" enhanced="true" language="mr-IN" timeout="{timeout}">'
                f'{play_elements}</Gather>'
                f'<Redirect method="POST">{no_input}</Redirect></Response>'
            )

        return Response(content=twiml, media_type="text/xml")

    except Exception as e:
        logger.error(f"[RESPOND ERROR] {e}")
        # Fallback TwiML so Twilio doesn't show "application error"
        base_url = settings.BASE_URL.rstrip("/")
        fallback_action = f"{base_url}/voice/incoming?call_sid={call_sid}"
        fallback = (
            '<?xml version="1.0" encoding="UTF-8"?><Response>'
            f'<Gather input="speech" action="{fallback_action}" method="POST" speechTimeout="2" language="mr-IN" timeout="10">'
            '<Say language="mr-IN">सर, जरा थांबा.</Say></Gather></Response>'
        )
        return Response(content=fallback, media_type="text/xml")


def _split_long_text(text: str) -> list:
    """Split long text into chunks at natural sentence boundaries."""
    # Split at periods, commas followed by space, or 'अन्'
    import re
    # Split at '. ' or ', अन्' or ', तसंच' or '. तर'
    sentences = re.split(r'(?<=\.)\s+|(?<=,)\s+(?=अन्)|(?<=,)\s+(?=तसंच)', text)

    # If still too long, split at any comma
    result = []
    for s in sentences:
        if len(s) > 120:
            sub_parts = s.split(', ')
            current = ""
            for sp in sub_parts:
                if len(current) + len(sp) < 100:
                    current += (", " if current else "") + sp
                else:
                    if current:
                        result.append(current)
                    current = sp
            if current:
                result.append(current)
        else:
            result.append(s)

    return [r.strip() for r in result if r.strip()]
