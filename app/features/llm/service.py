"""
LLM Service - handles interactions with AWS Bedrock (Claude) and provides fallback responses.
Uses the same Bedrock setup as the agri domain agent.
"""

import json
from typing import Dict, List, Optional

import boto3
import structlog
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from app.config import get_settings
from app.core.exceptions import LLMServiceError
from app.features.agents.base_agent import BaseAgent
from app.shared.models import (
    AgentResponse,
    CallDirection,
    ConversationMessage,
)

logger = structlog.get_logger(__name__)

# Bedrock client singleton
_bedrock_client = None


def _get_bedrock_client():
    """Get or create the Bedrock runtime client."""
    global _bedrock_client
    if _bedrock_client is None:
        settings = get_settings()
        _bedrock_client = boto3.client(
            "bedrock-runtime",
            region_name=settings.aws_region,
        )
    return _bedrock_client


class LLMService:
    """
    Service that manages LLM interactions for all agents via AWS Bedrock (Claude).
    Provides domain-specific responses and fallback handling for out-of-scope queries.
    """

    def __init__(self):
        settings = get_settings()
        self._model_id = settings.bedrock_model_id
        self._fallback_temperature = settings.llm_fallback_temperature
        self._max_tokens = settings.llm_max_tokens

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type((Exception,)),
        reraise=True,
    )
    async def _call_llm(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.4,
        max_tokens: Optional[int] = None,
    ) -> str:
        """
        Call AWS Bedrock Claude via invoke_model (same pattern as agri agent).

        Args:
            messages: List of message dicts with role and content.
            temperature: Sampling temperature.
            max_tokens: Maximum tokens in response.

        Returns:
            The assistant's response text.

        Raises:
            LLMServiceError: If all retries are exhausted.
        """
        try:
            bedrock = _get_bedrock_client()

            # Separate system prompt from conversation messages
            system_prompt = ""
            conversation_messages = []

            for msg in messages:
                if msg["role"] == "system":
                    system_prompt = msg["content"]
                else:
                    conversation_messages.append({
                        "role": msg["role"],
                        "content": msg["content"],
                    })

            # Ensure at least one user message
            if not conversation_messages:
                conversation_messages.append({
                    "role": "user",
                    "content": "Hello",
                })

            # Build request body (Anthropic Messages API format for Bedrock)
            body = {
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": max_tokens or self._max_tokens,
                "temperature": temperature,
                "messages": conversation_messages,
            }

            if system_prompt:
                body["system"] = system_prompt

            response = bedrock.invoke_model(
                modelId=self._model_id,
                contentType="application/json",
                accept="application/json",
                body=json.dumps(body),
            )

            response_body = json.loads(response["body"].read())
            content = response_body.get("content", [])

            if not content:
                raise LLMServiceError("Bedrock returned empty response")

            reply = content[0].get("text", "")
            if not reply:
                raise LLMServiceError("Bedrock returned empty text")

            return reply.strip()

        except LLMServiceError:
            raise
        except Exception as exc:
            logger.error("llm_call_failed", error=str(exc))
            raise LLMServiceError(f"Bedrock service error: {str(exc)}")

    async def generate_response(
        self,
        agent: BaseAgent,
        messages: List[ConversationMessage],
        user_message: str,
        direction: CallDirection,
        context: Optional[Dict] = None,
    ) -> AgentResponse:
        """
        Generate a response using the appropriate agent and LLM.
        Automatically routes to fallback if query is out of domain.
        """
        is_relevant = agent.is_relevant_query(user_message)

        if is_relevant:
            return await self._generate_domain_response(
                agent, messages, direction, context
            )
        else:
            return await self._generate_fallback_response(
                agent, messages, user_message
            )

    async def _generate_domain_response(
        self,
        agent: BaseAgent,
        messages: List[ConversationMessage],
        direction: CallDirection,
        context: Optional[Dict] = None,
    ) -> AgentResponse:
        """Generate a domain-specific response using the agent's system prompt."""
        llm_messages = agent.build_conversation_context(messages, direction, context)

        try:
            response_text = await self._call_llm(
                messages=llm_messages,
                temperature=0.4,
            )
            logger.info(
                "domain_response_generated",
                industry=agent.industry.value,
                response_length=len(response_text),
            )
            return AgentResponse(text=response_text, is_fallback=False)

        except LLMServiceError:
            return await self._generate_error_fallback(agent)

    async def _generate_fallback_response(
        self,
        agent: BaseAgent,
        messages: List[ConversationMessage],
        user_message: str,
    ) -> AgentResponse:
        """
        Generate a fallback response for out-of-domain queries.
        Acknowledges the question and guides back to the agent's domain.
        """
        fallback_prompt = agent.get_fallback_system_prompt()

        llm_messages = [
            {"role": "system", "content": fallback_prompt},
            {"role": "user", "content": user_message},
        ]

        try:
            response_text = await self._call_llm(
                messages=llm_messages,
                temperature=self._fallback_temperature,
                max_tokens=150,
            )
            logger.info(
                "fallback_response_generated",
                industry=agent.industry.value,
                user_query_preview=user_message[:50],
            )
            return AgentResponse(text=response_text, is_fallback=True)

        except LLMServiceError:
            return await self._generate_error_fallback(agent)

    async def _generate_error_fallback(self, agent: BaseAgent) -> AgentResponse:
        """
        Last-resort fallback when Bedrock is completely unavailable.
        Returns a static polite message.
        """
        industry_name = agent.industry.value.replace("_", " ")
        fallback_text = (
            f"I apologize, but I'm experiencing some technical difficulties right now. "
            f"I'm your {industry_name} assistant and I want to make sure I help you properly. "
            f"Could you please try again in a moment, or I can connect you with a human representative?"
        )
        logger.warning("error_fallback_used", industry=agent.industry.value)
        return AgentResponse(text=fallback_text, is_fallback=True)

    async def generate_greeting(
        self,
        agent: BaseAgent,
        direction: CallDirection,
        context: Optional[Dict] = None,
    ) -> str:
        """Get the appropriate greeting for a new call."""
        return agent.get_greeting(direction, context)
