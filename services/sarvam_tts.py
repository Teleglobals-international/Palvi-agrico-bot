"""Sarvam AI TTS — with memory + disk caching. Zero API calls during calls after first run."""
import os
import base64
import hashlib
import logging
import httpx

from app.config import settings

logger = logging.getLogger(__name__)

# In-memory cache: text_hash -> audio_bytes
_tts_audio_cache: dict[str, bytes] = {}

# Disk cache directory
CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "audio_cache")
os.makedirs(CACHE_DIR, exist_ok=True)


def get_cached_audio(text_hash: str) -> bytes | None:
    """Get cached audio bytes by hash."""
    return _tts_audio_cache.get(text_hash)


async def pre_cache_audio(text: str) -> None:
    """Pre-generate and cache TTS audio for a static response."""
    await synthesize_speech_to_url(text)


async def synthesize_speech_to_url(text: str) -> str:
    """Convert Marathi text to speech. Uses memory → disk → API fallback."""
    if not text or not settings.SARVAM_API_KEY:
        return ""

    if len(text) > 2000:
        text = text[:2000]

    text_hash = hashlib.md5(text.encode()).hexdigest()
    base_url = settings.BASE_URL.rstrip("/")

    # 1. Check memory cache (instant)
    if text_hash in _tts_audio_cache:
        logger.info(f"[SARVAM TTS] Memory cache hit: '{text[:30]}'")
        return f"{base_url}/audio/{text_hash}.wav"

    # 2. Check disk cache (fast, no API call)
    disk_path = os.path.join(CACHE_DIR, f"{text_hash}.wav")
    if os.path.exists(disk_path):
        with open(disk_path, "rb") as f:
            audio_bytes = f.read()
        _tts_audio_cache[text_hash] = audio_bytes
        logger.info(f"[SARVAM TTS] Disk cache hit: '{text[:30]}'")
        return f"{base_url}/audio/{text_hash}.wav"

    # 3. Call Sarvam API (only first time ever for this text)
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                settings.SARVAM_TTS_URL,
                headers={
                    "Content-Type": "application/json",
                    "api-subscription-key": settings.SARVAM_API_KEY,
                },
                json={
                    "inputs": [text],
                    "target_language_code": "mr-IN",
                    "model": "bulbul:v3",
                    "speaker": "rupali",
                    "pace": 1.0,
                    "speech_sample_rate": 8000,
                }
            )

            if response.status_code == 200:
                result = response.json()
                audios = result.get("audios", [])
                if not audios:
                    logger.warning("[SARVAM TTS] No audio in response")
                    return ""

                audio_bytes = base64.b64decode(audios[0])

                if len(audio_bytes) < 500:
                    logger.warning("[SARVAM TTS] Audio too small")
                    return ""

                # Save to memory cache
                _tts_audio_cache[text_hash] = audio_bytes

                # Save to disk cache (survives restarts)
                with open(disk_path, "wb") as f:
                    f.write(audio_bytes)

                logger.info(f"[SARVAM TTS] Generated + cached: {len(audio_bytes)} bytes")
                return f"{base_url}/audio/{text_hash}.wav"
            else:
                logger.error(f"[SARVAM TTS] HTTP {response.status_code}: {response.text[:200]}")
                return ""

    except Exception as e:
        logger.error(f"[SARVAM TTS] Error: {e}")
        return ""
