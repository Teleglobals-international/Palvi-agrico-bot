"""
Main FastAPI application entry point.
Configures the app, middleware, and routes.
"""

import asyncio
import os
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import api_v1_router
from app.config import get_settings
from app.core.middleware import ExceptionHandlerMiddleware, RequestLoggingMiddleware
from app.features.agents.registry import AgentRegistry

# Determine if running in debug mode
IS_DEBUG = os.getenv("DEBUG", "false").lower() == "true"

# Configure structured logging
structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.StackInfoRenderer(),
        structlog.dev.set_exc_info,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.dev.ConsoleRenderer() if IS_DEBUG else structlog.processors.JSONRenderer(),
    ],
    wrapper_class=structlog.make_filtering_bound_logger(20),
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(),
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager - startup and shutdown logic."""
    settings = get_settings()
    logger.info("application_starting", base_url=settings.base_url)

    # Initialize agent registry (singleton, pre-warms all agents)
    registry = AgentRegistry()
    logger.info("agents_initialized", agents=registry.list_agents())

    # Start background session cleanup task
    cleanup_task = asyncio.create_task(_periodic_session_cleanup())

    yield

    # Shutdown
    cleanup_task.cancel()
    logger.info("application_shutting_down")


async def _periodic_session_cleanup():
    """Background task that cleans up expired sessions every 5 minutes."""
    from app.features.conversation import ConversationManager

    manager = ConversationManager()
    while True:
        try:
            await asyncio.sleep(300)  # Every 5 minutes
            cleaned = manager.cleanup_expired_sessions(max_age_seconds=3600)
            if cleaned:
                logger.info("session_cleanup_completed", removed=cleaned)
        except asyncio.CancelledError:
            break
        except Exception as exc:
            logger.error("session_cleanup_error", error=str(exc))


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="Multi-Tenant Calling Agent Platform",
        version="1.0.0",
        description=(
            "Production-grade multi-tenant AI calling agent platform. "
            "Supports Real Estate, Home Services, and Fintech industries "
            "with inbound and outbound calling via Exotel."
        ),
        docs_url="/docs" if IS_DEBUG else None,
        redoc_url="/redoc" if IS_DEBUG else None,
        lifespan=lifespan,
    )

    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Custom middleware (order matters - first added = outermost)
    app.add_middleware(RequestLoggingMiddleware)
    app.add_middleware(ExceptionHandlerMiddleware)

    # Include API routes
    app.include_router(api_v1_router)

    # Top-level WebSocket endpoint for Exotel Voicebot Applet
    # (matches agri agent pattern: wss://domain/media-stream)
    from fastapi import WebSocket as WS
    from app.features.agents.registry import AgentRegistry as AR
    from app.features.conversation import ConversationManager as CM
    from app.features.llm import LLMService as LS
    from app.features.calling.websocket_handler import WebSocketHandler as WSH
    from app.shared.models import IndustryType as IT

    @app.websocket("/media-stream")
    async def root_media_stream(websocket: WS):
        """Top-level WebSocket for Exotel Voicebot Applet compatibility."""
        registry = AR()
        conversations = CM()
        llm = LS()
        handler = WSH(registry, conversations, llm)
        # Default to real_estate; industry parsed from custom_parameters
        await handler.handle_connection(websocket=websocket, industry=IT.REAL_ESTATE)

    return app


# Create the application instance
app = create_app()


if __name__ == "__main__":
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "app.main:app",
        host=settings.app_host,
        port=settings.app_port,
        reload=False,
        log_level="info",
    )
