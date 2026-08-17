"""
Sarvam AI TTS — Text-to-Speech for multi-tenant calling agents.
Speaker: meera (English, professional)
Model: bulbul:v3
Output: PCM16 8kHz mono (phone quality)
"""

import audioop
import base64
import logging
import struct
from typing import Optional

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)

# TTS Configuration for English professional voice
TTS_CONFIG = {
    "model": "bulbul:v3",
    "speaker": "priya",
    "target_language_code": "en-IN",
    "pace": 0.95,
    "speech_sample_rate": 8000,
}


def _extract_pcm_from_wav(wav_bytes: bytes) -> bytes:
    """Properly parse WAV file and extract raw PCM data."""
    if wav_bytes[:4] != b'RIFF':
        return wav_bytes  # Not a WAV, return as-is

    # Find the 'data' chunk
    pos = 12  # Skip RIFF header (12 bytes)
    while pos < len(wav_bytes) - 8:
        chunk_id = wav_bytes[pos:pos + 4]
        chunk_size = struct.unpack('<I', wav_bytes[pos + 4:pos + 8])[0]

        if chunk_id == b'data':
            return wav_bytes[pos + 8:pos + 8 + chunk_size]

        pos += 8 + chunk_size
        # Align to even boundary
        if chunk_size % 2:
            pos += 1

    # Fallback: skip first 44 bytes
    return wav_bytes[44:]


def pcm_to_mulaw(pcm_bytes: bytes) -> bytes:
    """Convert PCM16 LE bytes to mulaw (G.711)."""
    if len(pcm_bytes) % 2 != 0:
        pcm_bytes = pcm_bytes[:-1]
    return audioop.lin2ulaw(pcm_bytes, 2)


def mulaw_to_pcm(mulaw_bytes: bytes) -> bytes:
    """Convert mulaw audio to Linear PCM 16-bit for Exotel output."""
    return audioop.ulaw2lin(mulaw_bytes, 2)


class SarvamTTS:
    """Sarvam AI Text-to-Speech client for generating voice audio."""

    def __init__(self):
        settings = get_settings()
        self._api_key = settings.sarvam_api_key
        self._tts_url = settings.sarvam_tts_url

    async def synthesize_to_pcm(self, text: str) -> Optional[bytes]:
        """
        Synthesize text to PCM16 audio bytes ready for Exotel streaming.

        Args:
            text: Text to convert to speech.

        Returns:
            PCM16 audio bytes, or None on failure.
        """
        if not text or not self._api_key:
            return None

        if len(text) > 2000:
            text = text[:2000]

        try:
            timeout = 10.0 if len(text) > 150 else 6.0

            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(
                    self._tts_url,
                    headers={
                        "Content-Type": "application/json",
                        "api-subscription-key": self._api_key,
                    },
                    json={
                        "inputs": [text],
                        "target_language_code": TTS_CONFIG["target_language_code"],
                        "model": TTS_CONFIG["model"],
                        "speaker": TTS_CONFIG["speaker"],
                        "pace": TTS_CONFIG["pace"],
                        "speech_sample_rate": TTS_CONFIG["speech_sample_rate"],
                    },
                )

                if response.status_code == 200:
                    result = response.json()
                    audios = result.get("audios", [])

                    if not audios:
                        logger.warning("[TTS] No audio in response")
                        return None

                    audio_bytes = base64.b64decode(audios[0])

                    if len(audio_bytes) < 500:
                        logger.warning("[TTS] Audio too small")
                        return None

                    # Extract PCM from WAV
                    pcm_data = _extract_pcm_from_wav(audio_bytes)
                    logger.info(f"[TTS] Generated: {len(pcm_data)} bytes PCM")
                    return pcm_data

                else:
                    logger.error(
                        f"[TTS] HTTP {response.status_code}: {response.text[:200]}"
                    )
                    return None

        except Exception as e:
            logger.error(f"[TTS] Error: {e}")
            return None

    async def synthesize_to_mulaw(self, text: str) -> Optional[bytes]:
        """
        Synthesize text to mulaw audio bytes (for caching).

        Args:
            text: Text to convert to speech.

        Returns:
            Mulaw audio bytes, or None on failure.
        """
        pcm = await self.synthesize_to_pcm(text)
        if pcm:
            return pcm_to_mulaw(pcm)
        return None
