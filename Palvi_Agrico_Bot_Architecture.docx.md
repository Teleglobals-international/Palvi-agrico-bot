# Palvi Agrico Voice Bot — Architecture

---

## Outbound Calling Flow

```
┌──────────────┐        ┌──────────────┐        ┌──────────────────┐
│              │  API    │              │  Dials  │                  │
│  Our System  │ ─────→  │   Exotel    │ ─────→  │  Farmer's Phone  │
│  (Trigger)   │        │  (Calling)   │        │                  │
└──────────────┘        └──────┬───────┘        └────────┬─────────┘
                               │                         │
                               │ Opens WebSocket         │ Farmer
                               │ (Voicebot Applet)       │ speaks
                               ▼                         │
                        ┌──────────────┐                 │
                        │  Our Server  │ ←───────────────┘
                        │  (AWS EC2)   │   (PCM audio via WebSocket)
                        │              │
                        │  ┌────────┐  │
                        │  │ State  │  │
                        │  │Machine │  │
                        │  └───┬────┘  │
                        └──────┼───────┘
                               │
                        ┌──────┴───────┐
                        │  Sarvam AI   │
                        │  STT + TTS   │
                        └──────────────┘
```

---

## Inbound Calling Flow

```
Farmer calls ExoPhone → Exotel Call Flow → Voicebot Applet → WebSocket → Our Server
(Same conversation engine, same voice, same script)
```

---

## Modular Architecture

```
src/
├── core/               # Business logic (framework-agnostic)
│   ├── callFlow/       # 25+ step state machine
│   ├── offerEngine/    # Lucky draw promotion
│   └── productKnowledge/  # Product FAQs & recommendations
│
├── adapters/           # Swappable integrations
│   ├── telephony/      # Exotel (can swap to Twilio/Ozonetel)
│   ├── stt/            # Sarvam (can swap to Deepgram/Google)
│   ├── tts/            # Sarvam (can swap to ElevenLabs)
│   └── llm/            # Claude (can swap to GPT/Gemini)
│
├── modules/            # Feature-based API layer
│   ├── calls/          # Call trigger & webhooks
│   └── analytics/      # Call history & transcripts
│
├── config/             # Client-specific configuration
│
└── infra/              # Database, logging, queues
    └── db/             # DynamoDB session manager
```

---

## Services

| Service | Role |
|---------|------|
| **Exotel** | Telephony — PSTN calling + bidirectional WebSocket audio streaming |
| **Sarvam AI** | Marathi STT (streaming) + TTS (natural female voice) |
| **AWS Bedrock (Claude)** | LLM fallback for unexpected farmer questions |
| **AWS DynamoDB** | Session persistence + call history |
| **AWS EC2** | Application hosting |

---

## Data Flow (Single Turn)

```
1. Farmer speaks → Exotel sends PCM audio via WebSocket
2. Server streams audio to Sarvam STT → gets Marathi transcript
3. State machine processes transcript:
   - Scripted step? → Return pre-cached audio (0ms)
   - FAQ match? → Return pre-cached FAQ answer (0ms)
   - Off-script? → Call Claude → Generate TTS live (~2s)
4. Convert audio to PCM16 → Stream back via WebSocket → Farmer hears response
```

---

## Key Design Decisions

- **State machine over LLM** — 90% of calls follow the script, no need for LLM
- **Pre-cached audio** — All scripted responses synthesized at startup
- **Mulaw internal cache** — Compact storage, converted to PCM16 on output
- **Async everything** — DynamoDB writes, TTS calls never block the audio path
- **Dialect detection** — Adapts vocabulary based on farmer's region
- **Modular adapters** — Can swap telephony/STT/TTS/LLM without touching core logic
