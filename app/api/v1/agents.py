"""
Agent management endpoints - list agents, get agent info.
"""

from fastapi import APIRouter, Depends

from app.features.agents.registry import AgentRegistry
from app.shared.models import IndustryType

router = APIRouter()


def get_agent_registry() -> AgentRegistry:
    """Dependency to get the agent registry."""
    return AgentRegistry()


@router.get("/")
async def list_agents(registry: AgentRegistry = Depends(get_agent_registry)):
    """List all registered industry agents."""
    agents = registry.list_agents()
    return {
        "agents": agents,
        "total": len(agents),
    }


@router.get("/{industry}")
async def get_agent_info(
    industry: IndustryType,
    registry: AgentRegistry = Depends(get_agent_registry),
):
    """Get detailed information about a specific industry agent."""
    agent = registry.get_agent(industry)
    return {
        "industry": industry.value,
        "agent_class": agent.__class__.__name__,
        "greeting_inbound": agent.greeting_inbound,
        "greeting_outbound": agent.greeting_outbound,
        "domain_keywords_count": len(agent.get_domain_keywords()),
        "supports_inbound": True,
        "supports_outbound": True,
    }
