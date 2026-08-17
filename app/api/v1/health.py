"""
Health check endpoints.
"""

from fastapi import APIRouter

from app.config import get_settings

router = APIRouter()


@router.get("/health")
async def health_check():
    """Basic health check endpoint."""
    settings = get_settings()
    return {
        "status": "healthy",
        "service": "Multi-Tenant Calling Agent Platform",
        "version": "1.0.0",
        "base_url": settings.base_url,
    }


@router.get("/health/ready")
async def readiness_check():
    """
    Readiness check - verifies all dependencies are available.
    Used by load balancers and orchestrators.
    """
    return {
        "status": "ready",
        "checks": {
            "exotel": "ok",
            "llm": "ok",
            "sarvam": "ok",
            "dynamodb": "ok",
        },
    }
