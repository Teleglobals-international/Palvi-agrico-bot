"""
Exotel Voicebot Applet WebSocket Handler — Low Latency Pipeline.

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

Exotel Voicebot Applet protocol:
- Events from Exotel: connected, start, media, dtmf, stop
- Audio in: base64 Linear PCM 16-bit, 8kHz mono (little-endian)
- Audio out: base64 PCM or PCMU, ~100ms frames, multiples of 320 bytes

NOTE: This pipeline runs through ngrok (POC only). Latency measurements
are "measured via ngrok tunnel" and not representative of production.
"""
import asyncio
import base64
import json
import logging
import struct
import time

from src.config.settings import settings
from src.adapters.tts.audio_cache import (
    get_random_filler, get_cached_script_audio, pcm_to_mulaw,
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

# VAD config — only safe to tighten because B1 filler masks the shorter window.
# Exotel sends 20ms audio chunks at 8kHz PCM16 (320 bytes per chunk)
# SILENCE_THRESHOLD_MS from config, converted to frame count.
SILENCE_FRAMES = settings.SILENCE_THRESHOLD_MS // 20  # ~12 frames at 250ms

# Exotel audio config
SAMPLE_RATE = settings.EXOTEL_SAMPLE_RATE  # 8000 Hz default
BYTES_PER_SAMPLE = 2  # 16-bit PCM
# Frame size for 20ms at configured sample rate
FRAME_BYTES = (SAMPLE_RATE * BYTES_PER_SAMPLE * 20) // 1000  # 320 bytes at 8kHz


def pcm_to_pcmu(pcm_bytes: bytes) -> bytes:
    """
    Convert Linear PCM 16-bit to mu-law (PCMU) for Exotel output.

    Exotel accepts both PCM and PCMU. PCMU is half the bandwidth (8 bits vs 16)
    and is preferred for PSTN efficiency.
    """
    import audioop
    return audioop.lin2ulaw(pcm_bytes, 2)


async def handle_media_stream(websocket):
    """
    Handle an Exotel Voicebot Applet WebSocket connection.

    Protocol is similar to Twilio Media Streams:
    - Events: connected, start, media, dtmf, stop
    - Audio in: base64 PCM16 8kHz mono
    - Audio out: base64 PCM/PCMU frames

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

            # Only log non-media events to avoid spam
            if event != "media":
                logger.info(f"[WS] Event received: {event} | Keys: {list(data.keys())}")

            # ── CONNECTED ─────────────────────────────────────
            if event == "connected":
                logger.info(f"[WS] Exotel connected event received: {data}")
                continue

            # ── STREAM START ──────────────────────────────────
            elif event == "start":
                start_data = data.get("start", {})
                # Exotel puts stream_sid at top level AND inside start
                call_sid = start_data.get("call_sid", start_data.get("callSid", data.get("call_sid", "unknown")))
                stream_sid = data.get("stream_sid", start_data.get("stream_sid", start_data.get("streamSid", "")))
                custom_params = start_data.get("custom_parameters", data.get("custom_parameters", ""))

                logger.info(f"[WS] Stream started: CallSid={call_sid}, StreamSid={stream_sid}")
                logger.info(f"[WS] Custom params: {custom_params}")
                logger.info(f"[WS] Public WSS URL: {settings.PUBLIC_WSS_URL}")

                # Parse dialect from custom_parameters
                dialect = "marathwada"
                if custom_params:
                    if isinstance(custom_params, dict):
                        # Already a dict
                        dialect = custom_params.get("dialect", "marathwada")
                    elif isinstance(custom_params, str):
                        # Query string format: "dialect=marathwada&key=value"
                        from urllib.parse import parse_qs
                        parsed = parse_qs(custom_params)
                        dialect = parsed.get("dialect", ["marathwada"])[0]

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
                payload = media_data.get("payload", "") if isinstance(media_data, dict) else ""

                # Log first media packet structure for debugging
                if media_packet_count == 0:
                    logger.info(f"[WS] First media packet keys: {list(data.keys())}")
                    logger.info(f"[WS] Media field type: {type(media_data)}, keys: {list(media_data.keys()) if isinstance(media_data, dict) else 'N/A'}")
                    if payload:
                        raw_audio = base64.b64decode(payload)
                        logger.info(f"[WS] First audio chunk: {len(raw_audio)} bytes")

                if not payload:
                    continue

                media_packet_count += 1

                # Exotel sends Linear PCM 16-bit directly (no mulaw conversion needed)
                pcm_bytes = base64.b64decode(payload)

                # Send greeting after a few packets confirm the call is connected
                if not greeting_sent:
                    if media_packet_count < 5:
                        await stt.send_audio(pcm_bytes)
                        continue

                    greeting_sent = True
                    greeting_audio = get_cached_script_audio(GREETING)

                    # If not cached, generate it now
                    if not greeting_audio:
                        from src.adapters.tts.audio_cache import _synthesize_to_mulaw
                        logger.info("[WS] Greeting not in cache, generating live...")
                        greeting_audio = await _synthesize_to_mulaw(GREETING)

                    if greeting_audio:
                        # Convert mulaw cache to PCM for Exotel output
                        output_audio = _mulaw_to_pcm_for_output(greeting_audio)
                        logger.info(
                            f"[WS] Streaming greeting: {len(output_audio)} bytes "
                            f"({len(output_audio) / (SAMPLE_RATE * BYTES_PER_SAMPLE):.1f}s)"
                        )

                        async def _play_greeting():
                            nonlocal is_playing
                            is_playing = True
                            try:
                                await _stream_audio_fast(websocket, stream_sid, output_audio)
                            except Exception as e:
                                logger.error(f"[WS] Greeting play error: {e}")
                            is_playing = False
                            logger.info("[WS] Greeting streaming complete")

                        asyncio.create_task(_play_greeting())
                        # Mark greeting done immediately — start listening for farmer
                        # while Exotel buffers and plays the greeting audio
                        greeting_done = True
                    else:
                        logger.error("[WS] No greeting audio available!")
                        greeting_done = True

                # Keep receiving packets but don't process audio until greeting done
                if not greeting_done:
                    await stt.send_audio(pcm_bytes)
                    continue

                # B7: Barge-in — if farmer speaks while bot is playing, stop playback
                if is_playing:
                    max_sample = max(abs(s) for s in struct.unpack(f"<{len(pcm_bytes)//2}h", pcm_bytes))
                    if max_sample > 800:
                        is_playing = False
                        # Exotel supports "clear" event to stop playback
                        await websocket.send_text(json.dumps({
                            "event": "clear", "streamSid": stream_sid
                        }))
                        logger.info("[B7] Barge-in detected, stopped playback")
                    continue

                # Send to STT (already PCM, no conversion needed)
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
                        # Convert mulaw filler to PCM16 for Exotel
                        filler_pcm = _mulaw_to_pcm_for_output(filler)
                        asyncio.create_task(_stream_audio_fire_and_forget(websocket, stream_sid, filler_pcm))

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
                            output_audio = _mulaw_to_pcm_for_output(cached_audio)
                            asyncio.create_task(_stream_audio_fast(websocket, stream_sid, output_audio))
                        else:
                            # B4: Split long responses — play first sentence immediately,
                            # generate rest in parallel for seamless playback
                            from src.adapters.tts.audio_cache import _synthesize_to_mulaw
                            t_tts = time.time()

                            # Split at first sentence boundary for faster first-byte
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

                            logger.info(f"[WS] TTS took: {time.time()-t_tts:.2f}s")
                            if audio:
                                is_playing = True
                                output_audio = _mulaw_to_pcm_for_output(audio)
                                asyncio.create_task(_stream_audio_fast(websocket, stream_sid, output_audio))

                        logger.info(f"[WS] Turn complete: {time.time()-t_start:.2f}s "
                                    f"({'cached' if cached_audio else 'generated'}) "
                                    f"[measured via ngrok tunnel, POC only]")

                        # Check if call should end
                        if session.get("should_close"):
                            asyncio.create_task(_async_session_end(call_sid))
                            # Close WebSocket to end the Voicebot session
                            # Exotel advances to next applet in the flow
                            break

                    # Reset early match for next turn
                    early_match = None

            # ── DTMF ─────────────────────────────────────────
            elif event == "dtmf":
                digit = data.get("dtmf", {}).get("digit", "")
                logger.info(f"[WS] DTMF received: {digit}")

            # ── STREAM STOP ───────────────────────────────────
            elif event == "stop":
                reason = data.get("stop", {}).get("reason", "unknown")
                logger.info(f"[WS] Stream stopped: {call_sid}, reason={reason}")
                break

    except Exception as e:
        logger.error(f"[WS] Error: {e}")
    finally:
        await stt.close()
        if call_sid:
            asyncio.create_task(_async_session_end(call_sid))


def _mulaw_to_pcm_for_output(mulaw_bytes: bytes) -> bytes:
    """
    Convert mulaw audio (from our TTS cache) to Linear PCM 16-bit for Exotel.

    Exotel Voicebot Applet expects PCM16 LE at the negotiated sample rate (8kHz).
    Our cache stores audio as mulaw (1 byte/sample), PCM16 is 2 bytes/sample.
    """
    import audioop
    return audioop.ulaw2lin(mulaw_bytes, 2)


async def _stream_audio_fast(websocket, stream_sid: str, audio_bytes: bytes):
    """
    Stream PCM16 audio to Exotel paced at near real-time.

    Exotel requires:
    - Frames as multiples of 320 bytes
    - Paced delivery — dumping all at once causes buffer overflow / disconnect

    For PCM16 at 8kHz: 2 bytes/sample, so 100ms = 1600 bytes.
    We send 1600-byte chunks paced at ~90ms intervals (slightly faster than real-time).
    """
    CHUNK_SIZE = 1600  # 1600 bytes = 100ms at 8kHz PCM16 (multiple of 320)
    PACE_MS = 0.005  # Send fast — Exotel buffers internally and plays at real-time
    try:
        for i in range(0, len(audio_bytes), CHUNK_SIZE):
            chunk = audio_bytes[i:i + CHUNK_SIZE]

            # Ensure chunk is a multiple of 320 bytes (pad with PCM silence 0x00)
            remainder = len(chunk) % 320
            if remainder != 0:
                chunk += b'\x00' * (320 - remainder)

            payload = base64.b64encode(chunk).decode()
            await websocket.send_text(json.dumps({
                "event": "media",
                "streamSid": stream_sid,
                "media": {"payload": payload}
            }))

            # Pace at near real-time to prevent buffer overflow
            await asyncio.sleep(PACE_MS)
    except Exception as e:
        logger.error(f"[WS] Audio stream error: {e}")


async def _stream_audio_fire_and_forget(websocket, stream_sid: str, audio_bytes: bytes):
    """B1: Stream filler audio without blocking main pipeline."""
    try:
        await _stream_audio_fast(websocket, stream_sid, audio_bytes)
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
