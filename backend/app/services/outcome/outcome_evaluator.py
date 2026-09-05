"""Deterministic outcome evaluator.

The Financial Doctor declares success — or failure — based on the
patient's outcome, not the prescription. ``OutcomeEvaluator`` is the
deterministic aggregation and transition logic that drives that
declaration. No LLM code lives here; amounts are integer minor units;
status transitions are validated against
:data:`backend.app.schemas.outcome.enums.OUTCOME_TRANSITIONS`.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from backend.app.schemas.outcome.audit import AuditEvent
from backend.app.schemas.outcome.enums import (
    AuditActor,
    AuditEventType,
    OutcomeStatus,
    TargetOutcomeStatus,
)
from backend.app.schemas.outcome.intervention_outcome import InterventionOutcome
from backend.app.schemas.outcome.metrics import TreatmentEffectiveness
from backend.app.schemas.outcome.target_outcome import RecoveryTargetOutcome
from backend.app.services.outcome.outcome_store import AuditStore, OutcomeStore


class OutcomeEvaluator:
    """Deterministic outcome evaluation.

    Responsibilities:
      1. load target outcomes
      2. aggregate target counts
      3. calculate recovered amount
      4. calculate remaining amount
      5. calculate conversion rate
      6. determine aggregate status
      7. update the intervention outcome
      8. record audit events
    """

    def __init__(
        self,
        outcome_store: OutcomeStore,
        audit_store: AuditStore,
        observation_window_seconds: int = 7 * 24 * 3600,
    ) -> None:
        self._outcomes = outcome_store
        self._audit = audit_store
        # After this many seconds past creation, pending targets are
        # eligible for deterministic expiry finalization. Defaults to
        # one week. Tests override.
        self._observation_window_seconds = observation_window_seconds

    # ---- Public API ----

    def recalculate(self, outcome_id: str) -> InterventionOutcome:
        """Re-aggregate outcome state from current targets.

        Idempotent — calling twice with the same target state yields
        the same aggregate status (modulo timestamps).
        """
        outcome = self._require_outcome(outcome_id)
        targets = self._outcomes.list_targets_for_outcome(outcome_id)
        previous_status = outcome.status
        previous_amount = outcome.amount_recovered_minor

        self._apply_aggregation(outcome, targets)

        # If the aggregate hasn't changed but we recalculated, log a
        # recalc event so observability traces are complete.
        self._audit.record(
            AuditEvent(
                event_type=AuditEventType.OUTCOME_RECALCULATED,
                actor=AuditActor.SYSTEM,
                entity_type="outcome",
                entity_id=outcome.outcome_id,
                previous_state=previous_status.value,
                new_state=outcome.status.value,
                reason=f"recalculated from {len(targets)} targets",
                reference_id=None,
                metadata={
                    "amount_recovered_minor": outcome.amount_recovered_minor,
                    "amount_targeted_minor": outcome.amount_targeted_minor,
                    "delta_recovered_minor": outcome.amount_recovered_minor - previous_amount,
                    "targets_total": outcome.targets_total,
                    "targets_succeeded": outcome.targets_succeeded,
                    "targets_pending": outcome.targets_pending,
                    "targets_failed": outcome.targets_failed,
                    "targets_expired": outcome.targets_expired,
                },
            )
        )
        self._outcomes.save_outcome(outcome)
        return outcome

    def compute_effectiveness(self, outcome_id: str) -> TreatmentEffectiveness:
        """Build a TreatmentEffectiveness view of the outcome."""
        outcome = self._require_outcome(outcome_id)
        targets = self._outcomes.list_targets_for_outcome(outcome_id)
        return self._build_effectiveness(outcome, targets)

    def finalize_expired(self, outcome_id: str) -> InterventionOutcome | None:
        """Finalize pending targets whose observation window has elapsed.

        Returns the outcome if it transitioned to a terminal state,
        else ``None``. Used both by the per-evaluation logic and the
        explicit ``POST /outcomes/{id}/evaluate`` endpoint.
        """
        outcome = self._require_outcome(outcome_id)
        if outcome.is_terminal():
            return None

        targets = self._outcomes.list_targets_for_outcome(outcome_id)
        now = dt.datetime.utcnow()
        changed = False
        for target in targets:
            if target.is_terminal():
                continue
            age = (now - target.created_at).total_seconds()
            if age >= self._observation_window_seconds:
                previous = target.status
                target.transition(
                    TargetOutcomeStatus.EXPIRED,
                    event_at=now,
                    event_id=f"observation_window:{target.target_outcome_id}",
                )
                self._outcomes.save_target(target)
                self._audit.record(
                    AuditEvent(
                        event_type=AuditEventType.TARGET_EXPIRED,
                        actor=AuditActor.SYSTEM,
                        entity_type="target_outcome",
                        entity_id=target.target_outcome_id,
                        previous_state=previous.value,
                        new_state=target.status.value,
                        reason="observation_window_elapsed",
                        reference_id=outcome.outcome_id,
                    )
                )
                changed = True

        if changed:
            self.recalculate(outcome_id)
            outcome = self._require_outcome(outcome_id)  # refresh
        return outcome if outcome.is_terminal() else None

    # ---- Construction helpers ----

    def initialize_targets(
        self,
        outcome_id: str,
        *,
        targets: list[dict[str, Any]],
        audit_actor: AuditActor = AuditActor.SYSTEM,
        audit_reason: str = "execution_succeeded",
        execution_id: str | None = None,
    ) -> list[RecoveryTargetOutcome]:
        """Create ``RecoveryTargetOutcome`` records for each execution target.

        ``targets`` is a list of dicts containing at minimum ``payment_id``
        and ``amount_minor``. Optional fields:
          - order_id, customer_id, payment_method, failure_reason
          - payment_link_id, provider_reference
          - currency (defaults to outcome currency)
        """
        outcome = self._require_outcome(outcome_id)
        saved: list[RecoveryTargetOutcome] = []
        for entry in targets:
            payment_id = entry["payment_id"]
            amount_minor = int(entry["amount_minor"])
            currency = entry.get("currency", outcome.currency)
            target_id = entry.get("target_id") or self._compute_target_id(
                outcome.action_id, payment_id
            )
            payment_link_id = entry.get("payment_link_id")
            provider_reference = entry.get("provider_reference") or (
                f"{outcome.action_id}:{payment_id}"
            )
            target = RecoveryTargetOutcome(
                outcome_id=outcome.outcome_id,
                target_id=target_id,
                payment_id=payment_id,
                order_id=entry.get("order_id"),
                customer_id=entry.get("customer_id"),
                payment_method=entry.get("payment_method"),
                failure_reason=entry.get("failure_reason"),
                payment_link_id=payment_link_id,
                provider_reference=provider_reference,
                currency=currency,
                expected_amount_minor=amount_minor,
            )
            saved.append(self._outcomes.save_target(target))
            self._audit.record(
                AuditEvent(
                    event_type=AuditEventType.TARGET_REGISTERED,
                    actor=audit_actor,
                    entity_type="target_outcome",
                    entity_id=target.target_outcome_id,
                    previous_state=None,
                    new_state=target.status.value,
                    reason=audit_reason,
                    reference_id=execution_id or outcome.action_id,
                    metadata={
                        "payment_link_id": payment_link_id,
                        "payment_id": payment_id,
                        "expected_amount_minor": amount_minor,
                    },
                )
            )
        # Aggregate once at initialization so the outcome reflects the
        # full target set (targets_total/pending/targeted amount).
        self.recalculate(outcome.outcome_id)
        return saved

    # ---- Internals ----

    def _require_outcome(self, outcome_id: str) -> InterventionOutcome:
        outcome = self._outcomes.get_outcome(outcome_id)
        if outcome is None:
            raise KeyError(f"Outcome {outcome_id} not found")
        return outcome

    @staticmethod
    def _compute_target_id(action_id: str, payment_id: str) -> str:
        return f"{action_id}:{payment_id}"

    def _apply_aggregation(
        self, outcome: InterventionOutcome, targets: list[RecoveryTargetOutcome]
    ) -> None:
        """Recompute counters and apply the deterministic status rule."""
        total = len(targets)
        succeeded = sum(1 for t in targets if t.status == TargetOutcomeStatus.PAID)
        failed = sum(1 for t in targets if t.status == TargetOutcomeStatus.FAILED)
        expired = sum(1 for t in targets if t.status == TargetOutcomeStatus.EXPIRED)
        pending = sum(1 for t in targets if t.status == TargetOutcomeStatus.PENDING)
        # Defensive invariant — surface bad data loudly instead of silently.
        if succeeded + failed + expired + pending != total:
            raise ValueError(
                f"Target counts do not sum to total ({total}): "
                f"succeeded={succeeded} failed={failed} expired={expired} pending={pending}"
            )

        amount_targeted = sum(t.expected_amount_minor for t in targets)
        amount_recovered = sum(t.recovered_amount_minor for t in targets)
        if amount_recovered > amount_targeted:
            raise ValueError(
                f"Recovered amount {amount_recovered} exceeds targeted {amount_targeted}"
            )

        conversion_rate = (succeeded / total) if total else None

        outcome.targets_total = total
        outcome.targets_succeeded = succeeded
        outcome.targets_failed = failed
        outcome.targets_expired = expired
        outcome.targets_pending = pending
        outcome.amount_targeted_minor = amount_targeted
        outcome.amount_recovered_minor = amount_recovered
        outcome.conversion_rate = conversion_rate

        # First observation timestamp — derived from earliest paid target.
        paid_targets = [t for t in targets if t.status == TargetOutcomeStatus.PAID]
        if paid_targets:
            first_paid = min(t.paid_at for t in paid_targets if t.paid_at)
            if outcome.first_observed_at is None or first_paid < outcome.first_observed_at:
                outcome.first_observed_at = first_paid

        new_status = self._derive_status(total, succeeded, failed, expired, pending)
        # Aggregate status can only move forward; an already-terminal
        # outcome is never reopened by re-aggregation. The recalculate
        # call records the audit even when no transition occurs.
        if outcome.status != new_status and not outcome.is_terminal():
            try:
                outcome.transition(new_status)
            except ValueError:
                # The transition table rejected the move — keep current.
                pass

    @staticmethod
    def _derive_status(
        total: int,
        succeeded: int,
        failed: int,
        expired: int,
        pending: int,
    ) -> OutcomeStatus:
        if total == 0:
            return OutcomeStatus.FAILED
        if succeeded == total:
            return OutcomeStatus.RECOVERED
        if succeeded > 0:
            # Some recovery observed, but not all targets recovered yet.
            return OutcomeStatus.PARTIALLY_RECOVERED
        if pending > 0:
            # No recovery yet; observation continues.
            return OutcomeStatus.PENDING
        # No recovery and nothing pending: every target resolved
        # unsuccessfully (failed and/or expired). Provider expiry and
        # observation-window expiry both collapse to NO_RECOVERY for
        # the aggregate in the MVP, matching the Stage 5 test contract.
        return OutcomeStatus.NO_RECOVERY

    def _build_effectiveness(
        self,
        outcome: InterventionOutcome,
        targets: list[RecoveryTargetOutcome],
    ) -> TreatmentEffectiveness:
        total = outcome.targets_total
        succeeded = outcome.targets_succeeded
        pending = outcome.targets_pending
        unrecovered = outcome.targets_failed + outcome.targets_expired

        amount_remaining = outcome.amount_targeted_minor - outcome.amount_recovered_minor
        # Defence in depth — keep arithmetic in integer space.
        if amount_remaining < 0:
            amount_remaining = 0

        recovery_rate = (succeeded / total) if total else None
        revenue_recovery_rate = (
            outcome.amount_recovered_minor / outcome.amount_targeted_minor
            if outcome.amount_targeted_minor
            else None
        )

        time_to_first = None
        time_to_last = None
        paid_targets = [t for t in targets if t.status == TargetOutcomeStatus.PAID and t.paid_at]
        if paid_targets:
            paid_times = sorted(t.paid_at for t in paid_targets if t.paid_at is not None)
            earliest = paid_times[0]
            latest = paid_times[-1]
            time_to_first = (earliest - outcome.created_at).total_seconds()
            if len(paid_times) > 1:
                time_to_last = (latest - outcome.created_at).total_seconds()
            else:
                time_to_last = time_to_first

        return TreatmentEffectiveness(
            intervention_outcome_id=outcome.outcome_id,
            targets_total=total,
            targets_recovered=succeeded,
            targets_pending=pending,
            targets_unrecovered=unrecovered,
            currency=outcome.currency,
            amount_targeted_minor=outcome.amount_targeted_minor,
            amount_recovered_minor=outcome.amount_recovered_minor,
            amount_remaining_minor=amount_remaining,
            recovery_rate=recovery_rate,
            revenue_recovery_rate=revenue_recovery_rate,
            time_to_first_recovery_seconds=time_to_first,
            time_to_last_recovery_seconds=time_to_last,
        )


__all__ = ["OutcomeEvaluator"]