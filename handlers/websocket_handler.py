"""
Twilio Media Streams WebSocket Handler — Low Latency Pipeline.

Implements the POC latency-reduction architecture:
- B1: Backchannel filler audio on end-of-speech
- B2: Pre-cached script node audio (no live TTS for scripted lines)
- B3: Fast intent classifier on partial transcripts
- B4: Claude fallback with sentence-streamed TTS
- B5: Async session logging (DynamoDB off critical path)
- B6: Configurable VAD / silence detection
- B7: Barge-in support (farmer can interrupt bot)
- B8: STT flush timeout reduced (fall back to partial)
- B9: Batch audio sends (no per-chunk sleep for responses)

NOTE: This pipeline runs through ngrok (POC only). Latency measurements
are "measured via ngrok tunnel" and not representative of production.
"""
import asyncio
import base64
import json
import logging
import struct
import time
import websockets

from app.config import settings
from services.audio_cache import (
    get_random_filler, get_cached_script_audio, pcm_to_mulaw
)
from services.intent_classifier import classify_partial
from services.session_manager import SessionManager
from orchestrator.graph import (
    process_turn, GREETING, COMPANY_INTRO, COMPANY_INTRO_2, ASK_CROP,
    NO_TIME_RESPONSE, THANK_YOU, get_responses
)

logger = logging.getLogger(__name__)
session_manager = SessionManager()

# VAD config — only safe to tighten because B1 filler masks the shorter window.
# SILENCE_THRESHOLD_MS from config, converted to frame count.
# Twilio sends 20ms audio chunks, so frames = ms / 20
SILENCE_FRAMES = settings.SILENCE_THRESHOLD_MS // 20  # ~12 frames at 250ms


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
            f"&sample_rate=8000"
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
                    "sample_rate": "8000",
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


def mulaw_to_pcm(mulaw_bytes: bytes) -> bytes:
    """Convert mulaw to PCM16 LE using Python audioop."""
    import audioop
    return audioop.ulaw2lin(mulaw_bytes, 2)


async def handle_media_stream(websocket):
    """
    Handle a Twilio Media Stream WebSocket connection.

    Implements: B1 (filler), B3 (intent on partial), B5 (async logging),
    B6 (tuned VAD), B7 (barge-in).

    NOTE: Measured through ngrok tunnel — POC only.
    """
    call_sid = None
    stream_sid = None
    stt = SarvamSTTStream()
    session = None
    silence_frames = 0
    speech_started = False
    is_playing = False
    early_match = None
    greeting_sent = False
    greeting_done = False
    media_packet_count = 0
    t_start = 0

    # B3: Register partial transcript callback
    def on_partial(text):
        nonlocal early_match
        if session and not early_match:
            step = session.get("step", "")
            match = classify_partial(text, step)
            if match and match["confidence"] == "high":
                early_match = match
                logger.info(f"[B3] Early match on partial: {match}")

    stt.partial_callbacks.append(on_partial)

    try:
        await stt.connect()
        stt_task = asyncio.create_task(stt.receive_loop())

        while True:
            try:
                raw = await websocket.receive_text()
            except Exception as recv_err:
                logger.error(f"[WS] receive_text error (connection closed?): {recv_err}")
                break
            data = json.loads(raw)
            event = data.get("event")

            # ── CONNECTED ─────────────────────────────────────
            if event == "connected":
                logger.info(f"[WS] Twilio connected event received: {data}")
                continue

            # ── STREAM START ──────────────────────────────────
            elif event == "start":
                start_data = data.get("start", {})
                call_sid = start_data.get("callSid", "unknown")
                stream_sid = start_data.get("streamSid", "")
                logger.info(f"[WS] Stream started: CallSid={call_sid}")
                logger.info(f"[WS] Public WSS URL: {settings.PUBLIC_WSS_URL}")

                session = session_manager.get_or_create(call_sid, "", "", "outbound-api")
                if "conversation" not in session:
                    session["conversation"] = []

                session["step"] = "ask_availability"
                session["conversation"].append({"role": "bot", "text": GREETING})
                asyncio.create_task(_async_session_update(call_sid, session))

                # Don't play greeting yet — wait for first media event
                greeting_sent = False

            # ── AUDIO DATA ────────────────────────────────────
            elif event == "media":
                payload = data.get("media", {}).get("payload", "")
                if not payload:
                    continue

                media_packet_count += 1

                # Send greeting immediately — the trial message is already
                # finished by the time Media Streams connects (farmer pressed key)
                if not greeting_sent:
                    # Wait for a few media packets to confirm call is truly connected
                    if media_packet_count < 5:
                        mulaw_bytes = base64.b64decode(payload)
                        pcm_bytes = mulaw_to_pcm(mulaw_bytes)
                        await stt.send_audio(pcm_bytes)
                        continue

                    greeting_sent = True
                    greeting_audio = get_cached_script_audio(GREETING)

                    # If not cached, generate it now
                    if not greeting_audio:
                        from services.audio_cache import _synthesize_to_mulaw
                        logger.info("[WS] Greeting not in cache, generating live...")
                        greeting_audio = await _synthesize_to_mulaw(GREETING)

                    if greeting_audio:
                        logger.info(f"[WS] Streaming greeting: {len(greeting_audio)} bytes ({len(greeting_audio)/8000:.1f}s)")

                        async def _play_greeting():
                            nonlocal greeting_done, is_playing
                            is_playing = True
                            try:
                                await _stream_audio_fast(websocket, stream_sid, greeting_audio)
                            except Exception as e:
                                logger.error(f"[WS] Greeting play error: {e}")
                            # Mark greeting as done immediately after sending
                            # (Twilio buffers and plays it; we can start listening)
                            greeting_done = True
                            is_playing = False
                            logger.info("[WS] Greeting sent to Twilio buffer")

                        asyncio.create_task(_play_greeting())
                    else:
                        logger.error("[WS] No greeting audio available!")
                        greeting_done = True

                # Keep receiving packets (keeps connection alive) but don't process audio until greeting done
                if not greeting_done:
                    # Still decode and send to STT to keep STT connection alive
                    mulaw_bytes = base64.b64decode(payload)
                    pcm_bytes = mulaw_to_pcm(mulaw_bytes)
                    await stt.send_audio(pcm_bytes)
                    continue

                mulaw_bytes = base64.b64decode(payload)
                pcm_bytes = mulaw_to_pcm(mulaw_bytes)

                # Send silence mark to keep stream alive (Twilio disconnects idle streams)
                if media_packet_count % 250 == 0:
                    await websocket.send_text(json.dumps({
                        "event": "mark",
                        "streamSid": stream_sid,
                        "mark": {"name": "keepalive"}
                    }))

                # B7: Barge-in — if farmer speaks while bot is playing, stop playback
                if is_playing:
                    max_sample = max(abs(s) for s in struct.unpack(f"<{len(pcm_bytes)//2}h", pcm_bytes))
                    if max_sample > 800:
                        is_playing = False
                        await websocket.send_text(json.dumps({
                            "event": "clear", "streamSid": stream_sid
                        }))
                        logger.info("[B7] Barge-in detected, stopped playback")
                    continue

                # Send to STT
                await stt.send_audio(pcm_bytes)

                # B6: VAD with configurable threshold
                max_sample = max(abs(s) for s in struct.unpack(f"<{len(pcm_bytes)//2}h", pcm_bytes))
                if max_sample > 500:
                    speech_started = True
                    silence_frames = 0
                elif speech_started:
                    silence_frames += 1

                # End of speech detected
                if speech_started and silence_frames >= SILENCE_FRAMES:
                    t_start = time.time()
                    speech_started = False
                    silence_frames = 0

                    # B1: Play filler immediately (fire-and-forget)
                    dialect = session.get("dialect", "marathwada") if session else "marathwada"
                    filler = get_random_filler(dialect)
                    if filler:
                        asyncio.create_task(_stream_audio_fire_and_forget(websocket, stream_sid, filler))

                    # B3/B8: Use early match OR flush STT
                    if early_match:
                        transcript = stt.partial_transcript or ""
                        logger.info(f"[B3] Using early match, skipping final STT wait")
                    else:
                        transcript = await stt.flush_and_get()

                    logger.info(f"[TIMING] STT phase: {time.time()-t_start:.3f}s")

                    if transcript and len(transcript.strip()) > 1:
                        logger.info(f"[WS] Farmer: '{transcript}'")

                        # Process through orchestrator (Claude runs in thread pool)
                        t_claude = time.time()
                        bot_reply = await process_turn(transcript, session)
                        if not bot_reply:
                            bot_reply = "सर, जरा पुन्हा सांगा."

                        logger.info(f"[TIMING] Claude phase: {time.time()-t_claude:.3f}s")
                        logger.info(f"[WS] Bot: '{bot_reply[:50]}' (total so far: {time.time()-t_start:.2f}s)")

                        # B5: Track conversation async
                        session["conversation"].append({"role": "farmer", "text": transcript})
                        session["conversation"].append({"role": "bot", "text": bot_reply})
                        asyncio.create_task(_async_session_update(call_sid, session))

                        # Play response — try B2 cache first, then generate
                        cached_audio = get_cached_script_audio(bot_reply)
                        if cached_audio:
                            logger.info(f"[B2] Playing from script cache (no TTS call)")
                            is_playing = True
                            asyncio.create_task(_stream_audio_fast(websocket, stream_sid, cached_audio))
                        else:
                            # B4: Split long responses — play first sentence immediately,
                            # generate rest in parallel for seamless playback
                            from services.audio_cache import _synthesize_to_mulaw
                            t_tts = time.time()

                            # Split at first sentence boundary for faster first-byte
                            import re
                            sentences = re.split(r'(?<=[\.\?!।])\s*', bot_reply, maxsplit=1)

                            if len(sentences) > 1 and len(sentences[0]) > 10:
                                # Generate first sentence and rest in parallel
                                first_audio, rest_audio = await asyncio.gather(
                                    _synthesize_to_mulaw(sentences[0]),
                                    _synthesize_to_mulaw(sentences[1])
                                )
                                audio = first_audio + rest_audio if rest_audio else first_audio
                            else:
                                audio = await _synthesize_to_mulaw(bot_reply)

                            logger.info(f"[WS] TTS took: {time.time()-t_tts:.2f}s")
                            if audio:
                                is_playing = True
                                asyncio.create_task(_stream_audio_fast(websocket, stream_sid, audio))

                        logger.info(f"[WS] Turn complete: {time.time()-t_start:.2f}s "
                                    f"({'cached' if cached_audio else 'generated'}) "
                                    f"[measured via ngrok tunnel, POC only]")

                        # Check if call should end
                        if session.get("should_close"):
                            asyncio.create_task(_async_session_end(call_sid))
                            break

                    # Reset early match for next turn
                    early_match = None

            # ── STREAM STOP ───────────────────────────────────
            elif event == "stop":
                logger.info(f"[WS] Stream stopped: {call_sid}")
                break

    except Exception as e:
        logger.error(f"[WS] Error: {e}")
    finally:
        await stt.close()
        if call_sid:
            asyncio.create_task(_async_session_end(call_sid))


async def _stream_audio(websocket, stream_sid: str, mulaw_audio: bytes):
    """
    Stream mulaw audio to Twilio with pacing.
    Must pace at real-time or slightly faster so Twilio's buffer doesn't overflow.
    Without pacing, the entire audio is dumped in ms and may cause issues.
    """
    CHUNK_SIZE = 160  # 160 bytes = 20ms at 8kHz mulaw
    for i in range(0, len(mulaw_audio), CHUNK_SIZE):
        chunk = mulaw_audio[i:i + CHUNK_SIZE]
        payload = base64.b64encode(chunk).decode()
        await websocket.send_text(json.dumps({
            "event": "media",
            "streamSid": stream_sid,
            "media": {
                "payload": payload,
            }
        }))
        # Pace at real-time (20ms per chunk) for reliable playback over ngrok
        await asyncio.sleep(0.018)


async def _stream_audio_fast(websocket, stream_sid: str, mulaw_audio: bytes):
    """
    B9: Stream audio to Twilio in larger batches with minimal pacing.
    Twilio buffers incoming media and plays it sequentially.
    Small sleep every few chunks prevents buffer overflow.
    """
    CHUNK_SIZE = 640  # 640 bytes = 80ms at 8kHz mulaw (4x fewer sends)
    try:
        for i in range(0, len(mulaw_audio), CHUNK_SIZE):
            chunk = mulaw_audio[i:i + CHUNK_SIZE]
            payload = base64.b64encode(chunk).decode()
            await websocket.send_text(json.dumps({
                "event": "media",
                "streamSid": stream_sid,
                "media": {"payload": payload}
            }))
            # Minimal pacing: yield every 10 chunks (~800ms of audio) to let event loop breathe
            if (i // CHUNK_SIZE) % 10 == 9:
                await asyncio.sleep(0.001)
    except Exception as e:
        logger.error(f"[WS] Fast audio stream error: {e}")


async def _stream_audio_fire_and_forget(websocket, stream_sid: str, mulaw_audio: bytes):
    """B1: Stream filler audio without blocking main pipeline."""
    try:
        await _stream_audio_fast(websocket, stream_sid, mulaw_audio)
    except Exception:
        pass


# B5: Async session logging — never blocks the response path
async def _async_session_update(call_sid: str, session: dict):
    """Update session in background."""
    try:
        session_manager.update(call_sid, session)
    except Exception as e:
        logger.error(f"[B5] Async session update error: {e}")


async def _async_session_end(call_sid: str):
    """End session in background."""
    try:
        session_manager.end_session(call_sid)
    except Exception as e:
        logger.error(f"[B5] Async session end error: {e}")

async def _stream_audio_then_clear(websocket, stream_sid, audio, callback):
    """Stream audio then call callback. Safely handles closed connections."""
    try:
        await _stream_audio(websocket, stream_sid, audio)
        if callback:
            callback()
    except Exception as e:
        # Connection may have closed during streaming — this is expected
        logger.error(f"[WS] Greeting stream error: {e}")
