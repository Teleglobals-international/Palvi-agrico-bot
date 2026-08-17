"""
Exotel API Client - handles outbound call initiation.
Uses the same pattern as the agri domain agent.
Routes outbound calls through the Voicebot Applet flow.
"""

import json
from typing import Any, Dict, Optional

import httpx
import structlog
from tenacity import retry, stop_after_attempt, wait_exponential

from app.config import get_settings
from app.core.exceptions import ExotelConnectionError
from app.shared.models import IndustryType

logger = structlog.get_logger(__name__)


class ExotelClient:
    """
    Client for interacting with Exotel REST API.
    Shared credentials are used across all industry agents.
    """

    def __init__(self):
        settings = get_settings()
        self._account_sid = settings.exotel_account_sid
        self._api_key = settings.exotel_api_key
        self._api_token = settings.exotel_api_token
        self._subdomain = settings.exotel_subdomain
        self._caller_id = settings.exotel_caller_id
        self._app_id = settings.exotel_app_id
        self._base_url = f"https://{self._subdomain}/v1/Accounts/{self._account_sid}"
        self._app_base_url = settings.base_url

    def _normalize_phone(self, phone: str) -> str:
        """Normalize phone number to Exotel format (0XXXXXXXXXX)."""
        phone = phone.strip().replace(" ", "").replace("-", "")

        if phone.startswith("+91"):
            phone = "0" + phone[3:]
        elif phone.startswith("91") and len(phone) == 12:
            phone = "0" + phone[2:]
        elif not phone.startswith("0") and len(phone) == 10:
            phone = "0" + phone

        return phone

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True,
    )
    async def initiate_outbound_call(
        self,
        to_number: str,
        industry: IndustryType,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Initiate an outbound call via Exotel API.
        Routes through the Voicebot Applet flow (same as agri agent).

        Args:
            to_number: Destination phone number.
            industry: Industry type for routing to correct agent.
            context: Optional context passed as custom field.

        Returns:
            Exotel API response containing call SID and status.

        Raises:
            ExotelConnectionError: If the API call fails.
        """
        url = f"{self._base_url}/Calls/connect.json"

        # Normalize phone number
        phone = self._normalize_phone(to_number)

        if len(phone) < 11:
            raise ExotelConnectionError(f"Invalid phone number: {to_number}")

        # The Url parameter points to the Exotel App containing the Voicebot Applet
        # This is what makes it route through WebSocket instead of just bridging
        app_url = (
            f"http://my.exotel.com/{self._account_sid}"
            f"/exoml/start_voice/{self._app_id}"
        )

        # Custom field carries the industry type
        custom_field = f"industry={industry.value}"
        if context:
            custom_field += f"&context={json.dumps(context)}"

        payload = {
            "From": phone,
            "CallerId": self._caller_id,
            "Url": app_url,
            "CallType": "trans",
            "CustomField": custom_field,
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    url,
                    data=payload,
                    auth=(self._api_key, self._api_token),
                )

                if response.status_code not in (200, 201):
                    logger.error(
                        "exotel_call_initiation_failed",
                        status_code=response.status_code,
                        response_body=response.text[:200],
                    )
                    raise ExotelConnectionError(
                        f"Exotel API returned {response.status_code}: {response.text[:100]}"
                    )

                result = response.json()
                call_sid = result.get("Call", {}).get("Sid", "unknown")

                logger.info(
                    "outbound_call_initiated",
                    call_sid=call_sid,
                    to_number=phone[:6] + "****",
                    industry=industry.value,
                )
                return result

        except httpx.RequestError as exc:
            logger.error("exotel_connection_error", error=str(exc))
            raise ExotelConnectionError(f"Failed to connect to Exotel: {str(exc)}")

    async def get_call_details(self, call_sid: str) -> Dict[str, Any]:
        """Get details of a specific call from Exotel."""
        url = f"{self._base_url}/Calls/{call_sid}.json"

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.get(
                    url,
                    auth=(self._api_key, self._api_token),
                )

                if response.status_code != 200:
                    raise ExotelConnectionError(
                        f"Failed to get call details: {response.status_code}"
                    )

                return response.json()

        except httpx.RequestError as exc:
            logger.error("exotel_get_call_failed", error=str(exc))
            raise ExotelConnectionError(str(exc))

    async def end_call(self, call_sid: str) -> Dict[str, Any]:
        """End an active call via Exotel API."""
        url = f"{self._base_url}/Calls/{call_sid}.json"

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.post(
                    url,
                    data={"Status": "completed"},
                    auth=(self._api_key, self._api_token),
                )
                return response.json()

        except httpx.RequestError as exc:
            logger.error("exotel_end_call_failed", error=str(exc))
            raise ExotelConnectionError(str(exc))
