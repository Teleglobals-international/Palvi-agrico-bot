"""Application configuration loaded from environment variables."""
import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    # Telephony provider: "twilio" or "exotel"
    TELEPHONY_PROVIDER: str = os.getenv("TELEPHONY_PROVIDER", "twilio")

    # Twilio (Primary)
    TWILIO_ACCOUNT_SID: str = os.getenv("TWILIO_ACCOUNT_SID", "")
    TWILIO_AUTH_TOKEN: str = os.getenv("TWILIO_AUTH_TOKEN", "")
    TWILIO_FROM_NUMBER: str = os.getenv("TWILIO_FROM_NUMBER", "")

    # Exotel (Fallback)
    EXOTEL_API_KEY: str = os.getenv("EXOTEL_API_KEY", "")
    EXOTEL_API_TOKEN: str = os.getenv("EXOTEL_API_TOKEN", "")
    EXOTEL_ACCOUNT_SID: str = os.getenv("EXOTEL_ACCOUNT_SID", "")
    EXOTEL_SUBDOMAIN: str = os.getenv("EXOTEL_SUBDOMAIN", "api.in.exotel.com")  # Mumbai region
    EXOTEL_CALLER_ID: str = os.getenv("EXOTEL_CALLER_ID", "")  # Your ExoPhone number
    EXOTEL_APP_ID: str = os.getenv("EXOTEL_APP_ID", "")  # Call flow App ID with Voicebot Applet

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

    # Exotel audio config
    # Exotel Voicebot Applet sends Linear PCM 16-bit at this sample rate
    EXOTEL_SAMPLE_RATE: int = int(os.getenv("EXOTEL_SAMPLE_RATE", "8000"))

    # VAD / Silence Detection
    # Only safe to tighten because backchannel filler audio (B1) masks the
    # shorter reaction window. Do not reduce without filler audio active.
    SILENCE_THRESHOLD_MS: int = int(os.getenv("SILENCE_THRESHOLD_MS", "250"))


settings = Settings()
