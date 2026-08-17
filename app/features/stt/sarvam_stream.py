"""
Sarvam STT Streaming Client — WebSocket-based speech-to-text.
Supports partial/interim transcripts and final transcripts with flush timeout fallback.
Language: English (en-IN) for all 3 industry agents.
"""

import asyncio
import base64
import json
import logging

import websockets

from app.config import get_settings

logger = logging.getLogger(__name__)


class SarvamSTTStream:
    """WebSocket client for Sarvam streaming STT (partial + final)."""

    def __init__(self, language_code: str = "en-IN"):
        self.ws = None
        self.transcript = ""
        self.partial_transcript = ""
        self.final_received = asyncio.Event()
        self.partial_callbacks = []
        self._language_code = language_code

    async def connect(self):
        """Connect to Sarvam STT WebSocket."""
        settings = get_settings()
        sample_rate = settings.exotel_sample_rate

        url = (
            f"wss://api.sarvam.ai/speech-to-text/ws"
            f"?language-code={self._language_code}"
            f"&model=saaras:v3"
            f"&mode=transcribe"
            f"&sample_rate={sample_rate}"
            f"&input_audio_codec=pcm_s16le"
        )

        headers = {"api-subscription-key": settings.sarvam_api_key}
        try:
            self.ws = await websockets.connect(url, additional_headers=headers)
            logger.info("[STT] Connected to Sarvam STT WebSocket")
        except Exception as e:
            logger.error(f"[STT] Failed to connect: {e}")
            self.ws = None

    async def send_audio(self, pcm_bytes: bytes):
        """Send PCM audio chunk to Sarvam STT."""
        if not self.ws:
            return
        try:
            settings = get_settings()
            audio_b64 = base64.b64encode(pcm_bytes).decode()
            await self.ws.send(json.dumps({
                "audio": {
                    "data": audio_b64,
                    "sample_rate": str(settings.exotel_sample_rate),
                    "encoding": "pcm_s16le",
                }
            }))
        except Exception as e:
            logger.error(f"[STT] Send audio error: {e}")
            self.ws = None

    async def receive_loop(self):
        """Listen for transcription results (partial + final)."""
        try:
            async for message in self.ws:
                data = json.loads(message)
                msg_type = data.get("type", "")

                if msg_type == "data":
                    transcript = data.get("data", {}).get("transcript", "")
                    if transcript:
                        self.transcript = transcript
                        self.final_received.set()
                        logger.info(f"[STT] Final: '{transcript}'")

                elif msg_type in ("partial", "interim"):
                    partial = data.get("data", {}).get("transcript", "")
                    if partial:
                        self.partial_transcript = partial
                        for cb in self.partial_callbacks:
                            cb(partial)

        except websockets.exceptions.ConnectionClosed:
            logger.info("[STT] Connection closed")
        except Exception as e:
            logger.error(f"[STT] Receive error: {e}")

    async def flush_and_get(self) -> str:
        """Flush buffer and wait for final transcript. Falls back to partial on timeout."""
        if self.ws:
            try:
                await self.ws.send(json.dumps({"flush": True}))
                await asyncio.wait_for(self.final_received.wait(), timeout=1.2)
            except asyncio.TimeoutError:
                if self.partial_transcript:
                    logger.info(f"[STT] Timeout, using partial: '{self.partial_transcript}'")
                    result = self.partial_transcript
                    self.transcript = ""
                    self.partial_transcript = ""
                    self.final_received.clear()
                    return result
            except Exception:
                pass

        result = self.transcript or self.partial_transcript
        self.transcript = ""
        self.partial_transcript = ""
        self.final_received.clear()
        return result

    async def close(self):
        """Close the STT WebSocket connection."""
        if self.ws:
            await self.ws.close()
