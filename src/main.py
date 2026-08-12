"""
Palvi Agrico Voice Bot — FastAPI Application.

Supports Twilio (primary) and Exotel (fallback) telephony providers.
Provider is selected via TELEPHONY_PROVIDER environment variable.
"""
import asyncio
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response

from src.config.settings import settings
from src.modules.calls.exotel_webhooks import router as exotel_webhooks_router
from src.modules.calls.twilio_webhooks import router as twilio_webhooks_router
from src.modules.calls.trigger import router as exotel_trigger_router
from src.modules.calls.twilio_trigger import router as twilio_trigger_router
from src.modules.analytics.history import router as history_router
from src.modules.calls.live_ws import router as live_ws_router
from src.adapters.tts.sarvam_tts import get_cached_audio
from src.core.callFlow.scripts import (
    ALL_SCRIPTED_TEXTS, GREETING, COMPANY_INTRO, COMPANY_INTRO_2, ASK_CROP,
    NO_TIME_RESPONSE, THANK_YOU, NO_INPUT_RESPONSE,
)
from src.core.productKnowledge.products import (
    CYMINT_RECOMMENDATION, SIZE_PLUS_RECOMMENDATION, BOTH_PRODUCTS,
)
from src.core.callFlow.precache import pre_cache_static_responses
from src.adapters.telephony.exotel_ws import handle_media_stream
from src.adapters.telephony.twilio_ws import handle_twilio_media_stream
from src.adapters.tts.audio_cache import init_filler_audio, init_script_cache

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start server immediately, cache audio in background."""
    logger.info("[STARTUP] Initializing audio caches in background...")
    logger.info(f"[STARTUP] Telephony provider: {settings.TELEPHONY_PROVIDER.upper()}")

    # Start caching in background — server accepts requests immediately
    async def _background_cache():
        try:
            # B1: Pre-synthesize filler audio clips
            await init_filler_audio()

            # B2: Pre-cache all scripted audio (no live TTS for these during calls)
            await init_script_cache(ALL_SCRIPTED_TEXTS)

            # Also cache the combined intro
            full_intro = COMPANY_INTRO + " " + COMPANY_INTRO_2 + " " + ASK_CROP
            await init_script_cache([full_intro])

            # Also cache static responses
            await pre_cache_static_responses()

            logger.info("[STARTUP] Background audio caching complete!")
        except Exception as e:
            logger.error(f"[STARTUP] Background caching error: {e}")

    # Launch background task — don't block server startup
    asyncio.create_task(_background_cache())

    logger.info(f"[STARTUP] Server ready! (audio caching in background)")
    if settings.TELEPHONY_PROVIDER == "twilio":
        logger.info(f"[STARTUP] Twilio From: {settings.TWILIO_FROM_NUMBER}")
    else:
        logger.info(f"[STARTUP] Exotel Account: {settings.EXOTEL_ACCOUNT_SID}")
    logger.info(f"[STARTUP] Sample Rate: {settings.EXOTEL_SAMPLE_RATE}Hz")
    yield


app = FastAPI(title="Palvi Agrico Voice Bot", version="2.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)   

# Routes — conditionally include based on telephony provider
if settings.TELEPHONY_PROVIDER == "twilio":
    app.include_router(twilio_webhooks_router, prefix="/api/voice", tags=["Twilio"])
    app.include_router(twilio_trigger_router, prefix="/api/call", tags=["Call Trigger"])
else:
    app.include_router(exotel_webhooks_router, prefix="/api/voice", tags=["Exotel"])
    app.include_router(exotel_trigger_router, prefix="/api/call", tags=["Call Trigger"])

app.include_router(history_router, prefix="/api/calls", tags=["Call History"])
app.include_router(live_ws_router, prefix="/api", tags=["Live Call"])


@app.get("/api/audio/{filename}")
async def serve_audio(filename: str):
    """
    Serve cached TTS audio files directly to Twilio.

    Twilio's <Play> verb fetches audio from this endpoint.
    Files are cached in memory by synthesize_speech_to_url().
    """
    text_hash = filename.replace(".wav", "")
    audio_bytes = get_cached_audio(text_hash)
    if not audio_bytes:
        return Response(content="Not found", status_code=404)
    return Response(
        content=audio_bytes,
        media_type="audio/wav",
        headers={
            "Cache-Control": "public, max-age=3600",
            "Content-Length": str(len(audio_bytes)),
            "Accept-Ranges": "bytes",
        },
    )


@app.get("/api/health")
async def health_check():
    return {
        "status": "healthy",
        "service": "palvi-agrico-bot",
        "provider": settings.TELEPHONY_PROVIDER,
    }


@app.get("/health")
async def health_check_internal():
    """Internal health check for ALB/ECS (no /api prefix needed)."""
    return {"status": "healthy"}


@app.get("/")
async def root():
    return {
        "message": "Palvi Agrico Voice Bot is running",
        "provider": settings.TELEPHONY_PROVIDER,
    }


@app.websocket("/api/media-stream")
async def media_stream_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint for bidirectional audio streaming.

    Works with both Twilio Media Streams and Exotel Voicebot Applet.
    The handler is selected based on TELEPHONY_PROVIDER setting.
    """
    logger.info(f"[WS] New connection attempt from {websocket.client}")
    logger.info(f"[WS] Query params: {websocket.query_params}")
    await websocket.accept()

    if settings.TELEPHONY_PROVIDER == "twilio":
        logger.info("[WS] New Twilio media stream connection ACCEPTED")
        await handle_twilio_media_stream(websocket)
        logger.info("[WS] Twilio media stream disconnected")
    else:
        logger.info("[WS] New Exotel media stream connection ACCEPTED")
        await handle_media_stream(websocket)
        logger.info("[WS] Exotel media stream disconnected")
