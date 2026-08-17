"""
Calling endpoints - Exotel webhook callbacks and outbound call initiation.
"""

from typing import Any, Dict

import structlog
from fastapi import APIRouter, Depends, Form, Query, Request, WebSocket

from app.features.agents.registry import AgentRegistry
from app.features.calling.exotel_client import ExotelClient
from app.features.calling.webhook_handler import WebhookHandler
from app.features.calling.websocket_handler import WebSocketHandler
from app.features.conversation import ConversationManager
from app.features.llm import LLMService
from app.shared.models import IndustryType, OutboundCallRequest

logger = structlog.get_logger(__name__)

router = APIRouter()

# --- Dependency Injection ---


def get_services():
    """Create and return service instances."""
    registry = AgentRegistry()
    conversation_manager = ConversationManager()
    llm_service = LLMService()
    exotel_client = ExotelClient()
    webhook_handler = WebhookHandler(registry, conversation_manager, llm_service)
    websocket_handler = WebSocketHandler(registry, conversation_manager, llm_service)

    return {
        "registry": registry,
        "conversations": conversation_manager,
        "llm": llm_service,
        "exotel": exotel_client,
        "webhook": webhook_handler,
        "websocket": websocket_handler,
    }


# Global service instances (initialized once)
_services = None


def get_initialized_services():
    """Get or create singleton service instances."""
    global _services
    if _services is None:
        _services = get_services()
    return _services


# --- Outbound Call Endpoints ---


@router.post("/outbound")
async def initiate_outbound_call(request: OutboundCallRequest):
    """
    Initiate an outbound call to a customer.

    The call will be routed to the specified industry agent.
    """
    services = get_initialized_services()

    result = await services["exotel"].initiate_outbound_call(
        to_number=request.to_number,
        industry=request.industry,
        context=request.context,
    )

    # Pre-create session for outbound call
    call_sid = result.get("Call", {}).get("Sid")
    if call_sid:
        from app.shared.models import CallDirection

        services["conversations"].create_session(
            industry=request.industry,
            direction=CallDirection.OUTBOUND,
            call_sid=call_sid,
            callee_number=request.to_number,
            metadata={"context": request.context, "request_metadata": request.metadata},
        )

    return {
        "success": True,
        "call_sid": call_sid,
        "industry": request.industry.value,
        "to_number": request.to_number[:6] + "****",
    }


# --- Webhook Endpoints (Exotel calls these) ---


@router.post("/webhook/incoming/{industry}")
async def webhook_incoming_call(
    industry: IndustryType,
    request: Request,
):
    """
    Webhook endpoint for incoming (inbound) calls from Exotel.
    Exotel POSTs here when a new call arrives.
    """
    services = get_initialized_services()

    # Parse form data (Exotel sends as form-encoded)
    form_data = await request.form()
    webhook_data = dict(form_data)

    result = await services["webhook"].handle_incoming_call(
        industry=industry,
        webhook_data=webhook_data,
    )

    return result


@router.post("/webhook/answer/{industry}")
async def webhook_answer_callback(
    industry: IndustryType,
    request: Request,
):
    """
    Webhook endpoint for call answer events (outbound call picked up).
    Exotel POSTs here when the callee answers.
    """
    services = get_initialized_services()

    form_data = await request.form()
    webhook_data = dict(form_data)

    result = await services["webhook"].handle_answer_callback(
        industry=industry,
        webhook_data=webhook_data,
    )

    return result


@router.post("/webhook/status")
async def webhook_status_callback(request: Request):
    """
    Webhook endpoint for call status updates (ringing, completed, failed).
    Exotel POSTs status changes here.
    """
    services = get_initialized_services()

    form_data = await request.form()
    webhook_data = dict(form_data)

    result = await services["webhook"].handle_status_callback(
        webhook_data=webhook_data,
    )

    return result


# --- User Input (During Active Call) ---


@router.post("/session/{session_id}/message")
async def handle_call_message(
    session_id: str,
    user_message: str = Form(...),
):
    """
    Process user input during an active call session.
    Used when speech-to-text is handled externally and text is posted here.
    """
    services = get_initialized_services()

    result = await services["webhook"].handle_user_input(
        session_id=session_id,
        user_message=user_message,
    )

    return result


# --- WebSocket Endpoints ---


@router.websocket("/ws/{industry}")
async def websocket_endpoint(
    websocket: WebSocket,
    industry: IndustryType,
):
    """
    WebSocket endpoint for real-time audio streaming with Exotel.
    Industry-specific routing via URL path.
    """
    services = get_initialized_services()

    await services["websocket"].handle_connection(
        websocket=websocket,
        industry=industry,
    )


@router.websocket("/media-stream")
async def media_stream_endpoint(
    websocket: WebSocket,
):
    """
    Generic WebSocket endpoint (matches agri agent pattern).
    Exotel Voicebot Applet connects here.
    Industry is determined from custom_parameters in the 'start' event,
    defaults to real_estate if not specified.
    """
    services = get_initialized_services()

    # Default to real_estate; the handler will parse custom_parameters
    # to determine the actual industry from the call's CustomField
    await services["websocket"].handle_connection(
        websocket=websocket,
        industry=IndustryType.REAL_ESTATE,
    )


# --- Session Management ---


@router.get("/session/{session_id}")
async def get_session_details(session_id: str):
    """Get details of an active or completed call session."""
    services = get_initialized_services()

    session = services["conversations"].get_session(session_id)

    return {
        "session_id": session.session_id,
        "industry": session.industry.value,
        "direction": session.direction.value,
        "status": session.status.value,
        "call_sid": session.call_sid,
        "started_at": session.started_at.isoformat(),
        "ended_at": session.ended_at.isoformat() if session.ended_at else None,
        "message_count": len(session.messages),
        "messages": [
            {
                "role": msg.role.value,
                "content": msg.content,
                "timestamp": msg.timestamp.isoformat(),
            }
            for msg in session.messages
        ],
    }
