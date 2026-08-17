"""
API v1 routes.
"""

from fastapi import APIRouter

from app.api.v1.calling import router as calling_router
from app.api.v1.agents import router as agents_router
from app.api.v1.health import router as health_router

api_v1_router = APIRouter(prefix="/api/v1")

api_v1_router.include_router(health_router, tags=["Health"])
api_v1_router.include_router(agents_router, prefix="/agents", tags=["Agents"])
api_v1_router.include_router(calling_router, prefix="/calling", tags=["Calling"])
