"""Application configuration loaded from environment variables."""
import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    # Twilio
    TWILIO_ACCOUNT_SID: str = os.getenv("TWILIO_ACCOUNT_SID", "")
    TWILIO_AUTH_TOKEN: str = os.getenv("TWILIO_AUTH_TOKEN", "")
    TWILIO_FROM_NUMBER: str = os.getenv("TWILIO_FROM_NUMBER", "")

    # Sarvam AI (TTS + STT)
    SARVAM_API_KEY: str = os.getenv("SARVAM_API_KEY", "")
    SARVAM_TTS_URL: str = os.getenv("SARVAM_TTS_URL", "https://api.sarvam.ai/text-to-speech")

    # AWS
    AWS_REGION: str = os.getenv("AWS_REGION", "us-east-1")
    DYNAMODB_SESSION_TABLE: str = os.getenv("DYNAMODB_SESSION_TABLE", "palvi-sessions")

    # App
    APP_HOST: str = os.getenv("APP_HOST", "0.0.0.0")
    APP_PORT: int = int(os.getenv("APP_PORT", "8000"))
    BASE_URL: str = os.getenv("BASE_URL", "http://localhost:8000")

    # POC Networking — ngrok reserved domain for WSS
    # NOTE: ngrok adds an extra network hop. Latency measurements through this
    # setup are POC-only and not representative of final production latency.
    PUBLIC_WSS_URL: str = os.getenv("PUBLIC_WSS_URL", "wss://underwent-mothball-abreast.ngrok-free.dev")

    # VAD / Silence Detection
    # Only safe to tighten because backchannel filler audio (B1) masks the
    # shorter reaction window. Do not reduce without filler audio active.
    SILENCE_THRESHOLD_MS: int = int(os.getenv("SILENCE_THRESHOLD_MS", "250"))


settings = Settings()
