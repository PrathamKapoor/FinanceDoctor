"""Outcome status enums and transition rules.

All outcome state transitions are deterministic — they live in code and
MUST NOT be selected by an LLM. The transition tables in
``OUTCOME_TRANSITIONS`` / ``TARGET_TRANSITIONS`` document the legal
moves; ``OutcomeEvaluator`` / target handlers enforce them.
"""

from __future__ import annotations

from enum import StrEnum


class OutcomeStatus(StrEnum):
    """Aggregate status of an intervention outcome.

    The aggregate status is derived deterministically from the set of
    target outcomes. It cannot be set directly by an LLM or webhook.
    """

    PENDING = "PENDING"
    PARTIALLY_RECOVERED = "PARTIALLY_RECOVERED"
    RECOVERED = "RECOVERED"
    NO_RECOVERY = "NO_RECOVERY"
    EXPIRED = "EXPIRED"
    FAILED = "FAILED"


class TargetOutcomeStatus(StrEnum):
    """Per-target recovery status.

    A target transitions deterministically on provider-confirmed events.
    """

    PENDING = "PENDING"
    PAID = "PAID"
    FAILED = "FAILED"
    EXPIRED = "EXPIRED"


class AuditEventType(StrEnum):
    """Outcome-layer audit events.

    These extend the existing audit discipline with outcome-specific
    state transitions. ``actor`` discriminates SYSTEM vs PROVIDER.
    """

    OUTCOME_INITIALIZED = "OUTCOME_INITIALIZED"
    TARGET_REGISTERED = "TARGET_REGISTERED"
    TARGET_PAYMENT_CONFIRMED = "TARGET_PAYMENT_CONFIRMED"
    TARGET_MARKED_FAILED = "TARGET_MARKED_FAILED"
    TARGET_EXPIRED = "TARGET_EXPIRED"
    OUTCOME_RECALCULATED = "OUTCOME_RECALCULATED"
    OUTCOME_FINALIZED = "OUTCOME_FINALIZED"
    OUTCOME_WEBHOOK_DUPLICATE = "OUTCOME_WEBHOOK_DUPLICATE"
    OUTCOME_WEBHOOK_IGNORED = "OUTCOME_WEBHOOK_IGNORED"
    OUTCOME_WEBHOOK_UNRELATED = "OUTCOME_WEBHOOK_UNRELATED"
    OUTCOME_PAYMENT_LINK_EXPIRED = "OUTCOME_PAYMENT_LINK_EXPIRED"


class AuditActor(StrEnum):
    """Who produced the audit event."""

    SYSTEM = "SYSTEM"
    PROVIDER = "PROVIDER"
    HUMAN = "HUMAN"


# ----------------------------------------------------------------------
# Allowed status transitions.
#
# These tables are the single source of truth for legal status moves.
# Any attempt to mutate a status outside its allowed set MUST raise.
# ----------------------------------------------------------------------

TARGET_TRANSITIONS: dict[TargetOutcomeStatus, frozenset[TargetOutcomeStatus]] = {
    TargetOutcomeStatus.PENDING: frozenset(
        {TargetOutcomeStatus.PAID, TargetOutcomeStatus.FAILED, TargetOutcomeStatus.EXPIRED}
    ),
    TargetOutcomeStatus.PAID: frozenset(),  # terminal — provider-confirmed payment
    TargetOutcomeStatus.FAILED: frozenset(),  # terminal
    TargetOutcomeStatus.EXPIRED: frozenset(),  # terminal
}

OUTCOME_TRANSITIONS: dict[OutcomeStatus, frozenset[OutcomeStatus]] = {
    OutcomeStatus.PENDING: frozenset(
        {
            OutcomeStatus.PARTIALLY_RECOVERED,
            OutcomeStatus.RECOVERED,
            OutcomeStatus.NO_RECOVERY,
            OutcomeStatus.EXPIRED,
            OutcomeStatus.FAILED,
        }
    ),
    OutcomeStatus.PARTIALLY_RECOVERED: frozenset(
        {OutcomeStatus.RECOVERED, OutcomeStatus.NO_RECOVERY, OutcomeStatus.EXPIRED}
    ),
    OutcomeStatus.RECOVERED: frozenset(),  # terminal
    OutcomeStatus.NO_RECOVERY: frozenset(),  # terminal
    OutcomeStatus.EXPIRED: frozenset(),  # terminal
    OutcomeStatus.FAILED: frozenset(),  # terminal
}


def assert_target_transition(
    current: TargetOutcomeStatus, target: TargetOutcomeStatus
) -> None:
    """Raise ValueError if a target transition is not allowed."""
    allowed = TARGET_TRANSITIONS.get(current, frozenset())
    if target not in allowed:
        raise ValueError(
            f"Illegal target outcome transition: {current.value} -> {target.value}. "
            f"Allowed next states: {sorted(s.value for s in allowed)}"
        )


def assert_outcome_transition(
    current: OutcomeStatus, target: OutcomeStatus
) -> None:
    """Raise ValueError if an aggregate transition is not allowed."""
    allowed = OUTCOME_TRANSITIONS.get(current, frozenset())
    if target not in allowed:
        raise ValueError(
            f"Illegal outcome transition: {current.value} -> {target.value}. "
            f"Allowed next states: {sorted(s.value for s in allowed)}"
        )