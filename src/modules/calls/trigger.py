"""
Outbound Call Trigger API — Exotel.

POST /call/initiate with {"phone_number": "9876543210"}

Uses Exotel's Voice v1 API to connect a customer to a call flow
containing the Voicebot Applet (WebSocket streaming).
"""
import logging
import httpx
from fastapi import APIRouter
from pydantic import BaseModel

from src.config.settings import settings

logger = logging.getLogger(__name__)
router = APIRouter()


class CallRequest(BaseModel):
    phone_number: str
    dialect: str = "marathwada"


@router.post("/initiate")
async def initiate_call(request: CallRequest):
    """
    Initiate an outbound call to a farmer via Exotel.

    Exotel calls the farmer's number and connects them to the call flow
    (App) containing the Voicebot Applet, which opens a WebSocket to our server.
    """
    phone = request.phone_number.strip().replace(" ", "").replace("-", "")

    # Exotel expects numbers with leading 0 for mobile (e.g., 09876543210)
    # or with country code for international
    if phone.startswith("+91"):
        phone = "0" + phone[3:]  # +919876543210 -> 09876543210
    elif phone.startswith("91") and len(phone) == 12:
        phone = "0" + phone[2:]  # 919876543210 -> 09876543210
    elif not phone.startswith("0") and len(phone) == 10:
        phone = "0" + phone  # 9876543210 -> 09876543210

    if len(phone) < 11:
        return {"error": "Invalid phone number"}, 400

    dialect = request.dialect.lower()
    if dialect not in ("standard", "marathwada", "vidarbha"):
        dialect = "marathwada"

    try:
        # Exotel API: Connect customer to an App (call flow)
        # POST https://<api_key>:<api_token>@<subdomain>/v1/Accounts/<sid>/Calls/connect
        url = (
            f"https://{settings.EXOTEL_SUBDOMAIN}"
            f"/v1/Accounts/{settings.EXOTEL_ACCOUNT_SID}/Calls/connect.json"
        )

        # The Url parameter points to the call flow (app) containing Voicebot Applet
        app_url = (
            f"http://my.exotel.com/{settings.EXOTEL_ACCOUNT_SID}"
            f"/exoml/start_voice/{settings.EXOTEL_APP_ID}"
        )

        payload = {
            "From": phone,
            "CallerId": settings.EXOTEL_CALLER_ID,
            "Url": app_url,
            "CallType": "trans",  # Transactional call
            "StatusCallback": f"{settings.BASE_URL}/voice/status",
            "CustomField": f"dialect={dialect}",
        }

        logger.info(f"[EXOTEL] Initiating call: From={phone}, CallerId={settings.EXOTEL_CALLER_ID}, AppUrl={app_url}")

        async with httpx.AsyncClient() as client:
            response = await client.post(
                url,
                data=payload,
                auth=(settings.EXOTEL_API_KEY, settings.EXOTEL_API_TOKEN),
                timeout=30.0,
            )

        if response.status_code == 200:
            result = response.json()
            call_data = result.get("Call", {})
            call_sid = call_data.get("Sid", "unknown")

            logger.info(f"[CALL INITIATED] SID={call_sid}, To={phone}, Dialect={dialect}")
            return {
                "message": "Call initiated via Exotel",
                "call_sid": call_sid,
                "to": phone,
                "dialect": dialect,
            }
        else:
            error_msg = response.text
            logger.error(f"[EXOTEL API ERROR] Status={response.status_code}, Body={error_msg}")
            return {"error": f"Exotel API error: {response.status_code}", "details": error_msg}, 500

    except Exception as e:
        logger.error(f"[CALL ERROR] {e}")
        return {"error": str(e)}, 500
