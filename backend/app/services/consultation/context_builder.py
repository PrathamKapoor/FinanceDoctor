"""Deterministic consultation-context builder (Stage 7A).

Converts the existing ``CaseView`` read-model dict into a structured,
AI-safe ``ConsultationContext``. This is the ONLY data the consultation
model ever sees — it cannot look around the system, run SQL, or call tools.

Redaction policy (minimum necessary context):
- per-target ``payment_id`` / ``order_id`` / ``customer_id`` are dropped;
  only aggregate counts, methods, reasons, and amounts survive;
- snapshot hashes, provider references beyond the primary link id, webhook
  secrets, API keys, and auth tokens are never included (they are not in
  ``CaseView`` either, and nothing here re-adds them).
"""

from __future__ import annotations

from typing import Any

from backend.app.services.consultation.models import ConsultationContext


def _pct(value: Any) -> str | None:
    try:
        if value is None:
            return None
        return f"{float(value) * 100:.2f}%"
    except (TypeError, ValueError):
        return None


def _rupees(minor: Any) -> str | None:
    try:
        if minor is None:
            return None
        return f"₹{int(minor) // 100:,}"
    except (TypeError, ValueError):
        return None


class ConsultationContextBuilder:
    """Build a redacted ``ConsultationContext`` from a ``CaseView`` dict."""

    def build(self, case_view: dict[str, Any]) -> ConsultationContext:
        case_id = str(case_view.get("case_id", "unknown"))
        key_figures: dict[str, str] = {}

        incident = self._incident(case_view.get("symptom"), key_figures)
        metrics = self._metrics(case_view.get("symptom"), key_figures)
        investigation = self._investigation(case_view.get("investigation"))
        diagnosis = self._diagnosis(case_view.get("diagnosis"), key_figures)
        evidence = self._evidence(case_view.get("diagnosis"))
        recommended_action = self._action(case_view.get("prescription"), key_figures)
        policy_status = self._policy(case_view.get("policy"))
        approval_status = self._approval(case_view.get("approval"))
        execution_status = self._execution(case_view.get("treatment"))
        outcome = self._outcome(case_view.get("outcome"), key_figures)

        return ConsultationContext(
            case_id=case_id,
            incident=incident,
            metrics=metrics,
            investigation=investigation,
            diagnosis=diagnosis,
            evidence=evidence,
            recommended_action=recommended_action,
            policy_status=policy_status,
            approval_status=approval_status,
            execution_status=execution_status,
            outcome=outcome,
            key_figures=key_figures,
        )

    # ---- sections ----

    def _incident(
        self, symptom: dict[str, Any] | None, key_figures: dict[str, str]
    ) -> dict[str, Any]:
        if not symptom:
            return {"present": False}
        anomaly = symptom.get("anomaly") or {}
        overall = symptom.get("overall") or {}
        current = overall.get("current") or {}
        baseline = overall.get("baseline") or {}
        out: dict[str, Any] = {
            "present": True,
            "title": symptom.get("title"),
            "incident_type": symptom.get("incident_type"),
            "start_time": symptom.get("start_time"),
            "end_time": symptom.get("end_time"),
            "affected_dimension": symptom.get("affected_dimension"),
            "affected_value": symptom.get("affected_value"),
            "baseline_failure_rate": _pct(baseline.get("failure_rate")),
            "current_failure_rate": _pct(current.get("failure_rate")),
            "relative_increase": (
                f"{float(overall.get('relative_delta', 0)):.2f}x"
                if overall.get("relative_delta") is not None
                else None
            ),
            "anomaly_score": anomaly.get("anomaly_score"),
            "anomaly_threshold": anomaly.get("threshold"),
            "sample_size": anomaly.get("sample_size"),
        }
        for k in ("baseline_failure_rate", "current_failure_rate"):
            if out[k]:
                key_figures[k] = out[k]
        return out

    def _metrics(
        self, symptom: dict[str, Any] | None, key_figures: dict[str, str]
    ) -> dict[str, Any]:
        # Per-method / cohort / reason aggregates only — no identifiers.
        # The read-model nests these under "health"; accept it if present.
        return {"present": symptom is not None}

    def _investigation(self, investigation: dict[str, Any] | None) -> dict[str, Any]:
        if not investigation:
            return {"present": False}
        workers = []
        for w in investigation.get("workers", []):
            workers.append(
                {
                    "worker": w.get("worker"),
                    "finding": w.get("finding"),
                    "supports": w.get("supports", []),
                    "contradicts": w.get("contradicts", []),
                    "confidence": w.get("confidence"),
                }
            )
        return {
            "present": True,
            "state": investigation.get("state"),
            "anomaly_detected": investigation.get("anomaly_detected"),
            "workers": workers,
        }

    def _diagnosis(
        self, diagnosis: dict[str, Any] | None, key_figures: dict[str, str]
    ) -> dict[str, Any]:
        if not diagnosis:
            return {"present": False}
        return {
            "present": True,
            "leading_hypothesis": diagnosis.get("leading_hypothesis"),
            "confidence": diagnosis.get("confidence"),
            "summary": diagnosis.get("summary"),
            "supporting_evidence_ids": diagnosis.get("supporting_evidence_ids", []),
            "alternative_hypotheses": diagnosis.get("alternative_hypotheses", []),
            "recommended_action_type": diagnosis.get("recommended_action_type"),
            "action_rationale": diagnosis.get("action_rationale"),
            "uncertainties": diagnosis.get("uncertainties", []),
        }

    def _evidence(self, diagnosis: dict[str, Any] | None) -> list[dict[str, Any]]:
        if not diagnosis:
            return []
        items = []
        for e in diagnosis.get("evidence", []):
            items.append(
                {
                    "id": e.get("id"),
                    "kind": e.get("kind"),
                    "metric": e.get("metric"),
                    "value": e.get("value"),
                    "unit": e.get("unit"),
                    "baseline": e.get("baseline"),
                    "current": e.get("current"),
                    "delta": e.get("delta"),
                    "dimension": e.get("dimension"),
                }
            )
        return items

    def _action(
        self, prescription: dict[str, Any] | None, key_figures: dict[str, str]
    ) -> dict[str, Any]:
        if not prescription:
            return {"present": False}
        targets = prescription.get("targets", []) or []
        methods: dict[str, int] = {}
        reasons: dict[str, int] = {}
        for t in targets:
            methods[str(t.get("payment_method"))] = (
                methods.get(str(t.get("payment_method")), 0) + 1
            )
            reasons[str(t.get("failure_reason"))] = (
                reasons.get(str(t.get("failure_reason")), 0) + 1
            )
        total = _rupees(prescription.get("total_amount_minor"))
        if total:
            key_figures["total_eligible_amount"] = total
        return {
            "present": True,
            "action_type": prescription.get("action_type"),
            "status": prescription.get("status"),
            "targets_count": prescription.get("targets_count"),
            "total_amount": total,
            "currency": prescription.get("currency"),
            "rationale": prescription.get("rationale"),
            "methods": methods,
            "failure_reasons": reasons,
        }

    def _policy(self, policy: dict[str, Any] | None) -> dict[str, Any]:
        if not policy:
            return {"present": False}
        checks = [
            {"check": c.get("check"), "status": c.get("status")}
            for c in policy.get("checks", [])
        ]
        return {
            "present": True,
            "decision": policy.get("decision"),
            "passed": policy.get("passed"),
            "failed_checks": policy.get("failed_checks", []),
            "checks": checks,
        }

    def _approval(self, approval: dict[str, Any] | None) -> dict[str, Any]:
        if not approval:
            return {"present": False}
        return {
            "present": True,
            "status": approval.get("status"),
            "decided_by": approval.get("decided_by"),
        }

    def _execution(self, treatment: dict[str, Any] | None) -> dict[str, Any]:
        if not treatment:
            return {"present": False}
        return {
            "present": True,
            "status": treatment.get("status"),
            "provider_operation": treatment.get("provider_operation"),
            "links_count": treatment.get("links_count"),
        }

    def _outcome(
        self, outcome: dict[str, Any] | None, key_figures: dict[str, str]
    ) -> dict[str, Any]:
        if not outcome:
            return {"present": False}
        recovered = _rupees(outcome.get("amount_recovered_minor"))
        targeted = _rupees(outcome.get("amount_targeted_minor"))
        if recovered:
            key_figures["amount_recovered"] = recovered
        if targeted:
            key_figures["amount_targeted"] = targeted
        rate = outcome.get("conversion_rate")
        out: dict[str, Any] = {
            "present": True,
            "status": outcome.get("status"),
            "targets_total": outcome.get("targets_total"),
            "targets_succeeded": outcome.get("targets_succeeded"),
            "targets_pending": outcome.get("targets_pending"),
            "targets_failed": outcome.get("targets_failed"),
            "targets_expired": outcome.get("targets_expired"),
            "amount_recovered": recovered,
            "amount_targeted": targeted,
            "conversion_rate": (
                f"{float(rate) * 100:.1f}%" if rate is not None else None
            ),
        }
        if out["conversion_rate"]:
            key_figures["conversion_rate"] = out["conversion_rate"]
        return out


__all__ = ["ConsultationContextBuilder"]
