"""
Palvi Agrico Voice Bot — FastAPI Application.

Supports both:
- HTTP Webhooks (fallback, slower ~4s)
- WebSocket Media Streams (fast, ~2s)
"""
import asyncio
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response

from app.config import settings
from routes import twilio_routes, call_trigger_routes, call_history_routes
from services.sarvam_tts import get_cached_audio
from orchestrator.graph import pre_cache_static_responses, ALL_SCRIPTED_TEXTS, GREETING, COMPANY_INTRO, COMPANY_INTRO_2, ASK_CROP, NO_TIME_RESPONSE, THANK_YOU, NO_INPUT_RESPONSE, CYMINT_RECOMMENDATION, SIZE_PLUS_RECOMMENDATION, BOTH_PRODUCTS
from handlers.websocket_handler import handle_media_stream
from services.audio_cache import init_filler_audio, init_script_cache

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Pre-cache audio and initialize pipeline before accepting calls."""
    logger.info("[STARTUP] Initializing audio caches...")

    # B1: Pre-synthesize filler audio clips
    await init_filler_audio()

    # B2: Pre-cache all scripted audio (no live TTS for these during calls)
    await init_script_cache(ALL_SCRIPTED_TEXTS)

    # Also cache the combined intro
    full_intro = COMPANY_INTRO + " " + COMPANY_INTRO_2 + " " + ASK_CROP
    await init_script_cache([full_intro])

    # Also cache for HTTP webhook fallback
    await pre_cache_static_responses()

    logger.info(f"[STARTUP] Ready! Public WSS: {settings.PUBLIC_WSS_URL}")
    yield


app = FastAPI(title="Palvi Agrico Voice Bot", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routes
app.include_router(twilio_routes.router, prefix="/voice", tags=["Twilio"])
app.include_router(call_trigger_routes.router, prefix="/call", tags=["Call Trigger"])
app.include_router(call_history_routes.router, prefix="/calls", tags=["Call History"])


@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "palvi-agrico-bot"}


@app.get("/")
async def root():
    return {"message": "Palvi Agrico Voice Bot is running"}


@app.get("/audio/{filename}")
async def serve_audio(filename: str):
    """Serve cached TTS audio directly to Twilio."""
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


@app.websocket("/media-stream")
async def media_stream_endpoint(websocket: WebSocket):
    """WebSocket endpoint for Twilio Media Streams (low latency)."""
    await websocket.accept()
    logger.info("[WS] New media stream connection")
    await handle_media_stream(websocket)
    logger.info("[WS] Media stream disconnected")
