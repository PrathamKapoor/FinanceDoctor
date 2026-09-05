"""Stage 5 — Outcome domain model tests.

Covers schema invariants, status enums, allowed transition tables, and
metric scaffolding. No LLM or provider involvement.
"""

from __future__ import annotations

import datetime as dt

import pytest
from backend.app.schemas.outcome.audit import AuditEvent
from backend.app.schemas.outcome.enums import (
    OUTCOME_TRANSITIONS,
    TARGET_TRANSITIONS,
    AuditActor,
    AuditEventType,
    OutcomeStatus,
    TargetOutcomeStatus,
    assert_outcome_transition,
    assert_target_transition,
)
from backend.app.schemas.outcome.intervention_outcome import InterventionOutcome
from backend.app.schemas.outcome.metrics import (
    CaseSummaryEntry,
    FinancialCaseSummary,
    TreatmentEffectiveness,
)
from backend.app.schemas.outcome.target_outcome import RecoveryTargetOutcome
from pydantic import ValidationError


class TestEnums:
    def test_target_status_values(self):
        assert TargetOutcomeStatus.PENDING.value == "PENDING"
        assert TargetOutcomeStatus.PAID.value == "PAID"
        assert TargetOutcomeStatus.FAILED.value == "FAILED"
        assert TargetOutcomeStatus.EXPIRED.value == "EXPIRED"

    def test_outcome_status_values(self):
        assert OutcomeStatus.PENDING.value == "PENDING"
        assert OutcomeStatus.PARTIALLY_RECOVERED.value == "PARTIALLY_RECOVERED"
        assert OutcomeStatus.RECOVERED.value == "RECOVERED"
        assert OutcomeStatus.NO_RECOVERY.value == "NO_RECOVERY"
        assert OutcomeStatus.EXPIRED.value == "EXPIRED"
        assert OutcomeStatus.FAILED.value == "FAILED"

    def test_target_terminal_statuses_have_no_exits(self):
        for terminal in (
            TargetOutcomeStatus.PAID,
            TargetOutcomeStatus.FAILED,
            TargetOutcomeStatus.EXPIRED,
        ):
            assert TARGET_TRANSITIONS[terminal] == frozenset()

    def test_outcome_terminal_statuses_have_no_exits(self):
        for terminal in (
            OutcomeStatus.RECOVERED,
            OutcomeStatus.NO_RECOVERY,
            OutcomeStatus.EXPIRED,
            OutcomeStatus.FAILED,
        ):
            assert OUTCOME_TRANSITIONS[terminal] == frozenset()


class TestTransitionGuards:
    def test_assert_target_transition_accepts_valid(self):
        assert_target_transition(TargetOutcomeStatus.PENDING, TargetOutcomeStatus.PAID)

    def test_assert_target_transition_rejects_invalid(self):
        with pytest.raises(ValueError, match="Illegal target outcome transition"):
            assert_target_transition(TargetOutcomeStatus.PAID, TargetOutcomeStatus.PENDING)

    def test_assert_outcome_transition_rejects_invalid(self):
        with pytest.raises(ValueError, match="Illegal outcome transition"):
            assert_outcome_transition(OutcomeStatus.RECOVERED, OutcomeStatus.PENDING)


class TestInterventionOutcome:
    def _build(self, **overrides) -> InterventionOutcome:
        defaults = dict(
            action_id="act_001",
            investigation_id="inv_001",
            diagnosis_id="diag_001",
            approval_id="apr_001",
        )
        defaults.update(overrides)
        return InterventionOutcome(**defaults)

    def test_initial_status_is_pending(self):
        outcome = self._build()
        assert outcome.status == OutcomeStatus.PENDING
        assert outcome.is_terminal() is False

    def test_transition_advances_status(self):
        outcome = self._build()
        outcome.transition(OutcomeStatus.RECOVERED)
        assert outcome.status == OutcomeStatus.RECOVERED
        assert outcome.is_terminal() is True
        assert outcome.finalized_at is not None

    def test_terminal_outcome_cannot_reopen(self):
        outcome = self._build()
        outcome.transition(OutcomeStatus.RECOVERED)
        with pytest.raises(ValueError):
            outcome.transition(OutcomeStatus.PARTIALLY_RECOVERED)

    def test_target_count_validator_enforces_invariant(self):
        with pytest.raises(ValidationError):
            InterventionOutcome(
                action_id="act_x",
                investigation_id="inv_x",
                diagnosis_id="diag_x",
                targets_total=10,
                targets_pending=9,
                targets_succeeded=0,
                targets_failed=0,
                targets_expired=0,
            )

    def test_recovered_amount_cannot_exceed_target(self):
        with pytest.raises(ValidationError):
            InterventionOutcome(
                action_id="act_x",
                investigation_id="inv_x",
                diagnosis_id="diag_x",
                amount_targeted_minor=1000,
                amount_recovered_minor=2000,
            )

    def test_to_summary_round_trip_keys(self):
        outcome = self._build(targets_total=10, targets_pending=10)
        s = outcome.to_summary()
        assert s["status"] == "PENDING"
        assert s["action_id"] == "act_001"
        assert s["amount_targeted_minor"] == 0
        assert s["amount_recovered_minor"] == 0


class TestTargetOutcome:
    def _build(self, **overrides) -> RecoveryTargetOutcome:
        defaults = dict(
            outcome_id="out_001",
            target_id="tgt_001",
            payment_id="pay_001",
            expected_amount_minor=1000,
        )
        defaults.update(overrides)
        return RecoveryTargetOutcome(**defaults)

    def test_initial_status_pending(self):
        t = self._build()
        assert t.status == TargetOutcomeStatus.PENDING
        assert t.is_terminal() is False
        assert t.paid_at is None

    def test_transition_to_paid(self):
        t = self._build()
        t.transition(TargetOutcomeStatus.PAID, event_id="evt_001")
        assert t.status == TargetOutcomeStatus.PAID
        assert t.paid_at is not None
        assert t.is_terminal()
        assert t.recovered_amount_minor == 1000  # defaults to expected when provider omits

    def test_transition_to_paid_with_amount(self):
        t = self._build()
        t.transition(TargetOutcomeStatus.PAID, recovered_amount_minor=750)
        assert t.recovered_amount_minor == 750

    def test_illegal_transition_raises(self):
        t = self._build()
        t.transition(TargetOutcomeStatus.PAID)
        with pytest.raises(ValueError):
            t.transition(TargetOutcomeStatus.FAILED)

    def test_out_of_order_event_rejected_on_terminal(self):
        t = self._build()
        t1 = dt.datetime(2026, 9, 1, 12, 0, 0)
        old = dt.datetime(2026, 8, 1, 12, 0, 0)
        t.transition(TargetOutcomeStatus.PAID, event_id="evt_new", event_at=t1)
        # An older event must NOT change state (target is already terminal).
        with pytest.raises(ValueError):
            t.transition(TargetOutcomeStatus.FAILED, event_id="evt_old", event_at=old)

    def test_same_event_id_replay_is_silent_noop(self):
        t = self._build()
        evt_time = dt.datetime(2026, 9, 1, 12, 0, 0)
        t.transition(TargetOutcomeStatus.PAID, event_id="evt_x", event_at=evt_time)
        assert t.transition_count == 1
        # Same event id replayed: state unchanged, transition_count unchanged.
        t.transition(TargetOutcomeStatus.PAID, event_id="evt_x", event_at=evt_time)
        assert t.transition_count == 1
        assert t.status == TargetOutcomeStatus.PAID

    def test_to_summary_shape(self):
        t = self._build()
        s = t.to_summary()
        assert s["target_outcome_id"] == t.target_outcome_id
        assert s["status"] == "PENDING"
        assert s["payment_id"] == "pay_001"


class TestMetrics:
    def test_treatment_effectiveness_rejects_negative(self):
        with pytest.raises(ValidationError):
            TreatmentEffectiveness(
                intervention_outcome_id="out_x",
                targets_total=0,
                targets_recovered=0,
                targets_pending=0,
                targets_unrecovered=0,
                amount_targeted_minor=-1,
                amount_recovered_minor=0,
                amount_remaining_minor=0,
            )

    def test_case_summary_lineage(self):
        entry = CaseSummaryEntry(stage="outcome", reference_id="out_x", status="RECOVERED")
        summary = FinancialCaseSummary(
            action_id="act_x",
            outcome_id="out_x",
            outcome_status="RECOVERED",
            lineage=[entry],
        )
        assert summary.action_id == "act_x"
        assert summary.lineage[0].stage == "outcome"
        assert summary.journey_label("outcome") == "OUTCOME"


class TestAudit:
    def test_audit_event_defaults(self):
        ev = AuditEvent(
            event_type=AuditEventType.OUTCOME_INITIALIZED,
            actor=AuditActor.SYSTEM,
            entity_type="outcome",
            entity_id="out_001",
            new_state="PENDING",
        )
        assert ev.event_type == AuditEventType.OUTCOME_INITIALIZED
        assert ev.actor == AuditActor.SYSTEM
        assert ev.audit_id.startswith("aud_")
        assert isinstance(ev.timestamp, dt.datetime)