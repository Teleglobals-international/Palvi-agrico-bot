"""
Exotel Voicebot Applet WebSocket Handler — Full Voice Loop.
Replicates the agri agent's working pattern:
- Exotel sends PCM16 8kHz audio chunks
- We pipe to Sarvam STT for transcription
- LLM generates response (with fallback for off-topic)
- Sarvam TTS converts response to audio
- Audio streamed back to Exotel

Supports: VAD (silence detection), barge-in, filler audio.
"""

import asyncio
import base64
import json
import logging
import struct
import time
from typing import Optional

from fastapi import WebSocket

from app.config import get_settings
from app.features.agents.registry import AgentRegistry
from app.features.conversation import ConversationManager
from app.features.llm import LLMService
from app.features.stt.sarvam_stream import SarvamSTTStream
from app.features.tts.sarvam_tts import SarvamTTS
from app.shared.models import (
    CallDirection,
    CallStatus,
    ConversationRole,
    IndustryType,
)

logger = logging.getLogger(__name__)


class WebSocketHandler:
    """
    Handles real-time Exotel Voicebot Applet WebSocket connections.
    Full voice pipeline: Audio → STT → LLM → TTS → Audio back.
    """

    def __init__(
        self,
        agent_registry: AgentRegistry,
        conversation_manager: ConversationManager,
        llm_service: LLMService,
    ):
        self._registry = agent_registry
        self._conversations = conversation_manager
        self._llm = llm_service
        self._tts = SarvamTTS()

    async def handle_connection(
        self,
        websocket: WebSocket,
        industry: IndustryType,
    ) -> None:
        """
        Handle an Exotel Voicebot Applet WebSocket connection.
        Full voice loop with STT, LLM, and TTS.
        """
        await websocket.accept()

        settings = get_settings()
        SAMPLE_RATE = settings.exotel_sample_rate
        BYTES_PER_SAMPLE = 2
        SILENCE_FRAMES = settings.silence_threshold_ms // 20

        call_sid = None
        stream_sid = None
        session_id = None
        stt = SarvamSTTStream(language_code="en-IN")
        silence_frames = 0
        speech_started = False
        is_playing = False
        greeting_sent = False
        greeting_done = False
        media_packet_count = 0

        agent = self._registry.get_agent(industry)

        try:
            await stt.connect()
            stt_task = asyncio.create_task(stt.receive_loop())

            while True:
                try:
                    raw = await websocket.receive_text()
                except Exception as recv_err:
                    logger.error(f"[WS] receive error: {recv_err}")
                    break

                data = json.loads(raw)
                event = data.get("event")

                if event != "media":
                    logger.info(f"[WS] Event: {event}")

                # ── CONNECTED ─────────────────────────────────────
                if event == "connected":
                    logger.info(f"[WS] Exotel connected: {data}")
                    continue

                # ── STREAM START ──────────────────────────────────
                elif event == "start":
                    start_data = data.get("start", {})
                    call_sid = start_data.get("call_sid", start_data.get("callSid", data.get("call_sid", "unknown")))
                    stream_sid = data.get("stream_sid", start_data.get("stream_sid", start_data.get("streamSid", "")))
                    custom_params = start_data.get("custom_parameters", data.get("custom_parameters", {}))

                    logger.info(f"[WS] Stream started: CallSid={call_sid}, StreamSid={stream_sid}, Industry={industry.value}")

                    # Determine direction
                    direction_str = custom_params.get("direction", "inbound") if isinstance(custom_params, dict) else "inbound"
                    direction = CallDirection.OUTBOUND if direction_str == "outbound" else CallDirection.INBOUND

                    # Create session
                    session = self._conversations.create_session(
                        industry=industry,
                        direction=direction,
                        call_sid=call_sid,
                        metadata={"stream_sid": stream_sid, "custom_parameters": custom_params},
                    )
                    session_id = session.session_id

                    # Get greeting
                    context = custom_params if isinstance(custom_params, dict) else None
                    greeting = agent.get_greeting(direction, context)

                    # Store greeting
                    self._conversations.add_message(
                        session_id=session_id,
                        role=ConversationRole.AGENT,
                        content=greeting,
                    )

                    greeting_sent = False

                # ── AUDIO DATA ────────────────────────────────────
                elif event == "media":
                    media_data = data.get("media", {})
                    payload = media_data.get("payload", "") if isinstance(media_data, dict) else ""

                    if not payload:
                        continue

                    media_packet_count += 1
                    pcm_bytes = base64.b64decode(payload)

                    # Wait a few packets to confirm call is connected, then play greeting
                    if not greeting_sent:
                        if media_packet_count < 5:
                            await stt.send_audio(pcm_bytes)
                            continue

                        greeting_sent = True
                        greeting_text = agent.get_greeting(
                            self._conversations.get_session(session_id).direction
                        )

                        # Generate greeting audio
                        greeting_pcm = await self._tts.synthesize_to_pcm(greeting_text)
                        if greeting_pcm:
                            logger.info(f"[WS] Streaming greeting: {len(greeting_pcm)} bytes")

                            async def _play_greeting():
                                nonlocal is_playing
                                is_playing = True
                                try:
                                    await self._stream_audio(websocket, stream_sid, greeting_pcm)
                                except Exception as e:
                                    logger.error(f"[WS] Greeting play error: {e}")
                                is_playing = False
                                logger.info("[WS] Greeting complete")

                            asyncio.create_task(_play_greeting())
                            greeting_done = True
                        else:
                            logger.error("[WS] No greeting audio generated")
                            greeting_done = True

                    if not greeting_done:
                        await stt.send_audio(pcm_bytes)
                        continue

                    # Barge-in: if user speaks while bot is playing, stop playback
                    if is_playing:
                        max_sample = max(abs(s) for s in struct.unpack(f"<{len(pcm_bytes) // 2}h", pcm_bytes))
                        if max_sample > 800:
                            is_playing = False
                            await websocket.send_text(json.dumps({
                                "event": "clear",
                                "streamSid": stream_sid,
                            }))
                            logger.info("[WS] Barge-in detected, stopped playback")
                        continue

                    # Send audio to STT
                    await stt.send_audio(pcm_bytes)

                    # VAD: detect end of speech
                    max_sample = max(abs(s) for s in struct.unpack(f"<{len(pcm_bytes) // 2}h", pcm_bytes))
                    if max_sample > 500:
                        speech_started = True
                        silence_frames = 0
                    elif speech_started:
                        silence_frames += 1

                    # End of speech detected — process turn
                    if speech_started and silence_frames >= SILENCE_FRAMES:
                        t_start = time.time()
                        speech_started = False
                        silence_frames = 0

                        # Get transcript from STT
                        transcript = await stt.flush_and_get()
                        logger.info(f"[TIMING] STT phase: {time.time() - t_start:.3f}s")

                        if transcript and len(transcript.strip()) > 1:
                            logger.info(f"[WS] User ({industry.value}): '{transcript}'")

                            # Store user message
                            self._conversations.add_message(
                                session_id=session_id,
                                role=ConversationRole.USER,
                                content=transcript,
                            )

                            # Generate LLM response (domain or fallback)
                            t_llm = time.time()
                            session = self._conversations.get_session(session_id)
                            response = await self._llm.generate_response(
                                agent=agent,
                                messages=session.messages,
                                user_message=transcript,
                                direction=session.direction,
                            )
                            logger.info(f"[TIMING] LLM phase: {time.time() - t_llm:.3f}s")
                            logger.info(f"[WS] Agent ({industry.value}): '{response.text[:60]}' (fallback={response.is_fallback})")

                            # Store agent response
                            self._conversations.add_message(
                                session_id=session_id,
                                role=ConversationRole.AGENT,
                                content=response.text,
                                metadata={"is_fallback": response.is_fallback},
                            )

                            # TTS: convert response to audio
                            t_tts = time.time()
                            response_pcm = await self._tts.synthesize_to_pcm(response.text)
                            logger.info(f"[TIMING] TTS phase: {time.time() - t_tts:.3f}s")

                            if response_pcm:
                                is_playing = True
                                asyncio.create_task(
                                    self._stream_audio(websocket, stream_sid, response_pcm)
                                )

                            logger.info(f"[WS] Turn complete: {time.time() - t_start:.2f}s")

                # ── DTMF ─────────────────────────────────────────
                elif event == "dtmf":
                    digit = data.get("dtmf", {}).get("digit", "")
                    logger.info(f"[WS] DTMF: {digit}")

                # ── STREAM STOP ───────────────────────────────────
                elif event == "stop":
                    reason = data.get("stop", {}).get("reason", "unknown")
                    logger.info(f"[WS] Stream stopped: {call_sid}, reason={reason}")
                    break

        except Exception as e:
            logger.error(f"[WS] Error: {e}", exc_info=True)
        finally:
            await stt.close()
            if session_id:
                try:
                    self._conversations.end_session(session_id)
                except Exception:
                    pass
            logger.info(f"[WS] Connection closed: {call_sid}")

    async def _stream_audio(
        self,
        websocket: WebSocket,
        stream_sid: str,
        pcm_bytes: bytes,
    ) -> None:
        """
        Stream PCM16 audio to Exotel paced at near real-time.
        Sends 1600-byte chunks (100ms at 8kHz PCM16).
        """
        CHUNK_SIZE = 1600  # 100ms at 8kHz PCM16
        PACE_MS = 0.005  # Fast pace — Exotel buffers internally

        try:
            for i in range(0, len(pcm_bytes), CHUNK_SIZE):
                chunk = pcm_bytes[i:i + CHUNK_SIZE]

                # Ensure chunk is multiple of 320 bytes
                remainder = len(chunk) % 320
                if remainder != 0:
                    chunk += b'\x00' * (320 - remainder)

                payload = base64.b64encode(chunk).decode()
                await websocket.send_text(json.dumps({
                    "event": "media",
                    "streamSid": stream_sid,
                    "media": {"payload": payload},
                }))

                await asyncio.sleep(PACE_MS)

        except Exception as e:
            logger.error(f"[WS] Audio stream error: {e}")
