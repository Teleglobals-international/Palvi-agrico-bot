"""
Palvi Agrico Voice Bot — FastAPI Application.

Uses Exotel Voicebot Applet for bidirectional WebSocket audio streaming.
"""
import asyncio
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response

from src.config.settings import settings
from src.modules.calls.exotel_webhooks import router as exotel_router
from src.modules.calls.trigger import router as trigger_router
from src.modules.analytics.history import router as history_router
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
from src.adapters.tts.audio_cache import init_filler_audio, init_script_cache

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

    # Also cache static responses
    await pre_cache_static_responses()

    logger.info(f"[STARTUP] Ready! Public WSS: {settings.PUBLIC_WSS_URL}")
    logger.info(f"[STARTUP] Exotel Account: {settings.EXOTEL_ACCOUNT_SID}")
    logger.info(f"[STARTUP] Sample Rate: {settings.EXOTEL_SAMPLE_RATE}Hz")
    yield


app = FastAPI(title="Palvi Agrico Voice Bot", version="2.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routes
app.include_router(exotel_router, prefix="/voice", tags=["Exotel"])
app.include_router(trigger_router, prefix="/call", tags=["Call Trigger"])
app.include_router(history_router, prefix="/calls", tags=["Call History"])


@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "palvi-agrico-bot", "provider": "exotel"}


@app.get("/")
async def root():
    return {"message": "Palvi Agrico Voice Bot is running (Exotel)"}


@app.websocket("/media-stream")
async def media_stream_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint for Exotel Voicebot Applet (bidirectional audio streaming).

    Configure this URL in your Exotel Call Flow's Voicebot Applet:
    wss://your-domain.com/media-stream?sample-rate=8000
    """
    logger.info(f"[WS] New connection attempt from {websocket.client}")
    logger.info(f"[WS] Query params: {websocket.query_params}")
    await websocket.accept()
    logger.info("[WS] New Exotel media stream connection ACCEPTED")
    await handle_media_stream(websocket)
    logger.info("[WS] Exotel media stream disconnected")
