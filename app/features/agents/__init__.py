"""
Agent definitions for each industry vertical.
Each agent has its own system prompt, personality, and domain-specific capabilities.
"""

from app.features.agents.base_agent import BaseAgent
from app.features.agents.real_estate_agent import RealEstateAgent
from app.features.agents.home_services_agent import HomeServicesAgent
from app.features.agents.fintech_agent import FintechAgent
from app.features.agents.registry import AgentRegistry

__all__ = [
    "BaseAgent",
    "RealEstateAgent",
    "HomeServicesAgent",
    "FintechAgent",
    "AgentRegistry",
]
