"""Deterministic read-model for the Financial Doctor case journey.

The frontend consumes a single ``dict`` assembled from the ``DemoCaseSession``
artifacts. Nothing here invokes M3, executes an action, or mutates financial
state — it only serializes records that already exist.
"""

from __future__ import annotations

from typing import Any

from backend.app.services.demo.session import (
    STAGE_APPROVAL,
    STAGE_DIAGNOSIS,
    STAGE_INVESTIGATION,
    STAGE_OUTCOME,
    STAGE_PRESCRIPTION,
    STAGE_SAFETY,
    STAGE_SYMPTOM,
    STAGE_TREATMENT,
    DemoCaseSession,
)
from backend.app.services.evidence import flatten


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def build_read_model(session: DemoCaseSession) -> dict[str, Any]:
    """Assemble the full read-model from the session's existing records."""
    model: dict[str, Any] = {
        "case_id": session.case_id,
        "environment": session.mode,
        "started_at": session.started_at.isoformat(),
        "stages": _stages(session),
        "timeline": session.timeline,
    }

    # ---- Stage 1 — symptom / incident ----
    symptom = _build_symptom(session)
    if symptom is not None:
        model["symptom"] = symptom
        model["health"] = _build_health(session)

    # ---- Stage 3 — investigation + diagnosis ----
    if session.investigation is not None:
        model["investigation"] = _build_investigation(session)
    if session.diagnosis is not None:
        model["diagnosis"] = _build_diagnosis(session)

    # ---- Stage 4 — prescription + policy + approval ----
    if session.action is not None:
        model["prescription"] = _build_prescription(session)
    if session.policy_decision is not None:
        model["policy"] = _build_policy(session)
    if session.approval is not None:
        model["approval"] = _build_approval(session)

    # ---- Stage 4/5 — treatment + outcome ----
    if session.execution is not None:
        model["treatment"] = _build_treatment(session)
    model["outcome"] = _build_outcome(session)

    return model


def _stages(session: DemoCaseSession) -> list[dict[str, Any]]:
    done = {entry["stage"] for entry in session.timeline}
    labels = {
        STAGE_SYMPTOM: "Symptom",
        STAGE_INVESTIGATION: "Investigation",
        STAGE_DIAGNOSIS: "Diagnosis",
        STAGE_PRESCRIPTION: "Prescription",
        STAGE_SAFETY: "Safety check",
        STAGE_APPROVAL: "Approval",
        STAGE_TREATMENT: "Treatment",
        STAGE_OUTCOME: "Outcome",
    }
    stages: list[dict[str, Any]] = []
    for stage in (STAGE_SYMPTOM, STAGE_INVESTIGATION, STAGE_DIAGNOSIS,
                  STAGE_PRESCRIPTION, STAGE_SAFETY, STAGE_APPROVAL,
                  STAGE_TREATMENT, STAGE_OUTCOME):
        status = _stage_status(session, stage)
        stages.append(
            {
                "key": stage,
                "label": labels[stage],
                "complete": stage in done,
                "status": status,
                "active": _is_active_stage(session, stage),
            }
        )
    return stages


def _stage_status(session: DemoCaseSession, stage: str) -> str | None:
    for entry in session.timeline:
        if entry["stage"] == stage:
            return str(entry["status"])
    return None


def _is_active_stage(session: DemoCaseSession, stage: str) -> bool:
    done = [entry["stage"] for entry in session.timeline]
    if stage in done:
        return False
    # First non-completed stage in order is the active one.
    for candidate in (
        STAGE_SYMPTOM, STAGE_INVESTIGATION, STAGE_DIAGNOSIS, STAGE_PRESCRIPTION,
        STAGE_SAFETY, STAGE_APPROVAL, STAGE_TREATMENT, STAGE_OUTCOME,
    ):
        if candidate not in done:
            return candidate == stage
    return False


def _build_symptom(session: DemoCaseSession) -> dict[str, Any] | None:
    if session.world is None:
        return None
    from backend.app.services.analytics import AnalyticsEngine

    engine = AnalyticsEngine(session.world)
    overall = engine.overall()
    anomaly = engine.anomaly()
    incident = session.world.ground_truth
    return {
        "title": "PAYMENT HEALTH INCIDENT DETECTED",
        "incident_type": incident.incident_type if incident else None,
        "start_time": _iso(incident.start_time) if incident else None,
        "end_time": _iso(incident.end_time) if incident else None,
        "affected_dimension": incident.affected_dimension if incident else None,
        "affected_value": incident.affected_value if incident else None,
        "overall": {
            "baseline": overall.baseline.model_dump(),
            "current": overall.current.model_dump(),
            "absolute_delta": overall.absolute_delta,
            "relative_delta": overall.relative_delta,
        },
        "anomaly": anomaly.model_dump(),
    }


def _build_health(session: DemoCaseSession) -> dict[str, Any]:
    from backend.app.services.analytics import AnalyticsEngine

    engine = AnalyticsEngine(session.world)
    return {
        "baseline_daily": [b.model_dump() for b in engine.baseline_daily()],
        "temporal": [t.model_dump() for t in engine.temporal_hourly()],
        "payment_methods": [m.model_dump() for m in engine.payment_methods()],
        "cohorts": [c.model_dump() for c in engine.cohorts()],
        "failure_reasons": [r.model_dump() for r in engine.failure_reasons()],
        "monetary": engine.monetary().model_dump(),
    }


def _build_investigation(session: DemoCaseSession) -> dict[str, Any]:
    assert session.investigation is not None
    investigation = session.investigation
    workers: list[dict[str, Any]] = []
    for name, output in session.worker_outputs.items():
        if hasattr(output, "model_dump"):
            workers.append(output.model_dump(mode="json"))
        else:
            workers.append({"worker": name, **output})
    return {
        "investigation_id": investigation.investigation_id,
        "state": investigation.state.value,
        "anomaly_detected": investigation.anomaly_detected,
        "anomaly_score": investigation.anomaly_score,
        "workers": workers,
    }


def _build_diagnosis(session: DemoCaseSession) -> dict[str, Any]:
    assert session.diagnosis is not None
    diagnosis = session.diagnosis
    evidence: list[dict[str, Any]] = []
    if session.bundle is not None:
        evidence = [e.model_dump() for e in flatten(session.bundle)]
    result = diagnosis.model_dump(mode="json")
    result["evidence"] = evidence
    return result


def _build_prescription(session: DemoCaseSession) -> dict[str, Any]:
    assert session.action is not None
    action = session.action
    return {
        "action_id": action.action_id,
        "action_type": action.action_type.value,
        "status": action.status.value,
        "targets_count": len(action.targets),
        "total_amount_minor": action.total_amount_minor,
        "currency": action.currency,
        "rationale": action.rationale,
        "targets": [
            {
                "payment_id": t.payment_id,
                "payment_method": t.payment_method,
                "failure_reason": t.failure_reason,
                "amount_minor": t.amount_minor,
                "currency": t.currency,
            }
            for t in action.targets
        ],
    }


def _build_policy(session: DemoCaseSession) -> dict[str, Any]:
    assert session.policy_decision is not None
    decision = session.policy_decision
    return {
        "decision": decision.decision.value,
        "policy_version": decision.policy_version,
        "reasons": decision.reasons,
        "action_snapshot_hash": decision.action_snapshot_hash,
        "passed": decision.passed,
        "failed_checks": [c.check for c in decision.failed_checks],
        "checks": [
            {
                "check": c.check,
                "status": c.status.value,
                "actual": c.actual,
                "limit": c.limit,
                "message": c.message,
            }
            for c in decision.checks
        ],
    }


def _build_approval(session: DemoCaseSession) -> dict[str, Any]:
    assert session.approval is not None
    approval = session.approval
    return {
        "approval_id": approval.approval_id,
        "action_id": approval.action_id,
        "status": approval.status.value,
        "requested_at": _iso(approval.requested_at),
        "expires_at": _iso(approval.expires_at),
        "approved_at": _iso(approval.approved_at),
        "rejected_at": _iso(approval.rejected_at),
        "decision_reason": approval.decision_reason,
        "decided_by": approval.decided_by,
        "expired": approval.is_expired,
    }


def _build_treatment(session: DemoCaseSession) -> dict[str, Any]:
    assert session.execution is not None
    execution = session.execution
    links = (execution.provider_response or {}).get("links", [])
    return {
        "execution_id": execution.execution_id,
        "action_id": execution.action_id,
        "status": execution.status.value,
        "provider": execution.provider,
        "provider_operation": execution.provider_operation,
        "provider_reference": execution.provider_reference,
        "links_count": len(links),
        "started_at": _iso(execution.started_at),
        "completed_at": _iso(execution.completed_at),
        "error_code": execution.error_code,
        "error_message": execution.error_message,
    }


def _build_outcome(session: DemoCaseSession) -> dict[str, Any] | None:
    if session.action is None:
        return None
    outcome = session.outcome_store.get_outcome_by_action(session.action.action_id)
    if outcome is None:
        return None
    effectiveness = session.evaluator.compute_effectiveness(outcome.outcome_id)
    return {
        "outcome_id": outcome.outcome_id,
        "status": outcome.status.value,
        "targets_total": outcome.targets_total,
        "targets_pending": outcome.targets_pending,
        "targets_succeeded": outcome.targets_succeeded,
        "targets_failed": outcome.targets_failed,
        "targets_expired": outcome.targets_expired,
        "amount_targeted_minor": outcome.amount_targeted_minor,
        "amount_recovered_minor": outcome.amount_recovered_minor,
        "conversion_rate": outcome.conversion_rate,
        "currency": outcome.currency,
        "finalized": outcome.is_terminal(),
        "effectiveness": effectiveness.model_dump(mode="json"),
    }