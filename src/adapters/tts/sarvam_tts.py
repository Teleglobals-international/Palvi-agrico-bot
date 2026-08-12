"""
Sarvam AI TTS — Optimized for natural Marathi female voice.

Speaker: priya (warm, conversational)
Model: bulbul:v3
Pace: 0.92 (slightly slower for clarity)
Pre-processing: Converts text to conversational speech-ready format.
Caching: memory + disk. Zero API calls during calls after first run.
"""
import os
import re
import base64
import hashlib
import logging
import httpx

from src.config.settings import settings

logger = logging.getLogger(__name__)

# In-memory cache: text_hash -> audio_bytes
_tts_audio_cache: dict[str, bytes] = {}

# Disk cache directory
CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), "audio_cache")
os.makedirs(CACHE_DIR, exist_ok=True)

# TTS Configuration — optimized for natural phone conversation
TTS_CONFIG = {
    "model": "bulbul:v3",
    "speaker": "priya",
    "target_language_code": "mr-IN",
    "pace": 0.95,  # Natural conversational pace
    "speech_sample_rate": 8000,  # Phone quality
}


# ═══════════════════════════════════════════════════════════════
# TEXT PREPROCESSOR — Makes text sound natural when spoken
# ═══════════════════════════════════════════════════════════════

def preprocess_for_speech(text: str) -> str:
    """
    Convert text to speech-ready format for natural Marathi delivery.
    - Expands numbers to Marathi words
    - Adds natural pauses
    - Keeps sentences short
    - Removes unnatural punctuation
    """
    if not text:
        return text

    # Expand common numbers to Marathi words
    number_map = {
        "1": "एक", "2": "दोन", "3": "तीन", "4": "चार", "5": "पाच",
        "6": "सहा", "7": "सात", "8": "आठ", "9": "नऊ", "10": "दहा",
        "15": "पंधरा", "20": "वीस", "25": "पंचवीस", "30": "तीस",
        "50": "पन्नास", "100": "शंभर", "200": "दोनशे", "300": "तीनशे",
        "400": "चारशे", "500": "पाचशे", "1000": "हजार",
    }

    # Expand standalone numbers (not part of larger numbers)
    for num, word in sorted(number_map.items(), key=lambda x: -len(x[0])):
        text = re.sub(rf'\b{num}\b', word, text)

    # Expand currency patterns
    text = re.sub(r'₹\s*(\d+)', r'\1 रुपये', text)

    # Remove markdown formatting if any slipped through
    text = re.sub(r'\*\*([^*]+)\*\*', r'\1', text)
    text = re.sub(r'\*([^*]+)\*', r'\1', text)
    text = re.sub(r'`([^`]+)`', r'\1', text)

    # Replace semicolons with natural pause
    text = text.replace(";", "...")

    # Add slight pause after "सर" at beginning of sentence
    text = re.sub(r'^सर,', 'सर...', text)

    # Ensure commas have breathing space (Sarvam uses these for pauses)
    text = re.sub(r',\s*', ', ', text)

    # Remove excessive periods
    text = re.sub(r'\.{4,}', '...', text)

    # Trim whitespace
    text = re.sub(r'\s+', ' ', text).strip()

    return text


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

    # Preprocess for natural speech
    speech_text = preprocess_for_speech(text)

    # Cache key based on original text (so lookups match)
    text_hash = hashlib.md5(text.encode()).hexdigest()
    base_url = settings.BASE_URL.rstrip("/")

    # 1. Check memory cache (instant)
    if text_hash in _tts_audio_cache:
        logger.info(f"[SARVAM TTS] Memory cache hit: '{text[:30]}'")
        return f"{base_url}/api/audio/{text_hash}.wav"

    # 2. Check disk cache (fast, no API call)
    disk_path = os.path.join(CACHE_DIR, f"{text_hash}.wav")
    if os.path.exists(disk_path):
        with open(disk_path, "rb") as f:
            audio_bytes = f.read()
        _tts_audio_cache[text_hash] = audio_bytes
        logger.info(f"[SARVAM TTS] Disk cache hit: '{text[:30]}'")
        return f"{base_url}/api/audio/{text_hash}.wav"

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
                    "inputs": [speech_text],
                    "target_language_code": TTS_CONFIG["target_language_code"],
                    "model": TTS_CONFIG["model"],
                    "speaker": TTS_CONFIG["speaker"],
                    "pace": TTS_CONFIG["pace"],
                    "speech_sample_rate": TTS_CONFIG["speech_sample_rate"],
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
                return f"{base_url}/api/audio/{text_hash}.wav"
            else:
                logger.error(f"[SARVAM TTS] HTTP {response.status_code}: {response.text[:200]}")
                return ""

    except Exception as e:
        logger.error(f"[SARVAM TTS] Error: {e}")
        return ""
