"""Deterministic case-summary assembler.

Builds the ``FinancialCaseSummary`` contract that the future UI will
render. Always derived from structured records; never from an LLM.
"""

from __future__ import annotations

from typing import Any

from backend.app.schemas.outcome.metrics import (
    CaseSummaryEntry,
    FinancialCaseSummary,
)
from backend.app.services.outcome.outcome_evaluator import OutcomeEvaluator
from backend.app.services.outcome.outcome_store import OutcomeStore


class CaseSummaryService:
    """Deterministic assembler for ``FinancialCaseSummary``.

    Inputs are *references* to upstream objects — the executor / router /
    investigation stores are looked up via injection. Stage 5 does not
    own those stores; callers compose this service with whatever stores
    are in play (default in-memory dicts from the routers).
    """

    def __init__(
        self,
        outcome_store: OutcomeStore,
        evaluator: OutcomeEvaluator,
        *,
        action_resolver: Any | None = None,
        investigation_resolver: Any | None = None,
        diagnosis_resolver: Any | None = None,
        policy_resolver: Any | None = None,
        approval_resolver: Any | None = None,
        execution_resolver: Any | None = None,
        incident_resolver: Any | None = None,
    ) -> None:
        self._outcomes = outcome_store
        self._evaluator = evaluator
        self._actions = action_resolver
        self._investigations = investigation_resolver
        self._diagnoses = diagnosis_resolver
        self._policies = policy_resolver
        self._approvals = approval_resolver
        self._executions = execution_resolver
        self._incidents = incident_resolver

    def build_for_outcome(self, outcome_id: str) -> FinancialCaseSummary:
        outcome = self._outcomes.get_outcome(outcome_id)
        if outcome is None:
            raise KeyError(f"Outcome {outcome_id} not found")
        return self._build(
            action_id=outcome.action_id,
            investigation_id=outcome.investigation_id,
            diagnosis_id=outcome.diagnosis_id,
            approval_id=outcome.approval_id,
            execution_id=outcome.execution_id,
            outcome_id=outcome.outcome_id,
        )

    def build_for_action(self, action_id: str) -> FinancialCaseSummary:
        outcome = self._outcomes.get_outcome_by_action(action_id)
        if outcome is None:
            # Action hasn't been executed yet — allow caller to build a
            # partial case summary from upstream records alone.
            action = self._resolve(self._actions, action_id)
            return self._build(
                action_id=action_id,
                investigation_id=getattr(action, "investigation_id", None),
                diagnosis_id=getattr(action, "diagnosis_id", None),
                approval_id=None,
                execution_id=None,
                outcome_id=None,
            )
        return self.build_for_outcome(outcome.outcome_id)

    # ---- Internals ----

    def _build(
        self,
        *,
        action_id: str | None,
        investigation_id: str | None,
        diagnosis_id: str | None,
        approval_id: str | None,
        execution_id: str | None,
        outcome_id: str | None,
    ) -> FinancialCaseSummary:
        action = self._resolve(self._actions, action_id) if action_id else None
        investigation = (
            self._resolve(self._investigations, investigation_id)
            if investigation_id
            else None
        )
        diagnosis = (
            self._resolve(self._diagnoses, diagnosis_id) if diagnosis_id else None
        )
        approval = (
            self._resolve(self._approvals, approval_id) if approval_id else None
        )
        execution = (
            self._resolve(self._executions, execution_id) if execution_id else None
        )
        incident = (
            self._resolve(self._incidents, getattr(investigation, "incident_id", None))
            if investigation is not None and getattr(investigation, "incident_id", None)
            else None
        )
        outcome = self._outcomes.get_outcome(outcome_id) if outcome_id else None

        symptom = None
        if incident is not None:
            symptom = getattr(incident, "summary", None) or getattr(
                incident, "incident_type", None
            )
        elif investigation is not None:
            symptom = getattr(investigation, "incident_type", None)
        if symptom is None and investigation is not None:
            symptom = getattr(investigation, "incident_type", None)

        diagnosis_text = (
            getattr(diagnosis, "leading_hypothesis", None) if diagnosis else None
        )
        prescription = getattr(action, "rationale", None) if action else None

        approval_status = (
            getattr(getattr(approval, "status", None), "value", None)
            if approval
            else None
        )
        treatment_status = (
            getattr(getattr(execution, "status", None), "value", None)
            if execution
            else None
        )
        outcome_status = (
            getattr(getattr(outcome, "status", None), "value", None)
            if outcome
            else None
        )

        lineage: list[CaseSummaryEntry] = []
        if investigation is not None:
            lineage.append(
                CaseSummaryEntry(
                    stage="investigation",
                    reference_id=investigation.investigation_id,
                    status=getattr(getattr(investigation, "state", None), "value", None),
                    timestamp=getattr(investigation, "created_at", None),
                    notes=symptom,
                )
            )
        if diagnosis is not None:
            lineage.append(
                CaseSummaryEntry(
                    stage="diagnosis",
                    reference_id=diagnosis.diagnosis_id,
                    notes=diagnosis_text,
                )
            )
        if action is not None:
            lineage.append(
                CaseSummaryEntry(
                    stage="action",
                    reference_id=action.action_id,
                    status=getattr(getattr(action, "status", None), "value", None),
                    notes=prescription,
                )
            )
        if approval is not None:
            lineage.append(
                CaseSummaryEntry(
                    stage="approval",
                    reference_id=approval.approval_id,
                    status=approval_status,
                    timestamp=getattr(approval, "requested_at", None),
                )
            )
        if execution is not None:
            lineage.append(
                CaseSummaryEntry(
                    stage="execution",
                    reference_id=execution.execution_id,
                    status=treatment_status,
                    timestamp=getattr(execution, "started_at", None),
                    metadata={
                        "provider_reference": getattr(execution, "provider_reference", None)
                    },
                )
            )
        if outcome is not None:
            lineage.append(
                CaseSummaryEntry(
                    stage="outcome",
                    reference_id=outcome.outcome_id,
                    status=outcome_status,
                    timestamp=getattr(outcome, "created_at", None),
                    metadata={
                        "targets_total": outcome.targets_total,
                        "targets_recovered": outcome.targets_succeeded,
                        "amount_recovered_minor": outcome.amount_recovered_minor,
                    },
                )
            )

        effectiveness = None
        if outcome is not None:
            effectiveness = self._evaluator.compute_effectiveness(outcome.outcome_id)

        return FinancialCaseSummary(
            incident_type=getattr(investigation, "incident_type", None),
            investigation_id=investigation_id,
            diagnosis_id=diagnosis_id,
            action_id=action_id,
            approval_id=approval_id,
            execution_id=execution_id,
            outcome_id=outcome_id,
            symptom=symptom,
            diagnosis=diagnosis_text,
            prescription=prescription,
            approval_status=approval_status,
            treatment_status=treatment_status,
            outcome_status=outcome_status,
            lineage=lineage,
            treatment_effectiveness=effectiveness,
        )

    @staticmethod
    def _resolve(resolver: Any, key: str | None) -> Any | None:
        if resolver is None or key is None:
            return None
        if callable(resolver):
            return resolver(key)
        if hasattr(resolver, "get"):
            return resolver.get(key)
        return None


__all__ = ["CaseSummaryService"]