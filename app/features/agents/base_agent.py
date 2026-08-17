"""
Base agent class that all industry-specific agents inherit from.
Provides common functionality and enforces the agent interface.
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any

import structlog

from app.shared.models import (
    AgentResponse,
    CallDirection,
    ConversationMessage,
    ConversationRole,
    IndustryType,
)

logger = structlog.get_logger(__name__)


class BaseAgent(ABC):
    """
    Abstract base class for all calling agents.
    Each industry agent must implement the core methods.
    """

    def __init__(self, industry: IndustryType):
        self.industry = industry
        self._system_prompt: str = ""
        self._greeting_inbound: str = ""
        self._greeting_outbound: str = ""
        self._fallback_topics: List[str] = []

    @property
    def system_prompt(self) -> str:
        """Get the agent's system prompt."""
        return self._system_prompt

    @property
    def greeting_inbound(self) -> str:
        """Get greeting for inbound calls."""
        return self._greeting_inbound

    @property
    def greeting_outbound(self) -> str:
        """Get greeting for outbound calls."""
        return self._greeting_outbound

    @abstractmethod
    def get_system_prompt(self, direction: CallDirection, context: Optional[Dict[str, Any]] = None) -> str:
        """
        Build the full system prompt for the LLM based on call direction and context.

        Args:
            direction: Whether this is inbound or outbound call.
            context: Optional context (e.g., customer info for outbound).

        Returns:
            Complete system prompt string.
        """
        pass

    @abstractmethod
    def get_greeting(self, direction: CallDirection, context: Optional[Dict[str, Any]] = None) -> str:
        """
        Get the initial greeting based on call direction.

        Args:
            direction: Whether this is inbound or outbound call.
            context: Optional context for personalization.

        Returns:
            Greeting message string.
        """
        pass

    @abstractmethod
    def get_domain_keywords(self) -> List[str]:
        """
        Return list of domain-specific keywords that indicate
        the query is relevant to this agent's domain.

        Returns:
            List of keywords.
        """
        pass

    def is_relevant_query(self, user_message: str) -> bool:
        """
        Check if the user's message is relevant to this agent's domain.
        Used to decide whether to use domain-specific response or LLM fallback.

        Args:
            user_message: The user's message text.

        Returns:
            True if query is relevant to this domain.
        """
        message_lower = user_message.lower()
        keywords = self.get_domain_keywords()
        return any(keyword.lower() in message_lower for keyword in keywords)

    def get_fallback_system_prompt(self) -> str:
        """
        Get the system prompt for the LLM fallback handler.
        Used when user asks irrelevant or out-of-scope questions.

        Returns:
            Fallback system prompt string.
        """
        return (
            f"You are a helpful and polite AI assistant currently operating as a "
            f"{self.industry.value.replace('_', ' ')} calling agent. "
            f"The user has asked a question that is outside your primary domain. "
            f"Acknowledge their question politely, provide a brief helpful response if possible, "
            f"and gently guide the conversation back to {self.industry.value.replace('_', ' ')} topics. "
            f"Keep responses concise and conversational (2-3 sentences max). "
            f"Never provide financial advice, legal advice, or medical advice. "
            f"If the question is inappropriate or harmful, politely decline."
        )

    def build_conversation_context(
        self,
        messages: List[ConversationMessage],
        direction: CallDirection,
        context: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, str]]:
        """
        Build the full conversation context for the LLM.

        Args:
            messages: List of conversation messages so far.
            direction: Call direction.
            context: Optional additional context.

        Returns:
            List of message dicts ready for LLM API.
        """
        system_prompt = self.get_system_prompt(direction, context)

        llm_messages = [{"role": "system", "content": system_prompt}]

        for msg in messages:
            role = "assistant" if msg.role == ConversationRole.AGENT else "user"
            if msg.role == ConversationRole.SYSTEM:
                continue
            llm_messages.append({"role": role, "content": msg.content})

        return llm_messages
