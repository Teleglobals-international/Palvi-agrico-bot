"""
Exotel Webhook Handler - processes inbound/outbound call lifecycle events.
Routes calls to appropriate industry agents.
"""

import json
from typing import Any, Dict, Optional

import structlog

from app.core.exceptions import ExotelWebhookError
from app.features.agents.registry import AgentRegistry
from app.features.conversation import ConversationManager
from app.features.llm import LLMService
from app.shared.models import (
    CallDirection,
    CallStatus,
    ConversationRole,
    IndustryType,
)

logger = structlog.get_logger(__name__)


class WebhookHandler:
    """
    Handles Exotel webhook callbacks for call lifecycle events.
    Routes to the correct industry agent based on webhook data.
    """

    def __init__(
        self,
        agent_registry: AgentRegistry,
        conversation_manager: ConversationManager,
        llm_service: LLMService,
    ):
        self._registry = agent_registry
        self._conversations = conversation_manager
        self._llm = llm_service

    async def handle_incoming_call(
        self,
        industry: IndustryType,
        webhook_data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Handle a new incoming (inbound) call webhook from Exotel.

        Args:
            industry: The industry type this call is routed to.
            webhook_data: Raw webhook payload from Exotel.

        Returns:
            Response dict with TwiML/Exotel XML instructions.
        """
        call_sid = webhook_data.get("CallSid")
        from_number = webhook_data.get("From")
        to_number = webhook_data.get("To")

        if not call_sid:
            raise ExotelWebhookError("Missing CallSid in webhook data")

        logger.info(
            "incoming_call_received",
            call_sid=call_sid,
            industry=industry.value,
            from_number=from_number[:6] + "****" if from_number else None,
        )

        # Get the appropriate agent
        agent = self._registry.get_agent(industry)

        # Create a new conversation session
        session = self._conversations.create_session(
            industry=industry,
            direction=CallDirection.INBOUND,
            call_sid=call_sid,
            caller_number=from_number,
            callee_number=to_number,
            metadata={"webhook_data": webhook_data},
        )

        # Generate greeting
        greeting = await self._llm.generate_greeting(
            agent=agent,
            direction=CallDirection.INBOUND,
        )

        # Store greeting as first agent message
        self._conversations.add_message(
            session_id=session.session_id,
            role=ConversationRole.AGENT,
            content=greeting,
        )

        # Update status
        self._conversations.update_status(session.session_id, CallStatus.IN_PROGRESS)

        return {
            "session_id": session.session_id,
            "greeting": greeting,
            "call_sid": call_sid,
            "industry": industry.value,
            "status": "connected",
        }

    async def handle_answer_callback(
        self,
        industry: IndustryType,
        webhook_data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Handle the answer callback (when outbound call is answered).

        Args:
            industry: The industry type for this call.
            webhook_data: Raw webhook payload.

        Returns:
            Response with greeting and session info.
        """
        call_sid = webhook_data.get("CallSid")

        if not call_sid:
            raise ExotelWebhookError("Missing CallSid in answer callback")

        # Find existing session or create one
        session = self._conversations.get_session_by_call_sid(call_sid)

        if not session:
            # Parse context from custom field if available
            context = None
            custom_field = webhook_data.get("CustomField", "")
            if custom_field:
                try:
                    context = json.loads(custom_field).get("context")
                except (json.JSONDecodeError, AttributeError):
                    pass

            session = self._conversations.create_session(
                industry=industry,
                direction=CallDirection.OUTBOUND,
                call_sid=call_sid,
                caller_number=webhook_data.get("From"),
                callee_number=webhook_data.get("To"),
                metadata={"context": context},
            )

        agent = self._registry.get_agent(industry)

        greeting = await self._llm.generate_greeting(
            agent=agent,
            direction=session.direction,
            context=session.metadata.get("context"),
        )

        self._conversations.add_message(
            session_id=session.session_id,
            role=ConversationRole.AGENT,
            content=greeting,
        )

        self._conversations.update_status(session.session_id, CallStatus.IN_PROGRESS)

        logger.info(
            "call_answered",
            call_sid=call_sid,
            session_id=session.session_id,
            industry=industry.value,
        )

        return {
            "session_id": session.session_id,
            "greeting": greeting,
            "call_sid": call_sid,
            "status": "answered",
        }

    async def handle_status_callback(
        self,
        webhook_data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Handle call status update webhooks (ringing, completed, failed, etc.).

        Args:
            webhook_data: Raw webhook payload with status info.

        Returns:
            Acknowledgment response.
        """
        call_sid = webhook_data.get("CallSid")
        status = webhook_data.get("Status", "").lower()

        if not call_sid:
            raise ExotelWebhookError("Missing CallSid in status callback")

        # Map Exotel status to our CallStatus enum
        status_map = {
            "initiated": CallStatus.INITIATED,
            "ringing": CallStatus.RINGING,
            "in-progress": CallStatus.IN_PROGRESS,
            "completed": CallStatus.COMPLETED,
            "failed": CallStatus.FAILED,
            "no-answer": CallStatus.NO_ANSWER,
            "busy": CallStatus.BUSY,
        }

        call_status = status_map.get(status, CallStatus.FAILED)

        # Find session and update
        session = self._conversations.get_session_by_call_sid(call_sid)

        if session:
            self._conversations.update_status(session.session_id, call_status)

            if call_status in (CallStatus.COMPLETED, CallStatus.FAILED, CallStatus.NO_ANSWER):
                self._conversations.end_session(session.session_id)

        logger.info(
            "call_status_updated",
            call_sid=call_sid,
            status=status,
            session_found=session is not None,
        )

        return {
            "call_sid": call_sid,
            "status": status,
            "acknowledged": True,
        }

    async def handle_user_input(
        self,
        session_id: str,
        user_message: str,
    ) -> Dict[str, Any]:
        """
        Process user speech/input during a call and generate agent response.

        Args:
            session_id: The active session ID.
            user_message: Transcribed user speech.

        Returns:
            Agent response dict.
        """
        session = self._conversations.get_session(session_id)
        agent = self._registry.get_agent(session.industry)

        # Add user message to conversation
        self._conversations.add_message(
            session_id=session_id,
            role=ConversationRole.USER,
            content=user_message,
        )

        # Generate response (handles domain vs fallback routing internally)
        response = await self._llm.generate_response(
            agent=agent,
            messages=session.messages,
            user_message=user_message,
            direction=session.direction,
            context=session.metadata.get("context"),
        )

        # Store agent response
        self._conversations.add_message(
            session_id=session_id,
            role=ConversationRole.AGENT,
            content=response.text,
            metadata={"is_fallback": response.is_fallback},
        )

        logger.info(
            "user_input_processed",
            session_id=session_id,
            industry=session.industry.value,
            is_fallback=response.is_fallback,
        )

        return {
            "session_id": session_id,
            "response": response.text,
            "is_fallback": response.is_fallback,
            "end_conversation": response.end_conversation,
        }
