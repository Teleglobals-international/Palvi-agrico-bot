# Multi-Tenant AI Calling Agent Platform

Production-grade calling agent platform supporting **Real Estate**, **Home Services**, and **Fintech** industries with inbound and outbound calling via Exotel.

## Architecture

```
app/
├── main.py                          # FastAPI entry point
├── config.py                        # Configuration (env-based)
├── api/
│   └── v1/
│       ├── calling.py               # Webhook + WebSocket + outbound endpoints
│       ├── agents.py                # Agent info endpoints
│       └── health.py                # Health checks
├── features/
│   ├── agents/                      # Industry-specific agent definitions
│   │   ├── base_agent.py           # Abstract base class
│   │   ├── real_estate_agent.py    # Real Estate agent
│   │   ├── home_services_agent.py  # Home Services agent
│   │   ├── fintech_agent.py        # Fintech agent
│   │   └── registry.py            # Agent lookup registry
│   ├── calling/                     # Exotel integration
│   │   ├── exotel_client.py       # Exotel REST API client
│   │   ├── webhook_handler.py     # Webhook callback processing
│   │   └── websocket_handler.py   # Real-time audio streaming
│   ├── llm/                         # LLM service
│   │   └── service.py             # OpenAI integration + fallback
│   └── conversation/                # State management
│       └── manager.py             # Session & message history
├── core/
│   ├── exceptions.py               # Custom exceptions
│   ├── middleware.py               # Logging & error middleware
│   └── security.py                 # Webhook auth & rate limiting
└── shared/
    ├── models.py                    # Pydantic models
    └── utils.py                     # Utility functions
```

## Features

- **3 Industry Agents**: Real Estate, Home Services, Fintech — each with domain-specific prompts and keyword detection
- **Inbound + Outbound Calling**: Full support for both directions via Exotel
- **Webhook Integration**: Receives call lifecycle events from Exotel (incoming, answer, status)
- **WebSocket Streaming**: Real-time bidirectional audio handling
- **LLM Fallback**: When users ask irrelevant/out-of-domain questions, the agent politely acknowledges and guides back to topic
- **Shared Credentials**: All agents use the same Exotel credentials (same as agri domain)
- **Production-Ready**: Structured logging, error handling, rate limiting, health checks

## Setup

### Prerequisites

- Python 3.11+
- Redis (for session state)
- Exotel account with API access

### Installation

```bash
# Create virtual environment
python -m venv venv
venv\Scripts\activate   # Windows
# source venv/bin/activate  # Linux/Mac

# Install dependencies
pip install -r requirements.txt

# Copy and configure environment
copy .env.example .env
# Edit .env with your actual credentials
```

### Running

```bash
# Development
uvicorn app.main:app --reload --port 8000

# Production
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4

# Docker
docker-compose up --build
```

## API Endpoints

### Health
- `GET /api/v1/health` — Basic health check
- `GET /api/v1/health/ready` — Readiness check

### Agents
- `GET /api/v1/agents/` — List all agents
- `GET /api/v1/agents/{industry}` — Get agent info

### Calling
- `POST /api/v1/calling/outbound` — Initiate outbound call
- `POST /api/v1/calling/webhook/incoming/{industry}` — Inbound call webhook
- `POST /api/v1/calling/webhook/answer/{industry}` — Answer callback
- `POST /api/v1/calling/webhook/status` — Status callback
- `POST /api/v1/calling/session/{session_id}/message` — Send message during call
- `WS /api/v1/calling/ws/{industry}` — WebSocket audio stream
- `GET /api/v1/calling/session/{session_id}` — Get session details

### Example: Initiate Outbound Call

```bash
curl -X POST http://localhost:8000/api/v1/calling/outbound \
  -H "Content-Type: application/json" \
  -d '{
    "industry": "real_estate",
    "to_number": "+919876543210",
    "context": {"property_id": "PROP-001", "customer_name": "Rahul"}
  }'
```

## LLM Fallback Behavior

When a user asks something outside the agent's domain:

1. The agent detects the query is irrelevant using keyword matching
2. A fallback system prompt is used that:
   - Acknowledges the question politely
   - Provides a brief helpful response if possible
   - Guides the conversation back to the agent's domain
3. If the LLM itself fails, a static fallback message offers to connect with a human

## Adding a New Industry Agent

1. Create a new file in `app/features/agents/` (e.g., `healthcare_agent.py`)
2. Extend `BaseAgent` and implement all abstract methods
3. Add the new `IndustryType` enum value in `app/shared/models.py`
4. Register in `app/features/agents/registry.py`

## Environment Variables

See `.env.example` for all configuration options. The Exotel credentials are shared across all agents (same credentials used for the agri domain agent).
