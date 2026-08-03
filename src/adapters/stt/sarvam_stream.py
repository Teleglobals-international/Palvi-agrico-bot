"""
Sarvam STT Streaming Client — WebSocket-based speech-to-text.

Supports partial/interim transcripts for B3 (early intent classification)
and final transcripts with flush timeout fallback (B8).
"""
import asyncio
import base64
import json
import logging
import websockets

from src.config.settings import settings

logger = logging.getLogger(__name__)

# Exotel audio config
SAMPLE_RATE = settings.EXOTEL_SAMPLE_RATE  # 8000 Hz default


class SarvamSTTStream:
    """WebSocket client for Sarvam streaming STT (B3 partial + final)."""

    def __init__(self):
        self.ws = None
        self.transcript = ""
        self.partial_transcript = ""
        self.final_received = asyncio.Event()
        self.partial_callbacks = []  # Callbacks for partial transcripts (B3)

    async def connect(self):
        """Connect to Sarvam STT WebSocket."""
        url = (
            f"wss://api.sarvam.ai/speech-to-text/ws"
            f"?language-code=mr-IN"
            f"&model=saaras:v3"
            f"&mode=transcribe"
            f"&sample_rate={SAMPLE_RATE}"
            f"&input_audio_codec=pcm_s16le"
        )
        headers = {"Api-Subscription-Key": settings.SARVAM_API_KEY}
        self.ws = await websockets.connect(url, additional_headers=headers)
        logger.info("[STT] Connected to Sarvam STT WebSocket")

    async def send_audio(self, pcm_bytes: bytes):
        """Send PCM audio chunk to Sarvam STT."""
        if self.ws:
            audio_b64 = base64.b64encode(pcm_bytes).decode()
            await self.ws.send(json.dumps({
                "audio": {
                    "data": audio_b64,
                    "sample_rate": str(SAMPLE_RATE),
                    "encoding": "pcm_s16le"
                }
            }))

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

                # Sarvam may send partial/interim results
                elif msg_type == "partial" or msg_type == "interim":
                    partial = data.get("data", {}).get("transcript", "")
                    if partial:
                        self.partial_transcript = partial
                        # Notify B3 classifier about partial transcript
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
                # Reduced timeout: partial transcript is usually good enough
                await asyncio.wait_for(self.final_received.wait(), timeout=1.2)
            except asyncio.TimeoutError:
                # Use partial if final didn't arrive in time
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
        if self.ws:
            await self.ws.close()
