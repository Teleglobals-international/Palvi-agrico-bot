"""
Home Services industry calling agent.
Handles service bookings, quotes, scheduling, complaints, etc.
"""

from typing import Any, Dict, List, Optional

from app.features.agents.base_agent import BaseAgent
from app.shared.models import CallDirection, IndustryType


class HomeServicesAgent(BaseAgent):
    """Calling agent specialized for home services industry."""

    def __init__(self):
        super().__init__(IndustryType.HOME_SERVICES)

        self._greeting_inbound = (
            "Hello! Thank you for calling our home services center. "
            "I'm here to help you with any home service needs — "
            "plumbing, electrical, cleaning, painting, or any other service. "
            "How can I assist you today?"
        )

        self._greeting_outbound = (
            "Hello! This is your home services assistant calling. "
            "I'm following up on your recent service request. "
            "Do you have a moment?"
        )

    def get_system_prompt(self, direction: CallDirection, context: Optional[Dict[str, Any]] = None) -> str:
        """Build system prompt for home services conversations."""
        base_prompt = (
            "You are a professional and helpful home services calling agent. "
            "Your role is to assist callers with all home maintenance and improvement services. "
            "You can help with:\n"
            "- Scheduling service appointments (plumbing, electrical, HVAC, etc.)\n"
            "- Providing service quotes and estimates\n"
            "- Explaining service processes and timelines\n"
            "- Handling service complaints and rescheduling\n"
            "- Recommending appropriate services based on the issue described\n"
            "- Following up on completed services for feedback\n\n"
            "Guidelines:\n"
            "- Be empathetic and solution-oriented\n"
            "- Ask about the urgency of the issue (emergency vs. routine)\n"
            "- Collect necessary details: address, preferred time, description of issue\n"
            "- Keep responses concise and conversational (suitable for phone calls)\n"
            "- Provide realistic timelines — never overpromise\n"
            "- For emergencies, escalate immediately and confirm help is on the way\n"
            "- Always confirm booking details before ending the call\n"
        )

        if direction == CallDirection.INBOUND:
            base_prompt += (
                "\nThis is an inbound call. The customer likely needs help with a service. "
                "Be receptive, understand their issue, and guide them to a solution."
            )
        else:
            base_prompt += (
                "\nThis is an outbound call. You are following up with the customer. "
                "Be respectful of their time and be clear about the purpose of the call."
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
                f"Hello {context['customer_name']}! This is your home services assistant. "
                f"I'm calling to follow up on your recent service request. "
                f"Do you have a moment?"
            )
        return self._greeting_outbound

    def get_domain_keywords(self) -> List[str]:
        """Return home services domain keywords."""
        return [
            "plumber", "plumbing", "electrician", "electrical", "wiring",
            "hvac", "air conditioning", "ac", "heating", "ventilation",
            "cleaning", "deep clean", "sanitization", "pest control",
            "painting", "painter", "wall", "interior", "exterior",
            "carpenter", "carpentry", "furniture", "woodwork",
            "repair", "fix", "broken", "leak", "damage", "maintenance",
            "install", "installation", "setup", "fitting",
            "service", "technician", "handyman", "professional",
            "booking", "appointment", "schedule", "visit", "slot",
            "quote", "estimate", "cost", "charges", "pricing",
            "emergency", "urgent", "immediate", "asap",
            "complaint", "issue", "problem", "not working",
            "bathroom", "kitchen", "bedroom", "roof", "floor",
            "pipe", "tap", "switch", "socket", "bulb", "fan",
            "home", "house", "apartment", "office",
            "warranty", "guarantee", "follow-up",
        ]
