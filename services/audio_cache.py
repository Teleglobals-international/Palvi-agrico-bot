"""
B1 + B2 — Filler audio and pre-cached script node audio.

B1: Short acknowledgment clips played immediately on end-of-speech
    while the real response is being generated.
B2: Pre-synthesized audio for all fixed script lines, keyed by
    node ID and dialect. Never call TTS live for these.
"""
import base64
import hashlib
import random
import logging
import struct
import httpx

from app.config import settings

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════
# B1 — Filler audio clips (pre-synthesized, never generated live)
# ═══════════════════════════════════════════════════════════════
FILLER_TEXTS = {
    "marathwada": ["हा", "बरं", "हम्म"],
    "vidarbha": ["हा", "बरं शे", "हम्म"],
}

# Stores filler audio as mulaw bytes ready to stream
_filler_cache: dict[str, list[bytes]] = {"marathwada": [], "vidarbha": []}

# ═══════════════════════════════════════════════════════════════
# B2 — Script node audio cache
# ═══════════════════════════════════════════════════════════════
# Stores pre-synthesized audio as mulaw bytes, keyed by text hash
_script_audio_cache: dict[str, bytes] = {}


def _pcm_to_mulaw_byte(sample: int) -> int:
    """Convert a single PCM16 sample to mulaw."""
    sign = 0
    if sample < 0:
        sign = 0x80
        sample = -sample
    sample = min(sample, 32635)
    sample += 132
    exponent = 7
    for exp in range(7, 0, -1):
        if sample & (1 << (exp + 3)):
            exponent = exp
            break
    mantissa = (sample >> (exponent + 3)) & 0x0F
    return ~(sign | (exponent << 4) | mantissa) & 0xFF


def pcm_to_mulaw(pcm_bytes: bytes) -> bytes:
    """Convert PCM16 LE bytes to mulaw for Twilio.
    audioop.lin2ulaw produces standard G.711 mulaw.
    Twilio also uses standard G.711 — no bit inversion needed.
    """
    import audioop
    # Ensure even number of bytes (16-bit samples)
    if len(pcm_bytes) % 2 != 0:
        pcm_bytes = pcm_bytes[:-1]
    return audioop.lin2ulaw(pcm_bytes, 2)


def _extract_pcm_from_wav(wav_bytes: bytes) -> bytes:
    """Properly parse WAV file and extract raw PCM data."""
    if wav_bytes[:4] != b'RIFF':
        return wav_bytes  # Not a WAV, return as-is

    # Find the 'data' chunk
    pos = 12  # Skip RIFF header (12 bytes)
    while pos < len(wav_bytes) - 8:
        chunk_id = wav_bytes[pos:pos+4]
        chunk_size = struct.unpack('<I', wav_bytes[pos+4:pos+8])[0]
        if chunk_id == b'data':
            return wav_bytes[pos+8:pos+8+chunk_size]
        pos += 8 + chunk_size
        # Align to even boundary
        if chunk_size % 2:
            pos += 1

    # Fallback: skip first 44 bytes
    return wav_bytes[44:]


async def _synthesize_to_mulaw(text: str) -> bytes:
    """Synthesize text to mulaw audio bytes via Sarvam TTS."""
    try:
        # Longer texts need more time
        timeout = 10.0 if len(text) > 150 else 6.0
        async with httpx.AsyncClient(timeout=timeout) as client:
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
                if audios:
                    audio_bytes = base64.b64decode(audios[0])
                    # Properly parse WAV to extract PCM data
                    pcm_data = _extract_pcm_from_wav(audio_bytes)
                    return pcm_to_mulaw(pcm_data)
    except Exception as e:
        logger.error(f"[AUDIO_CACHE] TTS error: {e}")
    return b""


async def init_filler_audio():
    """Pre-synthesize filler clips at startup. Call once."""
    logger.info("[B1] Pre-synthesizing filler audio clips...")
    for dialect, texts in FILLER_TEXTS.items():
        for text in texts:
            mulaw = await _synthesize_to_mulaw(text)
            if mulaw:
                _filler_cache[dialect].append(mulaw)
    logger.info(f"[B1] Filler audio ready: {sum(len(v) for v in _filler_cache.values())} clips")


def get_random_filler(dialect: str = "marathwada") -> bytes:
    """Get a random filler clip for immediate playback. Non-blocking."""
    clips = _filler_cache.get(dialect, _filler_cache.get("marathwada", []))
    if clips:
        return random.choice(clips)
    return b""


async def cache_script_node(text: str) -> str:
    """Pre-synthesize and cache a script node's audio. Returns the cache key."""
    key = hashlib.md5(text.encode()).hexdigest()
    if key not in _script_audio_cache:
        mulaw = await _synthesize_to_mulaw(text)
        if mulaw:
            _script_audio_cache[key] = mulaw
            logger.info(f"[B2] Cached script node: '{text[:30]}...' ({len(mulaw)} bytes)")
    return key


def get_cached_script_audio(text: str) -> bytes | None:
    """Get pre-cached mulaw audio for a script line. Returns None if not cached."""
    key = hashlib.md5(text.encode()).hexdigest()
    return _script_audio_cache.get(key)


async def init_script_cache(texts: list[str]):
    """Pre-cache a list of script texts at startup."""
    logger.info(f"[B2] Pre-caching {len(texts)} script nodes...")
    for text in texts:
        await cache_script_node(text)
    logger.info("[B2] Script cache ready!")
