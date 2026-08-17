"""
Agent registry - singleton that manages all industry agent instances.
Provides lookup by industry type.
"""

from typing import Dict, Optional

import structlog

from app.features.agents.base_agent import BaseAgent
from app.features.agents.real_estate_agent import RealEstateAgent
from app.features.agents.home_services_agent import HomeServicesAgent
from app.features.agents.fintech_agent import FintechAgent
from app.shared.models import IndustryType
from app.core.exceptions import AgentNotFoundError

logger = structlog.get_logger(__name__)


class AgentRegistry:
    """
    Registry that holds all agent instances.
    Provides a central lookup mechanism for agents by industry type.
    """

    _instance: Optional["AgentRegistry"] = None
    _agents: Dict[IndustryType, BaseAgent] = {}

    def __new__(cls) -> "AgentRegistry":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialize_agents()
        return cls._instance

    def _initialize_agents(self) -> None:
        """Initialize all industry agents."""
        self._agents = {
            IndustryType.REAL_ESTATE: RealEstateAgent(),
            IndustryType.HOME_SERVICES: HomeServicesAgent(),
            IndustryType.FINTECH: FintechAgent(),
        }
        logger.info(
            "agent_registry_initialized",
            agents=list(self._agents.keys()),
        )

    def get_agent(self, industry: IndustryType) -> BaseAgent:
        """
        Get agent instance by industry type.

        Args:
            industry: The industry type to look up.

        Returns:
            The corresponding agent instance.

        Raises:
            AgentNotFoundError: If industry type has no registered agent.
        """
        agent = self._agents.get(industry)
        if agent is None:
            raise AgentNotFoundError(industry.value)
        return agent

    def list_agents(self) -> Dict[str, str]:
        """List all registered agents with their industry types."""
        return {
            industry.value: agent.__class__.__name__
            for industry, agent in self._agents.items()
        }

    def is_registered(self, industry: IndustryType) -> bool:
        """Check if an agent is registered for the given industry."""
        return industry in self._agents
