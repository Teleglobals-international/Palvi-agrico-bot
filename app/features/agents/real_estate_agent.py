"""
Real Estate industry calling agent.
Handles property inquiries, scheduling viewings, price discussions, etc.
"""

from typing import Any, Dict, List, Optional

from app.features.agents.base_agent import BaseAgent
from app.shared.models import CallDirection, IndustryType


class RealEstateAgent(BaseAgent):
    """Calling agent specialized for real estate industry."""

    def __init__(self):
        super().__init__(IndustryType.REAL_ESTATE)

        self._greeting_inbound = (
            "Hello! Thank you for calling. I'm your real estate assistant. "
            "How can I help you today? Whether you're looking to buy, sell, or rent "
            "a property, I'm here to assist you."
        )

        self._greeting_outbound = (
            "Hello! This is your real estate assistant calling. "
            "I'm reaching out regarding your property inquiry. "
            "Do you have a moment to chat?"
        )

    def get_system_prompt(self, direction: CallDirection, context: Optional[Dict[str, Any]] = None) -> str:
        """Build system prompt for real estate conversations."""
        base_prompt = (
            "You are a professional and friendly real estate calling agent. "
            "Your role is to assist callers with property-related inquiries. "
            "You can help with:\n"
            "- Property listings and availability\n"
            "- Scheduling property viewings and site visits\n"
            "- Providing information about localities, amenities, and infrastructure\n"
            "- Price range discussions and EMI estimates\n"
            "- Documentation requirements for buying/selling/renting\n"
            "- Connecting callers with the right real estate professionals\n\n"
            "Guidelines:\n"
            "- Be warm, professional, and knowledgeable\n"
            "- Ask clarifying questions to understand the caller's needs\n"
            "- Never provide exact legal or financial advice\n"
            "- Keep responses concise and conversational (suitable for phone calls)\n"
            "- If you don't know specifics, offer to connect them with a specialist\n"
            "- Always confirm next steps before ending the conversation\n"
        )

        if direction == CallDirection.INBOUND:
            base_prompt += (
                "\nThis is an inbound call. The caller is reaching out for help. "
                "Be receptive and guide the conversation to understand their needs."
            )
        else:
            base_prompt += (
                "\nThis is an outbound call. You are reaching out to the customer. "
                "Be respectful of their time and clearly state the purpose of your call."
            )

        if context:
            base_prompt += f"\n\nAdditional context: {context}"

        return base_prompt

    def get_greeting(self, direction: CallDirection, context: Optional[Dict[str, Any]] = None) -> str:
        """Get appropriate greeting based on call direction."""
        if direction == CallDirection.INBOUND:
            return self._greeting_inbound

        if context and context.get("customer_name"):
            return (
                f"Hello {context['customer_name']}! This is your real estate assistant calling. "
                f"I'm reaching out regarding your property inquiry. "
                f"Do you have a moment to chat?"
            )
        return self._greeting_outbound

    def get_domain_keywords(self) -> List[str]:
        """Return real estate domain keywords."""
        return [
            "property", "house", "apartment", "flat", "villa", "plot",
            "buy", "sell", "rent", "lease", "mortgage", "loan",
            "bedroom", "bhk", "sqft", "square feet", "area",
            "locality", "neighborhood", "location", "address",
            "viewing", "visit", "inspection", "site visit",
            "price", "cost", "rate", "budget", "emi",
            "builder", "developer", "broker", "agent",
            "registration", "stamp duty", "agreement", "possession",
            "amenities", "parking", "gym", "pool", "garden",
            "commercial", "residential", "industrial",
            "floor", "penthouse", "duplex", "studio",
            "furnished", "unfurnished", "semi-furnished",
            "real estate", "realty", "home", "housing",
        ]
