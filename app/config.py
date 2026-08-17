"""
Application configuration management.
Loads settings from environment variables with validation.
"""

from pydantic_settings import BaseSettings
from pydantic import Field
from functools import lru_cache


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # App
    app_host: str = Field(default="0.0.0.0", alias="APP_HOST")
    app_port: int = Field(default=8001, alias="APP_PORT")
    base_url: str = Field(default="http://localhost:8001", alias="BASE_URL")

    # Exotel Credentials (shared across all agents)
    exotel_api_key: str = Field(..., alias="EXOTEL_API_KEY")
    exotel_api_token: str = Field(..., alias="EXOTEL_API_TOKEN")
    exotel_account_sid: str = Field(default="teleglobals2", alias="EXOTEL_ACCOUNT_SID")
    exotel_subdomain: str = Field(default="api.in.exotel.com", alias="EXOTEL_SUBDOMAIN")
    exotel_caller_id: str = Field(default="02048565101", alias="EXOTEL_CALLER_ID")
    exotel_app_id: str = Field(default="1306422", alias="EXOTEL_APP_ID")
    exotel_sample_rate: int = Field(default=8000, alias="EXOTEL_SAMPLE_RATE")

    # Sarvam AI (TTS + STT)
    sarvam_api_key: str = Field(..., alias="SARVAM_API_KEY")
    sarvam_tts_url: str = Field(
        default="https://api.sarvam.ai/text-to-speech", alias="SARVAM_TTS_URL"
    )

    # AWS
    aws_region: str = Field(default="us-east-1", alias="AWS_REGION")
    dynamodb_session_table: str = Field(default="multi-tenant-sessions", alias="DYNAMODB_SESSION_TABLE")

    # POC Networking
    public_wss_url: str = Field(
        default="wss://underwent-mothball-abreast.ngrok-free.dev",
        alias="PUBLIC_WSS_URL",
    )

    # LLM Configuration (AWS Bedrock)
    bedrock_model_id: str = Field(
        default="us.anthropic.claude-sonnet-4-6", alias="BEDROCK_MODEL_ID"
    )
    llm_fallback_temperature: float = Field(default=0.7, alias="LLM_FALLBACK_TEMPERATURE")
    llm_max_tokens: int = Field(default=500, alias="LLM_MAX_TOKENS")

    # VAD Tuning
    silence_threshold_ms: int = Field(default=250, alias="SILENCE_THRESHOLD_MS")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False


@lru_cache()
def get_settings() -> Settings:
    """Get cached application settings."""
    return Settings()
