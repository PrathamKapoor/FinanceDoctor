"""Stage 8B — live provider wire-contract verification (no network, no keys).

Real credential calls are BLOCKED on credentials (none exist in this
environment and none were provided). These tests verify the maximum that is
honestly verifiable without keys: the exact HTTP contracts the live adapters
will speak once credentials arrive, exercised through the REAL client code
with ``httpx.MockTransport``. Anything asserting a real network call would be
fabricated — these tests assert request shape, auth, parsing, and errors.
"""

from __future__ import annotations

import base64
import json

import httpx
import pytest
from backend.app.adapters.razorpay.exceptions import (
    ProviderAuthenticationError,
    ProviderConflictError,
    ProviderUnavailableError,
)
from backend.app.adapters.razorpay.live import LiveRazorpayAdapter
from backend.app.agents.models import (
    MiniMaxModelClient,
    ModelConfig,
    StubModelClient,
    create_model_client,
)
from backend.app.services.consultation.consultation_service import (
    ConsultConfig,
    ConsultService,
)


def _mock_client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://unit.test",
    )


# ---------- MiniMax M2.7/M3 client contract ----------

def test_minimax_chat_request_shape_and_auth(monkeypatch):
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": '{"answer": "hi"}'}}]},
        )

    client = MiniMaxModelClient(ModelConfig(minimax_api_key="k", minimax_m3_model="MiniMax-M3"))

    async def fake_get_client():
        return httpx.AsyncClient(
            transport=httpx.MockTransport(handler),
            base_url="https://unit.test",
            headers={"Authorization": "Bearer k", "Content-Type": "application/json"},
        )

    monkeypatch.setattr(client, "_get_client", fake_get_client)

    import asyncio

    from pydantic import BaseModel

    class S(BaseModel):
        answer: str

    out = asyncio.run(
        client.generate(
            "Say hi", system_prompt="sys", temperature=0.2, max_tokens=10, response_schema=S
        )
    )
    assert isinstance(out, S) and out.answer == "hi"
    req = calls[0]
    assert req.url.path == "/chat/completions"
    assert req.headers["authorization"] == "Bearer k"
    body = json.loads(req.content.decode())
    assert body["model"] == "MiniMax-M3"
    assert body["response_format"] == {"type": "json_object"}
    assert [m["role"] for m in body["messages"]] == ["system", "user"]


def test_minimax_chat_errors_surface(monkeypatch):
    client = MiniMaxModelClient(ModelConfig(minimax_api_key="k"))

    async def fake_500():
        return _mock_client(lambda r: httpx.Response(500, json={}))

    async def fake_bad_json():
        return _mock_client(
            lambda r: httpx.Response(200, json={"choices": [{"message": {"content": "nope"}}]})
        )

    import asyncio

    from pydantic import BaseModel

    class S(BaseModel):
        answer: str

    monkeypatch.setattr(client, "_get_client", fake_500)
    with pytest.raises(httpx.HTTPStatusError):
        asyncio.run(client.generate("x", response_schema=S))
    monkeypatch.setattr(client, "_get_client", fake_bad_json)
    with pytest.raises(ValueError, match="Failed to parse"):
        asyncio.run(client.generate("x", response_schema=S))


def test_no_key_selects_stub_client(monkeypatch):
    monkeypatch.delenv("MINIMAX_API_KEY", raising=False)
    assert isinstance(create_model_client(), StubModelClient)


def test_fenced_json_output_is_accepted(monkeypatch):
    """Providers that wrap JSON in Markdown fences still validate."""
    import asyncio

    from pydantic import BaseModel

    class S(BaseModel):
        answer: str

    client = MiniMaxModelClient(ModelConfig(minimax_api_key="k"))

    async def fake_get_client():
        return httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda r: httpx.Response(
                    200,
                    json={"choices": [{"message": {"content": '```json\n{"answer": "hi"}\n```'}}]},
                )
            ),
            base_url="https://unit.test",
            headers={"Authorization": "Bearer k"},
        )

    monkeypatch.setattr(client, "_get_client", fake_get_client)
    out = asyncio.run(client.generate("x", response_schema=S))
    assert isinstance(out, S) and out.answer == "hi"


def test_worker_calls_default_to_m27_model_id(monkeypatch):
    """M2.7 responsibilities stay on the M2.7 model in live mode."""
    import asyncio
    from types import SimpleNamespace

    from backend.app.agents.models import default_m27_model
    from backend.app.agents.workers import TemporalWorker

    seen: dict = {}

    class _RecordingClient:
        async def generate(self, prompt: str, **kw):
            seen.update(kw)
            return {"worker": "temporal"}

        async def close(self) -> None:
            pass

    class _Dump:
        def model_dump(self):
            return {}

    bundle = SimpleNamespace(baseline_daily=[], temporal=[], anomaly=_Dump(), overall=_Dump())
    monkeypatch.setenv("MINIMAX_M27_MODEL", "MiniMaxAI/MiniMax-M2.7")
    worker = TemporalWorker(model_client=_RecordingClient())
    asyncio.run(worker.run(bundle, object(), model=None))  # type: ignore[arg-type]
    assert seen.get("model") == "MiniMaxAI/MiniMax-M2.7"
    assert default_m27_model() == "MiniMaxAI/MiniMax-M2.7"


def test_worker_model_override_honored():
    import asyncio
    from types import SimpleNamespace

    from backend.app.agents.workers import TemporalWorker

    seen: dict = {}

    class _RecordingClient:
        async def generate(self, prompt: str, **kw):
            seen.update(kw)
            return {"worker": "temporal"}

        async def close(self) -> None:
            pass

    class _Dump:
        def model_dump(self):
            return {}

    bundle = SimpleNamespace(baseline_daily=[], temporal=[], anomaly=_Dump(), overall=_Dump())
    worker = TemporalWorker(model_client=_RecordingClient())
    asyncio.run(worker.run(bundle, object(), model="custom-m27"))  # type: ignore[arg-type]
    assert seen.get("model") == "custom-m27"


def test_max_tokens_override_applies_to_live_requests(monkeypatch):
    import asyncio

    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(
            200, json={"choices": [{"message": {"content": "hi"}}]}
        )

    async def fake_get_client():
        return httpx.AsyncClient(
            transport=httpx.MockTransport(handler),
            base_url="https://unit.test",
            headers={"Authorization": "Bearer k"},
        )

    client = MiniMaxModelClient(
        ModelConfig(minimax_api_key="k", max_tokens_override=8192)
    )
    monkeypatch.setattr(client, "_get_client", fake_get_client)
    asyncio.run(client.generate("hi", max_tokens=64))
    body = json.loads(calls[0].content.decode())
    assert body["max_tokens"] == 8192


def test_live_implementations_selected_when_key_configured(monkeypatch):
    """Credential acceptance without network: selection + attribution only."""
    from backend.app.services.consultation.consultation_service import ConsultService
    from backend.app.services.consultation.speech_adapter import create_speech_provider

    monkeypatch.setenv("MINIMAX_API_KEY", "dummy-key-not-a-secret")
    monkeypatch.setenv("SPEECH_PROVIDER", "minimax")
    assert isinstance(create_model_client(), MiniMaxModelClient)
    assert create_speech_provider().name == "minimax"
    # Live answers are attributed to the configured model, never "stub".
    service = ConsultService()
    assert service._model_name == "MiniMax-M3"
    monkeypatch.delenv("MINIMAX_API_KEY")
    assert ConsultService()._model_name == "stub"


# ---------- Live Razorpay contract ----------

LINK_OK = {
    "id": "plink_TEST123",
    "reference_id": "act_x:pay_y",
    "status": "created",
    "amount": 50000,
    "amount_paid": 0,
    "currency": "INR",
    "short_url": "https://rzp.io/i/test123",
    "description": "Recovery",
    "expire_by": 1893456000,
    "created_at": 1754000000,
    "customer": {"id": "cust_T1", "name": "n", "email": "e@x.in", "contact": "+91"},
}


def _live_adapter(monkeypatch, handler) -> tuple[LiveRazorpayAdapter, list]:
    calls: list[httpx.Request] = []

    def wrapped(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return handler(request)

    adapter = LiveRazorpayAdapter(
        key_id="rzp_test_id", key_secret="rzp_test_secret", webhook_secret="wh"
    )

    def fake_get_client():
        # Mirror the production client auth; only transport is mocked.
        return httpx.AsyncClient(
            transport=httpx.MockTransport(wrapped),
            base_url="https://unit.test",
            auth=(adapter._key_id, adapter._key_secret),
        )

    monkeypatch.setattr(adapter, "_get_client", fake_get_client)
    return adapter, calls


def test_live_create_payment_link_contract(monkeypatch):
    import asyncio

    adapter, calls = _live_adapter(
        monkeypatch, lambda r: httpx.Response(201, json=LINK_OK)
    )
    link = asyncio.run(
        adapter.create_payment_link(
            amount_minor=50000, currency="INR", reference_id="act_x:pay_y"
        )
    )
    assert link.provider_id == "plink_TEST123"
    assert link.short_url == "https://rzp.io/i/test123"
    assert link.amount_minor == 50000
    req = calls[0]
    assert req.url.path == "/payment_links"
    assert req.headers["authorization"] == "Basic " + base64.b64encode(
        b"rzp_test_id:rzp_test_secret"
    ).decode()
    body = json.loads(req.content.decode())
    assert body["amount"] == 50000
    assert body["currency"] == "INR"
    assert body["reference_id"] == "act_x:pay_y"


def test_live_auth_and_conflict_errors(monkeypatch):
    import asyncio

    adapter, _ = _live_adapter(
        monkeypatch,
        lambda r: httpx.Response(
            401, json={"error": {"code": "BAD_REQUEST_ERROR", "description": "Invalid key"}}
        ),
    )
    with pytest.raises(ProviderAuthenticationError):
        asyncio.run(adapter.create_payment_link(amount_minor=100, reference_id="r"))

    adapter2, _ = _live_adapter(monkeypatch, lambda r: httpx.Response(409, json={}))
    with pytest.raises(ProviderConflictError):
        asyncio.run(adapter2.create_payment_link(amount_minor=100, reference_id="r"))

    adapter3, _ = _live_adapter(monkeypatch, lambda r: httpx.Response(502, json={}))
    with pytest.raises(ProviderUnavailableError):
        asyncio.run(adapter3.get_payment("pay_x"))


def test_live_get_link_404_returns_none_and_webhook_verify(monkeypatch):
    import asyncio
    import hashlib
    import hmac

    adapter, _ = _live_adapter(monkeypatch, lambda r: httpx.Response(404, json={}))
    assert asyncio.run(adapter.get_payment_link("plink_nope")) is None

    body = b'{"event":"payment_link.paid"}'
    sig = hmac.new(b"wh", body, hashlib.sha256).hexdigest()
    assert adapter.verify_webhook_signature(body, sig) is True
    assert adapter.verify_webhook_signature(body, "0" * 64) is False


def test_factory_selects_live_with_credentials(monkeypatch):
    import asyncio

    from backend.app.adapters.razorpay.factory import create_razorpay_adapter
    from backend.app.config import get_settings

    monkeypatch.setenv("RAZORPAY_MODE", "live")
    monkeypatch.setenv("RAZORPAY_KEY_ID", "rzp_test_id")
    monkeypatch.setenv("RAZORPAY_KEY_SECRET", "rzp_test_secret")
    get_settings.cache_clear()
    try:
        adapter = asyncio.run(create_razorpay_adapter())
        assert isinstance(adapter, LiveRazorpayAdapter)
    finally:
        get_settings.cache_clear()

    monkeypatch.delenv("RAZORPAY_KEY_ID")
    get_settings.cache_clear()
    try:
        with pytest.raises(RuntimeError, match="not configured"):
            asyncio.run(create_razorpay_adapter())
    finally:
        get_settings.cache_clear()


# ---------- M3 through the real consultation wiring ----------

MINIMAL_VIEW = {
    "case_id": "case_live",
    "symptom": {
        "title": "PAYMENT HEALTH INCIDENT DETECTED",
        "incident_type": "PAYMENT_METHOD_FAILURE_SPIKE",
        "start_time": "2026-07-31T14:37:00",
        "end_time": "2026-07-31T17:37:00",
        "affected_dimension": "payment_method",
        "affected_value": "UPI",
        "overall": {
            "baseline": {"failure_rate": 0.0454},
            "current": {"failure_rate": 0.2175},
            "relative_delta": 3.79,
        },
        "anomaly": {
            "anomaly_score": 10.854,
            "threshold": 3.0,
            "sample_size": 400,
        },
    },
    "diagnosis": {
        "leading_hypothesis": "PAYMENT_METHOD_DEGRADATION",
        "confidence": 0.91,
        "summary": "UPI degradation.",
        "supporting_evidence_ids": ["payment_method.UPI.failure_rate"],
        "alternative_hypotheses": [],
        "recommended_action_type": "CREATE_PAYMENT_LINK",
        "action_rationale": "Re-collect.",
        "uncertainties": [],
        "evidence": [],
    },
    "prescription": {
        "action_type": "CREATE_PAYMENT_LINK",
        "status": "PLANNED",
        "targets_count": 10,
        "total_amount_minor": 10000,
        "currency": "INR",
        "rationale": "Re-collect.",
        "targets": [],
    },
    "policy": {"decision": "HUMAN_APPROVAL_REQUIRED", "passed": True,
               "failed_checks": [], "checks": []},
    "approval": {"status": "APPROVED", "decided_by": "human"},
    "treatment": {"status": "SUCCEEDED", "provider_operation": "create_payment_link",
                  "links_count": 10},
    "outcome": {
        "status": "PARTIALLY_RECOVERED",
        "targets_total": 10,
        "targets_succeeded": 7,
        "targets_pending": 2,
        "targets_failed": 0,
        "targets_expired": 1,
        "amount_targeted_minor": 10000,
        "amount_recovered_minor": 7000,
        "conversion_rate": 0.7,
    },
}


def test_m3_answers_through_real_client_wiring(monkeypatch):
    import asyncio

    answer = "The treatment status is PARTIALLY_RECOVERED: recovered \u20b970."
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": json.dumps({
                "answer": answer,
                "answer_type": "outcome",
                "referenced_sections": ["outcome", "bogus_section"],
            })}}]},
        )

    live = MiniMaxModelClient(ModelConfig(minimax_api_key="k"))

    async def fake_get_client():
        return httpx.AsyncClient(
            transport=httpx.MockTransport(handler),
            base_url="https://unit.test",
            headers={"Authorization": "Bearer k", "Content-Type": "application/json"},
        )

    monkeypatch.setattr(live, "_get_client", fake_get_client)
    service = ConsultService(
        model_client=live,
        config=ConsultConfig(cooldown_seconds=0),
        model_name="MiniMax-M3",
    )
    history: list[dict] = []
    response, _ = asyncio.run(
        service.consult(dict(MINIMAL_VIEW), "Did it work?", history=history, last_at=None)
    )
    assert response.answer == answer
    assert response.model == "MiniMax-M3"
    # Sections come from the deterministic answer-type map (the model cannot
    # inject section names): OUTCOME -> [outcome, execution].
    assert [s.value for s in response.referenced_sections] == ["outcome", "execution"]
    assert calls and calls[0].url.path == "/chat/completions"
    assert history and history[0]["question"] == "Did it work?"
