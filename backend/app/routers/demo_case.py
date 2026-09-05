"""Demo case API — the Stage 6 frontend's single integration surface.

These endpoints are the safe, deterministic wrapper around Stage 1–5 that the
case journey UI consumes. Mutations (approve / reject / execute / simulate)
all flow through the same controlled service boundaries as the golden test:

- ``approve`` / ``reject``         → ``ApprovalService`` (human gate)
- ``execute``                      → ``ActionExecutor`` (post-approval, atomic hash check)
- ``simulate``                     → ``StubProviderSimulator`` → verified webhook boundary

A financial action is never executed from the frontend directly, and amounts /
targets / provider operations are never modifiable from the UI.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from backend.app.adapters.razorpay.models import NormalizedWebhookEvent
from backend.app.services.consultation.consultation_service import (
    ConsultationError,
    ConsultRateLimited,
    ConsultService,
    ConsultValidationError,
)
from backend.app.services.consultation.speech_adapter import (
    SpeechError,
    create_speech_provider,
)
from backend.app.services.demo.read_model import build_read_model
from backend.app.services.demo.session import (
    STAGE_APPROVAL,
    STAGE_TREATMENT,
    DemoCaseSession,
    run_demo_case,
)
from backend.app.services.outcome.stub_provider import StubProviderSimulator

router = APIRouter(prefix="/demo/case", tags=["demo-case"])


class StartRequest(BaseModel):
    seed: int | None = None
    num_orders: int | None = None
    num_customers: int | None = None


class DecideRequest(BaseModel):
    decided_by: str = "demo_operator"
    reason: str | None = None


class SimulateRequest(BaseModel):
    recovered_count: int | None = None


class ConsultRequest(BaseModel):
    question: str


def _store(request: Request):
    return request.app.state.demo_store


def _require_session(request: Request, case_id: str) -> DemoCaseSession:
    session = _store(request).get(case_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Demo case not found")
    return session


@router.post("/start")
async def start(payload: StartRequest, request: Request) -> dict[str, Any]:
    session = await run_demo_case(
        seed=payload.seed,
        num_orders=payload.num_orders,
        num_customers=payload.num_customers,
    )
    _store(request).put(session)
    return build_read_model(session)


@router.get("/{case_id}")
async def get_case(case_id: str, request: Request) -> dict[str, Any]:
    session = _require_session(request, case_id)
    return build_read_model(session)


@router.post("/{case_id}/approve")
async def approve(case_id: str, payload: DecideRequest, request: Request) -> dict[str, Any]:
    session = _require_session(request, case_id)
    if session.approval is None:
        raise HTTPException(status_code=409, detail="No approval request to decide")
    if session.approval.status.value not in ("PENDING",):
        raise HTTPException(status_code=409, detail="Approval already decided")
    try:
        session.approval_service.approve(
            session.approval.approval_id, payload.decided_by, payload.reason
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    session.completed_stage(STAGE_APPROVAL, "APPROVED", note=f"Approved by {payload.decided_by}")
    return build_read_model(session)


@router.post("/{case_id}/reject")
async def reject(case_id: str, payload: DecideRequest, request: Request) -> dict[str, Any]:
    session = _require_session(request, case_id)
    if session.approval is None:
        raise HTTPException(status_code=409, detail="No approval request to decide")
    if session.approval.status.value != "PENDING":
        raise HTTPException(status_code=409, detail="Approval already decided")
    try:
        session.approval_service.reject(
            session.approval.approval_id, payload.decided_by, payload.reason
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    session.completed_stage(STAGE_APPROVAL, "REJECTED", note=f"Rejected by {payload.decided_by}")
    return build_read_model(session)


@router.post("/{case_id}/execute")
async def execute(case_id: str, request: Request) -> dict[str, Any]:
    session = _require_session(request, case_id)
    if session.action is None or session.approval is None:
        raise HTTPException(status_code=409, detail="Case is not ready to execute")
    if session.approval.status.value != "APPROVED":
        raise HTTPException(
            status_code=409,
            detail="Approval has not been granted — cannot execute a financial action",
        )
    if session.executor is None:
        raise HTTPException(status_code=500, detail="Executor not initialized")
    if session.execution is not None:
        # Idempotent: a prior execution already exists for this case.
        return build_read_model(session)

    from backend.app.services.action.executor import ExecutionError

    try:
        execution = await session.executor.execute(session.action, session.approval)
    except ExecutionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    session.execution = execution
    session.completed_stage(
        STAGE_TREATMENT, execution.status.value, note="Payment Link recovery executed"
    )
    return build_read_model(session)


@router.post("/{case_id}/simulate")
async def simulate(case_id: str, payload: SimulateRequest, request: Request) -> dict[str, Any]:
    """Simulate provider webhooks to advance the outcome deterministically.

    This is the *only* way the outcome advances — through the verified webhook
    boundary, exactly as production would receive ``payment_link.paid`` /
    ``payment_link.cancelled``. No outcome status is set directly here.
    """
    session = _require_session(request, case_id)
    if session.execution is None:
        raise HTTPException(status_code=409, detail="No execution to observe yet")
    if session.action is None or session.stub_adapter is None:
        raise HTTPException(status_code=409, detail="Case is not fully initialized")

    outcome = session.outcome_store.get_outcome_by_action(session.action.action_id)
    if outcome is None:
        raise HTTPException(status_code=409, detail="No outcome initialized")
    targets = session.outcome_store.list_targets_for_outcome(outcome.outcome_id)
    total = len(targets)
    if total == 0:
        return build_read_model(session)

    # Default: deterministic partial recovery (~70% paid, one expired).
    recovered = payload.recovered_count
    if recovered is None:
        recovered = max(1, round(total * 0.7))
    recovered = min(recovered, total)

    simulator = StubProviderSimulator(session.stub_adapter, session.webhook_secret)

    for i, target in enumerate(targets):
        if i < recovered:
            link_id = target.payment_link_id
            if link_id is None:
                continue
            simulator.mark_payment_link_paid(link_id)
            payload_map, _body = simulator.build_payment_link_paid_payload(link_id)
            event = NormalizedWebhookEvent(
                event="payment_link.paid",
                payload=payload_map["payload"],
                raw=payload_map,
            )
            session.webhook_handler.process_event(event)
        elif i == recovered and total - recovered >= 1:
            # Deterministic expiry for a single pending target.
            link_id = target.payment_link_id
            if link_id is None:
                continue
            simulator.mark_payment_link_expired(link_id)
            event = NormalizedWebhookEvent(
                event="payment_link.cancelled",
                payload={"payment_link": {"id": link_id}},
                raw={"event": "payment_link.cancelled"},
            )
            session.webhook_handler.process_event(event)

    session.evaluator.recalculate(outcome.outcome_id)
    return build_read_model(session)


@router.post("/{case_id}/consult")
async def consult(case_id: str, payload: ConsultRequest, request: Request) -> dict[str, Any]:
    """Ask the Financial Doctor about this case (read-only consultation).

    The question is answered from the case read-model only. This endpoint
    cannot approve, execute, or mutate anything — consultation carries no
    action tools, adapters, or mutation handles by construction.
    """
    import time

    session = _require_session(request, case_id)
    question = (payload.question or "").strip()
    if not question:
        raise HTTPException(status_code=422, detail="Question must not be empty")
    if len(question) > 1000:
        raise HTTPException(status_code=422, detail="Question exceeds 1000 characters")

    service = ConsultService()
    started = time.perf_counter()
    try:
        response, new_last_at = await service.consult(
            build_read_model(session),
            question,
            history=session.consultations,
            last_at=session.last_consult_at,
        )
    except ConsultValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ConsultRateLimited as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except ConsultationError as exc:
        raise HTTPException(
            status_code=502,
            detail="Consultation temporarily unavailable. "
            "Your Financial Doctor case data remains available.",
        ) from exc
    session.last_consult_at = new_last_at
    out = response.model_dump(mode="json")
    out["timings"]["total_latency_ms"] = int((time.perf_counter() - started) * 1000)
    return out


@router.get("/{case_id}/consultations")
async def list_consultations(case_id: str, request: Request) -> dict[str, Any]:
    """Case-scoped consultation history (question/answer metadata only)."""
    session = _require_session(request, case_id)
    return {"case_id": case_id, "consultations": session.consultations}


@router.post("/{case_id}/consultations/{consultation_id}/audio")
async def consultation_audio(
    case_id: str, consultation_id: str, request: Request
) -> dict[str, Any]:
    """Synthesize the stored answer for a consultation (user-initiated playback).

    Only a previously recorded answer for THIS case can be voiced — the
    endpoint accepts no free text, so it cannot be used as a generic TTS
    proxy. Speech failures never affect case state.
    """
    import time

    session = _require_session(request, case_id)
    record = next(
        (c for c in session.consultations if c.get("consultation_id") == consultation_id),
        None,
    )
    if record is None:
        raise HTTPException(status_code=404, detail="Consultation not found")
    answer = str(record.get("answer", "")).strip()
    if not answer:
        raise HTTPException(status_code=409, detail="Nothing to synthesize")

    provider = create_speech_provider()
    started = time.perf_counter()
    try:
        result = await provider.synthesize(answer[:2000])
    except SpeechError as exc:
        raise HTTPException(
            status_code=502,
            detail="Speech synthesis unavailable. The text answer above remains available.",
        ) from exc
    out = result.model_dump(mode="json")
    out["consultation_id"] = consultation_id
    out["speech_latency_ms"] = int((time.perf_counter() - started) * 1000)
    return out


__all__ = ["router"]