# Palvi Agrico Voice Bot

AI-powered outbound sales voice agent for Palvi Agrico (agricultural products). Speaks Marathi with Marathwada/Vidarbha dialect support. Built on Exotel + Sarvam AI + Claude.

---

## Architecture

```
Farmer's Phone ←→ Exotel (Voicebot Applet) ←→ Our Server (WebSocket) ←→ Sarvam AI (STT/TTS)
                                                        ↕
                                                   Claude (LLM fallback)
                                                        ↕
                                                   DynamoDB (sessions)
```

## Features (27)

**Calling:** Outbound via API, inbound support, bidirectional WebSocket streaming, call history API

**Voice:** Marathi TTS (Sarvam), Marathi STT (streaming), dialect detection (Marathwada/Vidarbha), Hindi transcription handling

**Latency Optimization:**
- B1: Backchannel filler ("हम्म/होय") while processing
- B2: Pre-cached script audio (zero TTS during calls)
- B3: Early intent classification on partial transcripts
- B4: Sentence-streamed TTS for long responses
- B5: Async DynamoDB logging (off critical path)
- B6: Configurable VAD (250ms silence threshold)
- B7: Barge-in (farmer interrupts → playback stops)
- B8: STT flush timeout (falls back to partial)
- B9: Fast audio batching

**Intelligence:** 25+ step state machine, FAQ keyword matcher, Claude fallback for off-script questions, order capture, lucky draw promotion

---

## Project Structure

```
src/
├── main.py                          # FastAPI entry point
├── config/
│   └── settings.py                  # Environment config
├── core/
│   ├── callFlow/
│   │   ├── state_machine.py         # Conversation state machine
│   │   ├── scripts.py              # All scripted Marathi texts
│   │   └── precache.py             # Pre-cache audio at startup
│   ├── offerEngine/
│   │   └── scheme.py               # Lucky draw scheme logic
│   └── productKnowledge/
│       ├── products.py             # Product recommendations & FAQs
│       └── faq_matcher.py          # Keyword-based FAQ matching
├── adapters/
│   ├── telephony/
│   │   └── exotel_ws.py            # Exotel WebSocket handler
│   ├── stt/
│   │   ├── sarvam_stream.py        # Streaming STT client
│   │   ├── intent_classifier.py    # Early intent on partials
│   │   └── dialect_detector.py     # Dialect detection
│   ├── tts/
│   │   ├── sarvam_tts.py           # TTS + disk/memory cache
│   │   └── audio_cache.py          # Filler audio, codec conversion
│   └── llm/
│       └── claude.py               # Claude/Bedrock fallback
├── modules/
│   ├── calls/
│   │   ├── exotel_webhooks.py      # Status/passthru webhooks
│   │   └── trigger.py             # POST /call/initiate
│   └── analytics/
│       └── history.py             # GET /calls/history
└── infra/
    └── db/
        └── session_manager.py      # DynamoDB session storage
```

---

## Services Used

| Service | Purpose |
|---------|---------|
| **Exotel** | Telephony — outbound calls, Voicebot Applet (WebSocket audio streaming) |
| **Sarvam AI** | Marathi STT (streaming WebSocket) + TTS (bulbul:v3, speaker: priya) |
| **AWS Bedrock (Claude)** | LLM fallback for off-script questions (~10% of turns) |
| **AWS DynamoDB** | Session persistence, call history, order data |
| **AWS EC2** | Application server |

---

## Setup

### 1. Environment

```env
EXOTEL_API_KEY=your_api_key
EXOTEL_API_TOKEN=your_api_token
EXOTEL_ACCOUNT_SID=your_account_sid
EXOTEL_SUBDOMAIN=api.exotel.com
EXOTEL_CALLER_ID=your_exophone
EXOTEL_APP_ID=your_call_flow_id

SARVAM_API_KEY=your_sarvam_key
SARVAM_TTS_URL=https://api.sarvam.ai/text-to-speech

AWS_REGION=us-east-1
DYNAMODB_SESSION_TABLE=palvi-sessions

APP_HOST=0.0.0.0
APP_PORT=8000
BASE_URL=http://your-server:8000
PUBLIC_WSS_URL=wss://your-domain.com
EXOTEL_SAMPLE_RATE=8000
SILENCE_THRESHOLD_MS=250
```

### 2. Exotel Dashboard

1. Create a **Call Flow** with a **Voicebot Applet** (bidirectional)
2. Set endpoint: `wss://your-domain.com/media-stream?sample-rate=8000`
3. Add a **Hangup** applet after the Voicebot
4. Note the App ID for `EXOTEL_APP_ID`

### 3. Run

```bash
pip install -r requirements.txt
uvicorn src.main:app --host 0.0.0.0 --port 8000
```

### 4. Test Outbound Call

```bash
curl -X POST http://localhost:8000/call/initiate \
  -H "Content-Type: application/json" \
  -d '{"phone_number": "9876543210", "dialect": "marathwada"}'
```

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/call/initiate` | Start outbound call |
| POST | `/voice/status` | Exotel status callback |
| GET | `/voice/passthru` | Exotel passthru (post-voicebot) |
| WS | `/media-stream` | Exotel Voicebot Applet WebSocket |
| GET | `/calls/history` | All call transcripts |
| GET | `/calls/history/{call_sid}` | Single call detail |
| GET | `/health` | Health check |

---

## Docker

```bash
docker build -t palvi-agrico-bot .
docker run -p 8000:8000 --env-file .env palvi-agrico-bot
```
# CI/CD Pipeline Active
