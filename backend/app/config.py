"""Application configuration via pydantic-settings."""

from __future__ import annotations

import logging
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger("financial_doctor.startup")


class Settings(BaseSettings):
    app_name: str = "Financial Doctor"
    environment: str = "development"
    database_url: str = "sqlite:///./data/financial_doctor.db"

    # CORS: explicit comma-separated origins (no wildcards with credentials).
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    # Razorpay configuration
    razorpay_mode: str = "stub"  # "stub" or "live"
    razorpay_key_id: str = ""
    razorpay_key_secret: str = ""
    razorpay_webhook_secret: str = "test_webhook_secret"

    # MiniMax consultation reasoning (Stage 7A). Empty key = stub (default).
    minimax_api_key: str = ""
    minimax_base_url: str = "https://api.minimax.chat/v1"
    minimax_m3_model: str = "MiniMax-M3"
    minimax_group_id: str = ""

    # MiniMax Speech 2.8 TTS (Stage 7A). "stub" (default) or "minimax".
    speech_provider: str = "stub"
    speech_model: str = "speech-2.8-turbo"
    speech_voice_id: str = "English_expressive_narrator"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    def parsed_cors_origins(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


def validate_startup(settings: Settings) -> None:
    """Fail fast on dangerous provider combinations; never silently downgrade.

    Safe: stub anywhere; live only with explicit credentials. Stub providers
    in production are allowed but loudly logged as intentional demo mode.
    """
    mode = settings.razorpay_mode.strip().lower()
    if mode not in ("stub", "live"):
        raise RuntimeError(f"RAZORPAY_MODE must be 'stub' or 'live', got {mode!r}")
    if mode == "live" and not (settings.razorpay_key_id and settings.razorpay_key_secret):
        raise RuntimeError(
            "RAZORPAY_MODE=live but RAZORPAY_KEY_ID/RAZORPAY_KEY_SECRET are missing. "
            "Refusing to start rather than silently falling back to stub."
        )

    speech = settings.speech_provider.strip().lower()
    if speech not in ("stub", "minimax"):
        raise RuntimeError(f"SPEECH_PROVIDER must be 'stub' or 'minimax', got {speech!r}")
    if speech == "minimax" and not settings.minimax_api_key:
        raise RuntimeError(
            "SPEECH_PROVIDER=minimax but MINIMAX_API_KEY is missing. "
            "Refusing to start rather than silently falling back to stub audio."
        )

    consultation = "live (MiniMax M3)" if settings.minimax_api_key else "stub (deterministic)"
    logger.info(
        "startup: env=%s razorpay=%s speech=%s consultation=%s",
        settings.environment,
        mode,
        speech,
        consultation,
    )
    if settings.environment.strip().lower() == "production" and (
        mode == "stub" or speech == "stub" or not settings.minimax_api_key
    ):
        logger.warning(
            "startup: production environment with stub/demo providers — "
            "intentional hackathon demo mode (no real money moves)."
        )