"""
Outbound Call Trigger API — Twilio (Primary).

POST /call/initiate with {"phone_number": "9876543210", "dialect": "marathwada", "mode": "webhook"}

Supports two modes:
- "webhook" (default): Uses TwiML <Gather> for speech + <Play> for audio.
  Works on Twilio trial accounts (no Media Streams needed).
- "stream": Uses WebSocket Media Streams for real-time bidirectional audio.
  Requires Twilio paid account with Media Streams enabled.
"""
import logging
from fastapi import APIRouter
from pydantic import BaseModel

from twilio.rest import Client

from src.config.settings import settings

logger = logging.getLogger(__name__)
router = APIRouter()

# Twilio client (initialized once)
twilio_client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)


class CallRequest(BaseModel):
    phone_number: str
    dialect: str = "marathwada"
    mode: str = "webhook"


@router.post("/initiate")
async def initiate_call(request: CallRequest):
    """
    Initiate an outbound call to a farmer via Twilio.

    Mode "webhook": Twilio fetches /voice/outbound when call is answered,
    uses <Gather input="speech"> + <Play> for turn-based conversation.

    Mode "stream": Twilio connects to WebSocket Media Stream for
    real-time bidirectional audio (requires paid account).
    """
    phone = request.phone_number.strip().replace(" ", "").replace("-", "")

    # Twilio expects E.164 format: +91XXXXXXXXXX for Indian numbers
    if phone.startswith("+91"):
        pass  # Already in correct format
    elif phone.startswith("91") and len(phone) == 12:
        phone = "+" + phone  # 919876543210 -> +919876543210
    elif phone.startswith("0") and len(phone) == 11:
        phone = "+91" + phone[1:]  # 09876543210 -> +919876543210
    elif len(phone) == 10:
        phone = "+91" + phone  # 9876543210 -> +919876543210
    else:
        return {"error": "Invalid phone number format"}, 400

    if len(phone) != 13:  # +91 + 10 digits
        return {"error": "Invalid phone number"}, 400

    dialect = request.dialect.lower()
    if dialect not in ("standard", "marathwada", "vidarbha"):
        dialect = "marathwada"

    try:
        if request.mode == "webhook":
            # Webhook mode: Twilio fetches TwiML from /voice/outbound
            # Works on trial accounts — uses <Gather> + <Play>
            call = twilio_client.calls.create(
                to=phone,
                from_=settings.TWILIO_FROM_NUMBER,
                url=f"{settings.BASE_URL}/voice/outbound",
                status_callback=f"{settings.BASE_URL}/voice/status",
                status_callback_event=["completed", "failed", "busy", "no-answer"],
            )

            logger.info(f"[TWILIO] Webhook call initiated: SID={call.sid}, To={phone}, Dialect={dialect}")
            return {
                "message": "Call initiated via Twilio (webhook mode)",
                "call_sid": call.sid,
                "to": phone,
                "dialect": dialect,
                "mode": "webhook",
            }

        elif request.mode == "stream":
            # Stream mode: WebSocket Media Streams (requires paid account)
            twiml_url = f"{settings.BASE_URL}/voice/twiml-stream"

            call = twilio_client.calls.create(
                to=phone,
                from_=settings.TWILIO_FROM_NUMBER,
                url=twiml_url,
            )

            logger.info(f"[TWILIO] Stream call initiated: SID={call.sid}, To={phone}, Dialect={dialect}")
            return {
                "message": "Call initiated via Twilio (stream mode)",
                "call_sid": call.sid,
                "to": phone,
                "dialect": dialect,
                "mode": "stream",
            }

        else:
            return {"error": f"Unsupported mode: {request.mode}. Use 'webhook' or 'stream'."}, 400

    except Exception as e:
        logger.error(f"[TWILIO CALL ERROR] {e}")
        return {"error": str(e)}, 500
