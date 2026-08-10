"""
Twilio Media Streams WebSocket Handler — Low Latency Pipeline.

Implements the same POC latency-reduction architecture as the Exotel handler:
- B1: Backchannel filler audio on end-of-speech
- B2: Pre-cached script node audio (no live TTS for scripted lines)
- B3: Fast intent classifier on partial transcripts
- B4: Claude fallback with sentence-streamed TTS
- B5: Async session logging (DynamoDB off critical path)
- B6: Configurable VAD / silence detection
- B7: Barge-in support (farmer can interrupt bot)
- B8: STT flush timeout reduced (fall back to partial)
- B9: Batch audio sends (minimal pacing — Twilio buffers well)

Twilio Media Streams protocol:
- Events from Twilio: connected, start, media, stop
- Audio in: base64 mulaw 8kHz mono (160 bytes = 20ms per chunk)
- Audio out: base64 mulaw frames via {"event": "media", "streamSid": ..., "media": {"payload": ...}}
- Clear playback: {"event": "clear", "streamSid": ...}
- Keepalive mark: {"event": "mark", "streamSid": ..., "mark": {"name": "keepalive"}}

KEY DIFFERENCE FROM EXOTEL:
- Twilio sends mulaw (not PCM16) — needs audioop.ulaw2lin for STT input
- Twilio receives mulaw back — our cache already stores mulaw, so no conversion needed for output
"""
import asyncio
import audioop
import base64
import json
import logging
import struct
import time

from src.config.settings import settings
from src.adapters.tts.audio_cache import (
    get_random_filler, get_cached_script_audio, _synthesize_to_mulaw,
)
from src.adapters.stt.intent_classifier import classify_partial
from src.adapters.stt.sarvam_stream import SarvamSTTStream
from src.infra.db.session_manager import SessionManager
from src.core.callFlow.state_machine import process_turn
from src.core.callFlow.scripts import (
    GREETING, COMPANY_INTRO, COMPANY_INTRO_2, ASK_CROP,
    NO_TIME_RESPONSE, THANK_YOU, get_responses,
)

logger = logging.getLogger(__name__)
session_manager = SessionManager()

# VAD config — same threshold as Exotel handler.
# Twilio sends 20ms mulaw chunks at 8kHz (160 bytes per chunk)
SILENCE_FRAMES = settings.SILENCE_THRESHOLD_MS // 20  # ~12 frames at 250ms

# Twilio audio config
SAMPLE_RATE = 8000  # Twilio Media Streams always 8kHz mulaw
MULAW_FRAME_BYTES = 160  # 20ms of mulaw at 8kHz (1 byte per sample)

# Output chunk size: 640 bytes = 80ms of mulaw (4x fewer sends than 160-byte chunks)
OUTPUT_CHUNK_SIZE = 640


def mulaw_to_pcm(mulaw_bytes: bytes) -> bytes:
    """Convert mulaw audio to PCM16 LE for STT processing."""
    return audioop.ulaw2lin(mulaw_bytes, 2)


async def handle_twilio_media_stream(websocket):
    """
    Handle a Twilio Media Streams WebSocket connection.

    Protocol:
    - Events: connected, start, media, stop
    - Audio in: base64 mulaw 8kHz mono
    - Audio out: base64 mulaw frames

    Implements: B1 (filler), B3 (intent on partial), B5 (async logging),
    B6 (tuned VAD), B7 (barge-in).
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
                logger.error(f"[WS-Twilio] receive_text error (connection closed?): {recv_err}")
                break
            data = json.loads(raw)
            event = data.get("event")

            # Only log non-media events to avoid spam
            if event != "media":
                logger.info(f"[WS-Twilio] Event received: {event}")

            # ── CONNECTED ─────────────────────────────────────
            if event == "connected":
                logger.info(f"[WS-Twilio] Connected event: {data}")
                continue

            # ── STREAM START ──────────────────────────────────
            elif event == "start":
                start_data = data.get("start", {})
                call_sid = start_data.get("callSid", "unknown")
                stream_sid = start_data.get("streamSid", "")

                logger.info(f"[WS-Twilio] Stream started: CallSid={call_sid}, StreamSid={stream_sid}")

                # Parse custom parameters if provided
                custom_params = start_data.get("customParameters", {})
                dialect = custom_params.get("dialect", "marathwada") if custom_params else "marathwada"

                session = session_manager.get_or_create(call_sid, "", "", "outbound-api")
                if "conversation" not in session:
                    session["conversation"] = []

                session["step"] = "ask_availability"
                session["dialect"] = dialect
                session["conversation"].append({"role": "bot", "text": GREETING})
                asyncio.create_task(_async_session_update(call_sid, session))

                # Don't play greeting yet — wait for first media event
                greeting_sent = False

            # ── AUDIO DATA ────────────────────────────────────
            elif event == "media":
                media_data = data.get("media", {})
                payload = media_data.get("payload", "")

                if not payload:
                    continue

                media_packet_count += 1

                # Twilio sends mulaw — decode and convert to PCM for STT
                mulaw_bytes = base64.b64decode(payload)
                pcm_bytes = mulaw_to_pcm(mulaw_bytes)

                # Send greeting after a few packets confirm the call is connected
                if not greeting_sent:
                    if media_packet_count < 5:
                        await stt.send_audio(pcm_bytes)
                        continue

                    greeting_sent = True
                    greeting_audio = get_cached_script_audio(GREETING)

                    # If not cached, generate it now
                    if not greeting_audio:
                        logger.info("[WS-Twilio] Greeting not in cache, generating live...")
                        greeting_audio = await _synthesize_to_mulaw(GREETING)

                    if greeting_audio:
                        logger.info(
                            f"[WS-Twilio] Streaming greeting: {len(greeting_audio)} bytes mulaw "
                            f"({len(greeting_audio) / SAMPLE_RATE:.1f}s)"
                        )

                        async def _play_greeting():
                            nonlocal is_playing
                            is_playing = True
                            try:
                                await _stream_mulaw_to_twilio(websocket, stream_sid, greeting_audio)
                            except Exception as e:
                                logger.error(f"[WS-Twilio] Greeting play error: {e}")
                            is_playing = False
                            logger.info("[WS-Twilio] Greeting streaming complete")

                        asyncio.create_task(_play_greeting())
                        greeting_done = True
                    else:
                        logger.error("[WS-Twilio] No greeting audio available!")
                        greeting_done = True

                # Keep receiving packets but don't process audio until greeting done
                if not greeting_done:
                    await stt.send_audio(pcm_bytes)
                    continue

                # B7: Barge-in — if farmer speaks while bot is playing, stop playback
                if is_playing:
                    # Check amplitude on PCM (converted from mulaw)
                    max_sample = max(abs(s) for s in struct.unpack(f"<{len(pcm_bytes)//2}h", pcm_bytes))
                    if max_sample > 800:
                        is_playing = False
                        # Twilio supports "clear" event to stop playback
                        await websocket.send_text(json.dumps({
                            "event": "clear", "streamSid": stream_sid
                        }))
                        logger.info("[B7] Barge-in detected, stopped playback")
                    continue

                # Send PCM to STT
                await stt.send_audio(pcm_bytes)

                # B6: VAD with configurable threshold (check on PCM samples)
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
                        # Filler is already mulaw — send directly to Twilio
                        asyncio.create_task(_stream_mulaw_fire_and_forget(websocket, stream_sid, filler))

                    # B3/B8: Use early match OR flush STT
                    if early_match:
                        transcript = stt.partial_transcript or ""
                        logger.info(f"[B3] Using early match, skipping final STT wait")
                    else:
                        transcript = await stt.flush_and_get()

                    logger.info(f"[TIMING] STT phase: {time.time()-t_start:.3f}s")

                    if transcript and len(transcript.strip()) > 1:
                        logger.info(f"[WS-Twilio] Farmer: '{transcript}'")

                        # Process through orchestrator (Claude runs in thread pool)
                        t_claude = time.time()
                        bot_reply = await process_turn(transcript, session)
                        if not bot_reply:
                            bot_reply = "सर, जरा पुन्हा सांगा."

                        logger.info(f"[TIMING] Claude phase: {time.time()-t_claude:.3f}s")
                        logger.info(f"[WS-Twilio] Bot: '{bot_reply[:50]}' (total so far: {time.time()-t_start:.2f}s)")

                        # B5: Track conversation async
                        session["conversation"].append({"role": "farmer", "text": transcript})
                        session["conversation"].append({"role": "bot", "text": bot_reply})
                        asyncio.create_task(_async_session_update(call_sid, session))

                        # Play response — try B2 cache first, then generate
                        cached_audio = get_cached_script_audio(bot_reply)
                        if cached_audio:
                            logger.info(f"[B2] Playing from script cache (no TTS call)")
                            is_playing = True
                            # Cache is mulaw — send directly to Twilio
                            asyncio.create_task(_stream_mulaw_to_twilio(websocket, stream_sid, cached_audio))
                        else:
                            # B4: Split long responses — play first sentence immediately
                            t_tts = time.time()

                            import re
                            sentences = re.split(r'(?<=[\.\?!।])\s*', bot_reply, maxsplit=1)

                            if len(sentences) > 1 and len(sentences[0]) > 10:
                                first_audio, rest_audio = await asyncio.gather(
                                    _synthesize_to_mulaw(sentences[0]),
                                    _synthesize_to_mulaw(sentences[1])
                                )
                                audio = first_audio + rest_audio if rest_audio else first_audio
                            else:
                                audio = await _synthesize_to_mulaw(bot_reply)

                            logger.info(f"[WS-Twilio] TTS took: {time.time()-t_tts:.2f}s")
                            if audio:
                                is_playing = True
                                # audio is mulaw — send directly to Twilio
                                asyncio.create_task(_stream_mulaw_to_twilio(websocket, stream_sid, audio))

                        logger.info(f"[WS-Twilio] Turn complete: {time.time()-t_start:.2f}s "
                                    f"({'cached' if cached_audio else 'generated'})")

                        # Check if call should end
                        if session.get("should_close"):
                            asyncio.create_task(_async_session_end(call_sid))
                            break

                    # Reset early match for next turn
                    early_match = None

            # ── STREAM STOP ───────────────────────────────────
            elif event == "stop":
                logger.info(f"[WS-Twilio] Stream stopped: {call_sid}")
                break

    except Exception as e:
        logger.error(f"[WS-Twilio] Error: {e}")
    finally:
        await stt.close()
        if call_sid:
            asyncio.create_task(_async_session_end(call_sid))


async def _stream_mulaw_to_twilio(websocket, stream_sid: str, mulaw_bytes: bytes):
    """
    Stream mulaw audio to Twilio Media Streams.

    Twilio accepts mulaw directly — no PCM conversion needed.
    Sends in 640-byte chunks (80ms) with minimal pacing since Twilio buffers well.
    """
    try:
        chunk_count = 0
        for i in range(0, len(mulaw_bytes), OUTPUT_CHUNK_SIZE):
            chunk = mulaw_bytes[i:i + OUTPUT_CHUNK_SIZE]
            payload = base64.b64encode(chunk).decode()
            await websocket.send_text(json.dumps({
                "event": "media",
                "streamSid": stream_sid,
                "media": {"payload": payload}
            }))
            chunk_count += 1

            # Minimal pacing — Twilio buffers internally
            if chunk_count % 10 == 0:
                await asyncio.sleep(0.001)

        # Send a mark to track when playback finishes
        await websocket.send_text(json.dumps({
            "event": "mark",
            "streamSid": stream_sid,
            "mark": {"name": "keepalive"}
        }))
    except Exception as e:
        logger.error(f"[WS-Twilio] Audio stream error: {e}")


async def _stream_mulaw_fire_and_forget(websocket, stream_sid: str, mulaw_bytes: bytes):
    """B1: Stream filler audio without blocking main pipeline."""
    try:
        await _stream_mulaw_to_twilio(websocket, stream_sid, mulaw_bytes)
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
