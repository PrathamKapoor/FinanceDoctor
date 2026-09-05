"""Stage 8A — deployment readiness tests.

Startup validation (fail fast, never silent fallback), safe health output,
explicit CORS, and single-process static frontend serving.
"""

from __future__ import annotations

import pytest
from backend.app.config import Settings, get_settings, validate_startup
from backend.app.main import create_app
from fastapi.testclient import TestClient


@pytest.fixture
def fresh_settings(monkeypatch):
    """Build an app with isolated env (clears the cached settings)."""
    monkeypatch.delenv("RAZORPAY_MODE", raising=False)
    monkeypatch.delenv("RAZORPAY_KEY_ID", raising=False)
    monkeypatch.delenv("RAZORPAY_KEY_SECRET", raising=False)
    monkeypatch.delenv("SPEECH_PROVIDER", raising=False)
    monkeypatch.delenv("MINIMAX_API_KEY", raising=False)
    monkeypatch.delenv("CORS_ORIGINS", raising=False)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_stub_defaults_validate():
    validate_startup(Settings())


def test_live_razorpay_without_credentials_fails_fast():
    with pytest.raises(RuntimeError, match="RAZORPAY_KEY_ID"):
        validate_startup(
            Settings(razorpay_mode="live", razorpay_key_id="", razorpay_key_secret="")
        )


def test_live_razorpay_with_credentials_passes():
    validate_startup(
        Settings(razorpay_mode="live", razorpay_key_id="id", razorpay_key_secret="s")
    )


def test_unknown_modes_fail_fast():
    with pytest.raises(RuntimeError, match="RAZORPAY_MODE"):
        validate_startup(Settings(razorpay_mode="real"))
    with pytest.raises(RuntimeError, match="SPEECH_PROVIDER"):
        validate_startup(Settings(speech_provider="elevenlabs"))


def test_minimax_speech_without_key_fails_fast():
    with pytest.raises(RuntimeError, match="MINIMAX_API_KEY"):
        validate_startup(Settings(speech_provider="minimax", minimax_api_key=""))


def test_create_app_refuses_dangerous_config(fresh_settings, monkeypatch):
    monkeypatch.setenv("RAZORPAY_MODE", "live")
    get_settings.cache_clear()
    with pytest.raises(RuntimeError, match="RAZORPAY_KEY_ID"):
        create_app()


def test_health_is_minimal_and_secret_free(fresh_settings):
    with TestClient(create_app()) as client:
        body = client.get("/health").json()
    assert body["status"] == "ok"
    assert body["razorpay_mode"] == "stub"
    assert body["speech_provider"] == "stub"
    assert body["consultation"] == "stub"
    blob = str(body)
    assert "test_webhook_secret" not in blob
    assert "sk-" not in blob


def test_cors_allows_configured_origin(fresh_settings):
    with TestClient(create_app()) as client:
        resp = client.get(
            "/health", headers={"Origin": "http://localhost:5173"}
        )
    assert resp.headers.get("access-control-allow-origin") == "http://localhost:5173"


def test_cors_rejects_unlisted_origin(fresh_settings):
    with TestClient(create_app()) as client:
        resp = client.get("/health", headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in resp.headers


def test_frontend_dist_served_same_origin(fresh_settings):
    import os

    dist_index = os.path.join("frontend", "dist", "index.html")
    if not os.path.isfile(dist_index):
        pytest.skip("frontend/dist not built here")
    with TestClient(create_app()) as client:
        resp = client.get("/")
    assert resp.status_code == 200
    assert "Financial Doctor" in resp.text
    # API routes still win over static serving.
    with TestClient(create_app()) as client:
        assert client.get("/health").json()["status"] == "ok"


def test_audio_provider_failure_maps_to_safe_502(fresh_settings, monkeypatch):
    from backend.app.routers import demo_case
    from backend.app.services.consultation.speech_adapter import SpeechError

    class _Boom:
        @property
        def name(self):
            return "boom"

        @property
        def capabilities(self):
            return {"tts": True, "stt": False}

        async def synthesize(self, text, *, voice_id=None):
            raise SpeechError("provider exploded")

    monkeypatch.setattr(demo_case, "create_speech_provider", lambda: _Boom())
    with TestClient(create_app()) as client:
        case = client.post("/demo/case/start", json={}).json()
        cid = case["case_id"]
        consult = client.post(
            f"/demo/case/{cid}/consult", json={"question": "What happened?"}
        ).json()
        resp = client.post(
            f"/demo/case/{cid}/consultations/{consult['consultation_id']}/audio"
        )
    assert resp.status_code == 502
    assert "text answer" in resp.json()["detail"]
