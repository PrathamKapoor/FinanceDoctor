"""Outcome API endpoints (Stage 5).

The endpoints are deliberately *read-only* plus one explicit
``POST /outcomes/{id}/evaluate`` that **only** recalculates and
evaluates existing state. There is no ``PUT /outcomes/...`` or
``POST /outcomes/{id}/finalize-payment`` endpoint — the only way the
outcome layer advances is via the verified webhook boundary or
deterministic recalculation.
"""

from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from backend.app.services.outcome.case_summary import CaseSummaryService
from backend.app.services.outcome.outcome_evaluator import OutcomeEvaluator
from backend.app.services.outcome.outcome_store import AuditStore, OutcomeStore

router = APIRouter(prefix="/outcomes", tags=["outcomes"])


class EvaluateResponse(BaseModel):
    outcome_id: str
    status: str
    targets_total: int
    targets_pending: int
    targets_succeeded: int
    targets_failed: int
    targets_expired: int
    amount_targeted_minor: int
    amount_recovered_minor: int
    conversion_rate: float | None
    finalized: bool
    effectiveness: dict[str, Any] | None
    latency_ms: int


class TargetsResponse(BaseModel):
    outcome_id: str
    targets: list[dict[str, Any]]


class AuditResponse(BaseModel):
    outcome_id: str | None
    target_outcome_id: str | None
    events: list[dict[str, Any]]


class CaseSummaryResponse(BaseModel):
    case_summary_id: str
    incident_type: str | None
    investigation_id: str | None
    diagnosis_id: str | None
    action_id: str | None
    approval_id: str | None
    execution_id: str | None
    outcome_id: str | None
    symptom: str | None
    diagnosis: str | None
    prescription: str | None
    approval_status: str | None
    treatment_status: str | None
    outcome_status: str | None
    lineage: list[dict[str, Any]]
    treatment_effectiveness: dict[str, Any] | None


class MetricsResponse(BaseModel):
    events_processed: int
    events_duplicated: int
    events_unrelated: int
    events_ignored: int
    targets_evaluated: int
    aggregation_latency_ms_avg: float


def _services(request: Request) -> tuple[OutcomeStore, AuditStore, OutcomeEvaluator]:
    outcome_store = request.app.state.outcome_store
    audit_store = request.app.state.audit_store
    evaluator = request.app.state.outcome_evaluator
    return outcome_store, audit_store, evaluator


@router.get("/metrics", response_model=MetricsResponse)
async def metrics(request: Request) -> MetricsResponse:
    handler = getattr(request.app.state, "webhook_handler", None)
    if handler is None:
        return MetricsResponse(
            events_processed=0,
            events_duplicated=0,
            events_unrelated=0,
            events_ignored=0,
            targets_evaluated=0,
            aggregation_latency_ms_avg=0.0,
        )
    m = handler.metrics
    return MetricsResponse(**m)


@router.get("/{outcome_id}", response_model=EvaluateResponse)
async def get_outcome(outcome_id: str, request: Request) -> EvaluateResponse:
    outcome_store, _audit_store, evaluator = _services(request)
    outcome = outcome_store.get_outcome(outcome_id)
    if outcome is None:
        raise HTTPException(status_code=404, detail="Outcome not found")
    eff = evaluator.compute_effectiveness(outcome_id)
    return EvaluateResponse(
        outcome_id=outcome.outcome_id,
        status=outcome.status.value,
        targets_total=outcome.targets_total,
        targets_pending=outcome.targets_pending,
        targets_succeeded=outcome.targets_succeeded,
        targets_failed=outcome.targets_failed,
        targets_expired=outcome.targets_expired,
        amount_targeted_minor=outcome.amount_targeted_minor,
        amount_recovered_minor=outcome.amount_recovered_minor,
        conversion_rate=outcome.conversion_rate,
        finalized=outcome.is_terminal(),
        effectiveness=eff.model_dump(),
        latency_ms=0,
    )


@router.get("/{outcome_id}/targets", response_model=TargetsResponse)
async def list_targets(outcome_id: str, request: Request) -> TargetsResponse:
    outcome_store, _audit_store, _evaluator = _services(request)
    outcome = outcome_store.get_outcome(outcome_id)
    if outcome is None:
        raise HTTPException(status_code=404, detail="Outcome not found")
    targets = outcome_store.list_targets_for_outcome(outcome_id)
    return TargetsResponse(
        outcome_id=outcome_id,
        targets=[t.to_summary() for t in targets],
    )


@router.post("/{outcome_id}/evaluate", response_model=EvaluateResponse)
async def evaluate(outcome_id: str, request: Request) -> EvaluateResponse:
    """Re-aggregate and finalize (if expired) — does NOT execute a new action."""
    outcome_store, _audit_store, evaluator = _services(request)
    outcome = outcome_store.get_outcome(outcome_id)
    if outcome is None:
        raise HTTPException(status_code=404, detail="Outcome not found")
    started_at = time.perf_counter()
    evaluator.recalculate(outcome_id)
    evaluator.finalize_expired(outcome_id)
    elapsed_ms = int((time.perf_counter() - started_at) * 1000)
    refreshed = outcome_store.get_outcome(outcome_id)
    assert refreshed is not None
    eff = evaluator.compute_effectiveness(outcome_id)
    return EvaluateResponse(
        outcome_id=refreshed.outcome_id,
        status=refreshed.status.value,
        targets_total=refreshed.targets_total,
        targets_pending=refreshed.targets_pending,
        targets_succeeded=refreshed.targets_succeeded,
        targets_failed=refreshed.targets_failed,
        targets_expired=refreshed.targets_expired,
        amount_targeted_minor=refreshed.amount_targeted_minor,
        amount_recovered_minor=refreshed.amount_recovered_minor,
        conversion_rate=refreshed.conversion_rate,
        finalized=refreshed.is_terminal(),
        effectiveness=eff.model_dump(),
        latency_ms=elapsed_ms,
    )


@router.get("/{outcome_id}/audit", response_model=AuditResponse)
async def outcome_audit(outcome_id: str, request: Request) -> AuditResponse:
    outcome_store, audit_store, _evaluator = _services(request)
    outcome = outcome_store.get_outcome(outcome_id)
    if outcome is None:
        raise HTTPException(status_code=404, detail="Outcome not found")
    events = audit_store.list_for_entity("outcome", outcome_id)
    return AuditResponse(
        outcome_id=outcome_id,
        target_outcome_id=None,
        events=[e.model_dump(mode="json") for e in events],
    )


@router.get(
    "/{outcome_id}/audit/targets/{target_outcome_id}",
    response_model=AuditResponse,
)
async def target_audit(
    outcome_id: str, target_outcome_id: str, request: Request
) -> AuditResponse:
    outcome_store, audit_store, _evaluator = _services(request)
    outcome = outcome_store.get_outcome(outcome_id)
    if outcome is None:
        raise HTTPException(status_code=404, detail="Outcome not found")
    events = audit_store.list_for_entity("target_outcome", target_outcome_id)
    return AuditResponse(
        outcome_id=outcome_id,
        target_outcome_id=target_outcome_id,
        events=[e.model_dump(mode="json") for e in events],
    )


def build_case_summary_service(request: Request) -> CaseSummaryService:
    """Wire the case-summary service to whatever resolvers the app exposes."""
    outcome_store = request.app.state.outcome_store
    evaluator = request.app.state.outcome_evaluator
    resolvers = getattr(request.app.state, "case_resolvers", {}) or {}
    return CaseSummaryService(
        outcome_store=outcome_store,
        evaluator=evaluator,
        action_resolver=resolvers.get("action"),
        investigation_resolver=resolvers.get("investigation"),
        diagnosis_resolver=resolvers.get("diagnosis"),
        approval_resolver=resolvers.get("approval"),
        execution_resolver=resolvers.get("execution"),
    )


@router.get("/{outcome_id}/case", response_model=CaseSummaryResponse)
async def get_case_for_outcome(outcome_id: str, request: Request) -> CaseSummaryResponse:
    summary = build_case_summary_service(request).build_for_outcome(outcome_id)
    return CaseSummaryResponse(**summary.model_dump(mode="json"))


__all__ = ["router", "build_case_summary_service"]