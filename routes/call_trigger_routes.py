"""
Outbound Call Trigger API.

POST /call/initiate with {"phone_number": "9876543210"}
"""
import logging
from fastapi import APIRouter
from pydantic import BaseModel
from twilio.rest import Client

from app.config import settings

logger = logging.getLogger(__name__)
router = APIRouter()


class CallRequest(BaseModel):
    phone_number: str
    dialect: str = "marathwada"
    mode: str = "webhook"  # "webhook" (HTTP, reliable) or "stream" (WebSocket, experimental)


@router.post("/initiate")
async def initiate_call(request: CallRequest):
    """Initiate an outbound call to a farmer."""
    phone = request.phone_number.strip().replace(" ", "").replace("-", "")
    if not phone.startswith("+"):
        phone = "+91" + phone

    if len(phone) < 12:
        return {"error": "Invalid phone number"}, 400

    dialect = request.dialect.lower()
    if dialect not in ("standard", "marathwada", "vidarbha"):
        dialect = "marathwada"

    mode = request.mode.lower()

    try:
        client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)

        if mode == "stream":
            # WebSocket Media Streams mode (faster ~1-2s latency)
            wss_url = settings.PUBLIC_WSS_URL
            twiml = (
                '<?xml version="1.0" encoding="UTF-8"?>'
                '<Response>'
                f'<Connect><Stream url="{wss_url}/media-stream" /></Connect>'
                '</Response>'
            )
            call = client.calls.create(
                to=phone,
                from_=settings.TWILIO_FROM_NUMBER,
                twiml=twiml,
                status_callback=f"{settings.BASE_URL}/voice/status",
                status_callback_event=["completed", "busy", "no-answer", "failed"],
            )
            logger.info(f"[CALL INITIATED] SID={call.sid}, To={phone}, Mode=stream")
            return {"message": "Call initiated (WebSocket)", "call_sid": call.sid, "to": phone, "mode": "stream"}
        else:
            # HTTP Webhook mode (fallback, ~4s latency)
            call = client.calls.create(
                to=phone,
                from_=settings.TWILIO_FROM_NUMBER,
                url=f"{settings.BASE_URL}/voice/outbound?dialect={dialect}",
                status_callback=f"{settings.BASE_URL}/voice/status",
                status_callback_event=["completed", "busy", "no-answer", "failed"],
            )
            logger.info(f"[CALL INITIATED] SID={call.sid}, To={phone}, Mode=webhook")
            return {"message": "Call initiated (Webhook)", "call_sid": call.sid, "to": phone, "mode": "webhook", "dialect": dialect}

    except Exception as e:
        logger.error(f"[CALL ERROR] {e}")
        return {"error": str(e)}, 500
