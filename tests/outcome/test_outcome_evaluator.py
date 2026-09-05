"""Stage 5 — OutcomeEvaluator unit tests.

Deterministic aggregation, status derivation, recalculation idempotency,
finalization rules. No webhooks, no LLM, no provider calls.
"""

from __future__ import annotations

import datetime as dt

import pytest
from backend.app.schemas.outcome.enums import OutcomeStatus, TargetOutcomeStatus
from backend.app.schemas.outcome.intervention_outcome import InterventionOutcome
from backend.app.schemas.outcome.target_outcome import RecoveryTargetOutcome
from backend.app.services.outcome.outcome_evaluator import OutcomeEvaluator
from backend.app.services.outcome.outcome_store import AuditStore, OutcomeStore


def _new_outcome() -> InterventionOutcome:
    return InterventionOutcome(
        action_id="act_test",
        investigation_id="inv_test",
        diagnosis_id="diag_test",
    )


def _new_target(
    outcome_id: str, payment_id: str, amount_minor: int
) -> RecoveryTargetOutcome:
    return RecoveryTargetOutcome(
        outcome_id=outcome_id,
        target_id=f"tgt_{payment_id}",
        payment_id=payment_id,
        expected_amount_minor=amount_minor,
    )


@pytest.fixture
def stack():
    outcomes_store = OutcomeStore()
    audit_store = AuditStore()
    evaluator = OutcomeEvaluator(outcomes_store, audit_store)
    outcome = _new_outcome()
    outcomes_store.save_outcome(outcome)
    return outcomes_store, audit_store, evaluator, outcome


class TestEvaluatorAggregation:
    def test_initial_state_after_initialization(self, stack):
        outcomes_store, audit_store, evaluator, outcome = stack
        targets = [
            {
                "payment_id": f"pay_{i}",
                "amount_minor": 1000,
                "currency": "INR",
            }
            for i in range(3)
        ]
        evaluator.initialize_targets(
            outcome.outcome_id,
            targets=targets,
        )
        refreshed = outcomes_store.get_outcome(outcome.outcome_id)
        assert refreshed is not None
        assert refreshed.targets_total == 3
        assert refreshed.targets_pending == 3
        assert refreshed.amount_targeted_minor == 3000
        assert refreshed.amount_recovered_minor == 0
        assert refreshed.status == OutcomeStatus.PENDING

    def test_recalculate_aggregates_target_state(self, stack):
        outcomes_store, audit_store, evaluator, outcome = stack
        targets = [
            _new_target(outcome.outcome_id, f"pay_{i}", 1000) for i in range(3)
        ]
        for t in targets:
            outcomes_store.save_target(t)
        targets[0].transition(TargetOutcomeStatus.PAID, event_id="e1")
        targets[1].transition(TargetOutcomeStatus.PAID, event_id="e2")
        for t in targets:
            outcomes_store.save_target(t)
        evaluator.recalculate(outcome.outcome_id)
        refreshed = outcomes_store.get_outcome(outcome.outcome_id)
        assert refreshed.targets_succeeded == 2
        assert refreshed.targets_pending == 1
        assert refreshed.amount_recovered_minor == 2000
        assert refreshed.conversion_rate == pytest.approx(2 / 3)

    def test_aggregate_status_partially_recovered(self, stack):
        outcomes_store, audit_store, evaluator, outcome = stack
        targets = [
            _new_target(outcome.outcome_id, f"pay_{i}", 1000) for i in range(3)
        ]
        targets[0].transition(TargetOutcomeStatus.PAID, event_id="e1")
        targets[1].transition(TargetOutcomeStatus.FAILED, event_id="e2")
        targets[2].transition(TargetOutcomeStatus.EXPIRED, event_id="e3")
        for t in targets:
            outcomes_store.save_target(t)
        evaluator.recalculate(outcome.outcome_id)
        refreshed = outcomes_store.get_outcome(outcome.outcome_id)
        assert refreshed.status == OutcomeStatus.PARTIALLY_RECOVERED

    def test_aggregate_status_fully_recovered(self, stack):
        outcomes_store, audit_store, evaluator, outcome = stack
        targets = [
            _new_target(outcome.outcome_id, f"pay_{i}", 1000) for i in range(3)
        ]
        for i, t in enumerate(targets):
            t.transition(TargetOutcomeStatus.PAID, event_id=f"e{i}")
            outcomes_store.save_target(t)
        evaluator.recalculate(outcome.outcome_id)
        refreshed = outcomes_store.get_outcome(outcome.outcome_id)
        assert refreshed.status == OutcomeStatus.RECOVERED

    def test_aggregate_status_no_recovery(self, stack):
        outcomes_store, audit_store, evaluator, outcome = stack
        targets = [
            _new_target(outcome.outcome_id, f"pay_{i}", 1000) for i in range(3)
        ]
        targets[0].transition(TargetOutcomeStatus.FAILED, event_id="e1")
        targets[1].transition(TargetOutcomeStatus.EXPIRED, event_id="e2")
        # targets[2] stays PENDING -> outcome still PENDING
        for t in targets:
            outcomes_store.save_target(t)
        evaluator.recalculate(outcome.outcome_id)
        refreshed = outcomes_store.get_outcome(outcome.outcome_id)
        assert refreshed.status == OutcomeStatus.PENDING

        # Finalize the last pending by marking expired
        targets[2].transition(TargetOutcomeStatus.EXPIRED, event_id="e3")
        outcomes_store.save_target(targets[2])
        evaluator.recalculate(outcome.outcome_id)
        refreshed = outcomes_store.get_outcome(outcome.outcome_id)
        assert refreshed.status == OutcomeStatus.NO_RECOVERY

    def test_recalculate_is_idempotent(self, stack):
        outcomes_store, audit_store, evaluator, outcome = stack
        targets = [
            _new_target(outcome.outcome_id, f"pay_{i}", 1000) for i in range(2)
        ]
        for t in targets:
            t.transition(TargetOutcomeStatus.PAID, event_id=f"e{t.payment_id}")
            outcomes_store.save_target(t)
        evaluator.recalculate(outcome.outcome_id)
        snapshot_a = outcomes_store.get_outcome(outcome.outcome_id).to_summary()
        evaluator.recalculate(outcome.outcome_id)
        snapshot_b = outcomes_store.get_outcome(outcome.outcome_id).to_summary()
        assert snapshot_a["status"] == snapshot_b["status"]
        assert snapshot_a["targets_total"] == snapshot_b["targets_total"]
        assert snapshot_a["amount_recovered_minor"] == snapshot_b["amount_recovered_minor"]


class TestEvaluatorFinalization:
    def test_finalize_expired_marks_pending_targets(self, stack):
        outcomes_store, audit_store, evaluator, outcome = stack
        evaluator._observation_window_seconds = 0
        t1 = _new_target(outcome.outcome_id, "pay_1", 1000)
        t2 = _new_target(outcome.outcome_id, "pay_2", 1000)
        t1.created_at = dt.datetime.utcnow() - dt.timedelta(hours=1)
        t2.created_at = dt.datetime.utcnow() - dt.timedelta(hours=1)
        outcomes_store.save_target(t1)
        outcomes_store.save_target(t2)
        evaluator.finalize_expired(outcome.outcome_id)
        refreshed = outcomes_store.get_outcome(outcome.outcome_id)
        assert refreshed.status == OutcomeStatus.NO_RECOVERY
        assert refreshed.targets_expired == 2
        assert refreshed.targets_pending == 0

    def test_finalize_expired_returns_none_for_active_outcome(self, stack):
        outcomes_store, audit_store, evaluator, outcome = stack
        t1 = _new_target(outcome.outcome_id, "pay_1", 1000)
        outcomes_store.save_target(t1)
        result = evaluator.finalize_expired(outcome.outcome_id)
        assert result is None  # still PENDING

    def test_terminal_outcome_not_reopened_by_recalc(self, stack):
        outcomes_store, audit_store, evaluator, outcome = stack
        targets = [
            _new_target(outcome.outcome_id, f"pay_{i}", 1000) for i in range(2)
        ]
        for t in targets:
            t.transition(TargetOutcomeStatus.PAID, event_id=f"e{t.payment_id}")
            outcomes_store.save_target(t)
        evaluator.recalculate(outcome.outcome_id)
        refreshed = outcomes_store.get_outcome(outcome.outcome_id)
        assert refreshed.status == OutcomeStatus.RECOVERED
        refreshed.targets_succeeded = 0
        refreshed.targets_failed = 2
        evaluator.recalculate(outcome.outcome_id)
        refreshed = outcomes_store.get_outcome(outcome.outcome_id)
        assert refreshed.status == OutcomeStatus.RECOVERED


class TestEffectivenessMetrics:
    def test_recovery_rate_when_some_recovered(self, stack):
        outcomes_store, audit_store, evaluator, outcome = stack
        targets = [
            _new_target(outcome.outcome_id, f"pay_{i}", 1000) for i in range(4)
        ]
        for t in targets[:3]:
            t.transition(TargetOutcomeStatus.PAID, event_id=f"e{t.payment_id}")
            outcomes_store.save_target(t)
        outcomes_store.save_target(targets[3])
        evaluator.recalculate(outcome.outcome_id)
        eff = evaluator.compute_effectiveness(outcome.outcome_id)
        assert eff.recovery_rate == pytest.approx(0.75)
        assert eff.revenue_recovery_rate == pytest.approx(0.75)
        assert eff.targets_recovered == 3
        assert eff.targets_unrecovered == 0
        assert eff.targets_pending == 1
        assert eff.amount_remaining_minor == 1000

    def test_metrics_are_none_when_total_is_zero(self, stack):
        outcomes_store, audit_store, evaluator, outcome = stack
        eff = evaluator.compute_effectiveness(outcome.outcome_id)
        assert eff.recovery_rate is None
        assert eff.revenue_recovery_rate is None
        assert eff.time_to_first_recovery_seconds is None
        assert eff.time_to_last_recovery_seconds is None

    def test_time_to_first_recovery(self, stack):
        outcomes_store, audit_store, evaluator, outcome = stack
        t = _new_target(outcome.outcome_id, "pay_1", 1000)
        outcomes_store.save_target(t)
        t.transition(TargetOutcomeStatus.PAID, event_id="e1")
        outcomes_store.save_target(t)
        evaluator.recalculate(outcome.outcome_id)
        eff = evaluator.compute_effectiveness(outcome.outcome_id)
        assert eff.time_to_first_recovery_seconds is not None
        assert eff.time_to_first_recovery_seconds >= 0


class TestAuditTrail:
    def test_recalculate_records_recalc_event(self, stack):
        outcomes_store, audit_store, evaluator, outcome = stack
        t = _new_target(outcome.outcome_id, "pay_1", 1000)
        outcomes_store.save_target(t)
        evaluator.recalculate(outcome.outcome_id)
        events = audit_store.list_for_entity("outcome", outcome.outcome_id)
        recalc_events = [
            e for e in events if e.event_type.value == "OUTCOME_RECALCULATED"
        ]
        assert len(recalc_events) == 1

    def test_audit_carries_actor_and_reference(self, stack):
        outcomes_store, audit_store, evaluator, outcome = stack
        t = _new_target(outcome.outcome_id, "pay_1", 1000)
        outcomes_store.save_target(t)
        evaluator.recalculate(outcome.outcome_id)
        events = audit_store.list_for_entity("outcome", outcome.outcome_id)
        assert all(e.actor.value == "SYSTEM" for e in events)
        assert all(e.reference_id is None or isinstance(e.reference_id, str) for e in events)