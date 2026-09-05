"""Execution-to-outcome boundary.

When Stage 4 successfully executes ``CREATE_PAYMENT_LINK``, Stage 5
initializes the corresponding outcome + target records. This module is
the deterministic bridge — no LLM call. The executor invokes
``initialize_outcome_for_execution`` after a successful execution and
the outcome layer is left in the ``PENDING`` state waiting on
provider webhooks.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from backend.app.schemas.action.approval import ApprovalRequest
from backend.app.schemas.action.execution import ActionExecution, ExecutionStatus
from backend.app.schemas.outcome.audit import AuditEvent
from backend.app.schemas.outcome.enums import AuditActor, AuditEventType
from backend.app.schemas.outcome.intervention_outcome import InterventionOutcome
from backend.app.services.outcome.outcome_evaluator import OutcomeEvaluator
from backend.app.services.outcome.outcome_store import AuditStore, OutcomeStore


class OutcomeInitError(Exception):
    pass


class OutcomeInitializer:
    """Deterministic execution -> outcome boundary."""

    def __init__(
        self,
        outcome_store: OutcomeStore,
        audit_store: AuditStore,
        evaluator: OutcomeEvaluator,
    ) -> None:
        self._outcomes = outcome_store
        self._audit = audit_store
        self._evaluator = evaluator

    def initialize_outcome_for_execution(
        self,
        *,
        action: Any,
        approval: ApprovalRequest | None,
        execution: ActionExecution,
        targets_with_links: list[dict[str, Any]],
    ) -> InterventionOutcome:
        """Build + persist an outcome from a successful execution.

        ``targets_with_links`` is the executor's per-target manifest.
        Each entry must contain ``payment_id`` and ``amount_minor``;
        ``payment_link_id`` / ``provider_reference`` are filled in from
        the executor's adapter responses.
        """
        if execution.status != ExecutionStatus.SUCCEEDED:
            raise OutcomeInitError(
                f"Cannot initialize outcome from execution in status {execution.status.value}"
            )
        if not targets_with_links:
            raise OutcomeInitError("targets_with_links is empty")

        existing = self._outcomes.get_outcome_by_action(action.action_id)
        if existing is not None:
            # Idempotency: a previous initialization for the same action
            # already produced an outcome. Re-aggregate but do not create
            # duplicate audit events for initialization.
            self._evaluator.recalculate(existing.outcome_id)
            return existing

        outcome = InterventionOutcome(
            action_id=action.action_id,
            execution_id=execution.execution_id,
            investigation_id=action.investigation_id,
            diagnosis_id=action.diagnosis_id,
            approval_id=approval.approval_id if approval else None,
            currency=action.currency,
            created_at=dt.datetime.utcnow(),
        )
        self._outcomes.save_outcome(outcome)

        self._audit.record(
            AuditEvent(
                event_type=AuditEventType.OUTCOME_INITIALIZED,
                actor=AuditActor.SYSTEM,
                entity_type="outcome",
                entity_id=outcome.outcome_id,
                previous_state=None,
                new_state=outcome.status.value,
                reason="execution_succeeded",
                reference_id=execution.execution_id,
                metadata={
                    "action_id": action.action_id,
                    "targets_count": len(targets_with_links),
                    "amount_targeted_minor": sum(
                        int(t["amount_minor"]) for t in targets_with_links
                    ),
                    "currency": action.currency,
                },
            )
        )

        # Construct target outcomes + register them. The evaluator
        # recalculates inside ``initialize_targets`` so the outcome
        # reflects the full target set immediately.
        self._evaluator.initialize_targets(
            outcome.outcome_id,
            targets=targets_with_links,
            audit_actor=AuditActor.SYSTEM,
            audit_reason="execution_succeeded",
            execution_id=execution.execution_id,
        )
        refreshed = self._outcomes.get_outcome(outcome.outcome_id)
        assert refreshed is not None
        return refreshed


__all__ = ["OutcomeInitError", "OutcomeInitializer"]