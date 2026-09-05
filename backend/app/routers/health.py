"""Health endpoint (deployment-safe: no secrets, no financial data)."""

from __future__ import annotations

from fastapi import APIRouter, Request

from backend.app.config import get_settings

router = APIRouter(tags=["health"])


@router.get("/health")
def health(request: Request) -> dict[str, object]:
    settings = get_settings()
    world_loaded = getattr(request.app.state, "world", None) is not None
    return {
        "status": "ok",
        "version": request.app.version,
        "environment": settings.environment,
        "razorpay_mode": settings.razorpay_mode.strip().lower(),
        "speech_provider": settings.speech_provider.strip().lower(),
        "consultation": "live" if settings.minimax_api_key else "stub",
        "world_loaded": world_loaded,
    }