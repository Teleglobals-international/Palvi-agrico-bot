# Palvi Agrico — AI Voice Sales Bot

Agricultural product sales bot that calls farmers and pitches Palvi Agrico products in regional Marathi (Marathwada / Vidarbha accent) over phone calls.

## Architecture

```
Farmer's Phone
      ↕
Twilio (Voice Calls + Speech Recognition)
      ↕
FastAPI Server (AWS EC2)
  ├── Orchestrator (Conversation flow — sales script)
  ├── Dialect Detector (Marathwada / Vidarbha / Standard)
  ├── Sarvam AI TTS (Text → Natural Marathi Female Voice)
  └── Session Manager (AWS DynamoDB)
```

## Call Flow

```
Greet → Ask Availability → Ask Crop & Acres → Pitch Cytoboost →
Ask Current Pump → Cross-sell Pump → Cross-sell Tarpaulin →
Confirm Order → Collect Address → Thank You & Close
```

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Compute | AWS EC2 (t3.micro, Amazon Linux 2023) |
| Language | Python 3.12 + FastAPI + Uvicorn |
| Telephony | Twilio Voice API |
| Speech-to-Text | Twilio Gather (mr-IN) |
| Text-to-Speech | Sarvam AI (bulbul:v3, speaker: rupali) |
| Database | AWS DynamoDB (palvi-sessions) |
| Dialect Support | Marathwada, Vidarbha, Standard Marathi |

## Products Pitched

1. **Cytoboost** — Plant Growth Regulator (Gibberellic Acid 0.001%)
2. **Spray Pumps** — Battery and Petrol operated
3. **Tarpaulins** — HDPE, waterproof, multiple sizes

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/call/initiate` | Trigger outbound call to a farmer |
| GET | `/calls/history` | Get all call history with conversations |
| GET | `/calls/history/{call_sid}` | Get specific call details |
| GET | `/health` | Health check |

## Usage

```bash
# Initiate a call
curl -X POST http://localhost:8000/call/initiate \
  -H "Content-Type: application/json" \
  -d '{"phone_number": "7066498822"}'

# With specific dialect
curl -X POST http://localhost:8000/call/initiate \
  -H "Content-Type: application/json" \
  -d '{"phone_number": "7066498822", "dialect": "vidarbha"}'
```

## Project Structure

```
app/
├── config.py                 — Environment variable loading
├── main.py                   — FastAPI app + audio serving
├── orchestrator/
│   └── graph.py              — Conversation flow + 3 dialect responses
├── routes/
│   ├── twilio_routes.py      — Twilio voice webhooks
│   ├── call_trigger_routes.py — Call initiation API
│   └── call_history_routes.py — Call history API
└── services/
    ├── sarvam_tts.py         — Sarvam AI TTS + in-memory caching
    ├── session_manager.py    — DynamoDB session management
    └── dialect_detector.py   — Speech-based dialect detection
```

## Setup

1. Create EC2 instance with IAM role (DynamoDB access)
2. Install Python 3.12
3. Copy code to EC2
4. Create `.env` from `.env.example` and fill in keys
5. Install dependencies: `pip install -r requirements.txt`
6. Run: `python3.12 -m uvicorn app.main:app --host 0.0.0.0 --port 8000`

## Language

Marathi only — Marathwada accent (default), auto-switches to Vidarbha if detected from farmer's speech.
