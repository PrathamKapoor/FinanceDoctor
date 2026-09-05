"""RecoveryTargetOutcome - per-target measurement of recovery success.

Stage 4 may create Payment Links for one or more eligible recovery
targets. Stage 5 tracks each target individually. A batch action is not
"successful" because one Payment Link was paid — every target is
measured.
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from pydantic import BaseModel, Field

from backend.app.schemas.outcome.enums import TargetOutcomeStatus, assert_target_transition


class RecoveryTargetOutcome(BaseModel):
    """Outcome for a single recovery target (one Payment Link)."""

    target_outcome_id: str = Field(
        default_factory=lambda: f"tgo_{uuid.uuid4().hex[:12]}",
        description="Unique target-outcome identifier",
    )
    outcome_id: str = Field(..., description="Parent InterventionOutcome ID")
    target_id: str = Field(
        ..., description="Stable per-target identifier (e.g. action_id:payment_id)"
    )
    payment_id: str = Field(..., description="Razorpay payment ID this target recovers")
    order_id: str | None = Field(default=None)
    customer_id: str | None = Field(default=None)
    payment_method: str | None = Field(default=None)
    failure_reason: str | None = Field(default=None)

    payment_link_id: str | None = Field(
        default=None, description="Razorpay Payment Link ID (plink_...)"
    )
    provider_reference: str | None = Field(
        default=None, description="Internal reference (e.g. action_id:payment_id)"
    )

    currency: str = Field(default="INR", min_length=3, max_length=3)
    expected_amount_minor: int = Field(default=0, ge=0)
    recovered_amount_minor: int = Field(default=0, ge=0)

    status: TargetOutcomeStatus = Field(default=TargetOutcomeStatus.PENDING)

    created_at: dt.datetime = Field(default_factory=dt.datetime.utcnow)
    paid_at: dt.datetime | None = Field(default=None)
    failed_at: dt.datetime | None = Field(default=None)
    expired_at: dt.datetime | None = Field(default=None)
    last_updated_at: dt.datetime = Field(default_factory=dt.datetime.utcnow)

    # Event-ordering bookkeeping. Stores the provider event id that last
    # transitioned this target, so out-of-order deliveries cannot roll
    # the state backward.
    last_event_id: str | None = None
    last_event_at: dt.datetime | None = None
    transition_count: int = 0

    metadata: dict[str, Any] = Field(default_factory=dict)

    def transition(
        self,
        new_status: TargetOutcomeStatus,
        *,
        event_id: str | None = None,
        event_at: dt.datetime | None = None,
        recovered_amount_minor: int | None = None,
    ) -> None:
        """Apply a deterministic transition with optional event-ordering guard.

        - Raises ``ValueError`` on illegal transitions.
        - Same-event-id replay on a terminal target is a silent no-op
          (idempotent at the schema layer).
        - Older provider events cannot overwrite a terminal status.
        """
        # Same-event-id replay: silent no-op for idempotency.
        if (
            event_id is not None
            and self.last_event_id is not None
            and event_id == self.last_event_id
        ):
            return

        # Illegal transition?
        assert_target_transition(self.status, new_status)

        # Out-of-order event guard. A terminal status (PAID/FAILED/EXPIRED)
        # cannot be replaced by an older event regardless of ordering.
        if self.status != TargetOutcomeStatus.PENDING:
            if event_at and self.last_event_at and event_at < self.last_event_at:
                raise ValueError(
                    f"Out-of-order provider event: incoming event_at={event_at.isoformat()} "
                    f"older than recorded {self.last_event_at.isoformat()}; refusing to "
                    f"overwrite terminal status {self.status.value} with {new_status.value}"
                )

        now = dt.datetime.utcnow()
        self.status = new_status
        self.last_updated_at = now
        self.transition_count += 1
        if event_id is not None:
            self.last_event_id = event_id
        if event_at is not None:
            self.last_event_at = event_at
        if new_status == TargetOutcomeStatus.PAID:
            self.paid_at = event_at or now
            if recovered_amount_minor is not None:
                if recovered_amount_minor < 0:
                    raise ValueError("recovered_amount_minor must be >= 0")
                self.recovered_amount_minor = recovered_amount_minor
            elif self.expected_amount_minor and self.recovered_amount_minor == 0:
                # Default to full expected amount if provider did not
                # specify (e.g. legacy partial-payment webhook shape).
                self.recovered_amount_minor = self.expected_amount_minor
        elif new_status == TargetOutcomeStatus.FAILED:
            self.failed_at = event_at or now
        elif new_status == TargetOutcomeStatus.EXPIRED:
            self.expired_at = event_at or now

    def is_terminal(self) -> bool:
        return self.status in (
            TargetOutcomeStatus.PAID,
            TargetOutcomeStatus.FAILED,
            TargetOutcomeStatus.EXPIRED,
        )

    def to_summary(self) -> dict[str, Any]:
        return {
            "target_outcome_id": self.target_outcome_id,
            "outcome_id": self.outcome_id,
            "target_id": self.target_id,
            "payment_id": self.payment_id,
            "payment_link_id": self.payment_link_id,
            "provider_reference": self.provider_reference,
            "currency": self.currency,
            "expected_amount_minor": self.expected_amount_minor,
            "recovered_amount_minor": self.recovered_amount_minor,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "paid_at": self.paid_at.isoformat() if self.paid_at else None,
            "failed_at": self.failed_at.isoformat() if self.failed_at else None,
            "expired_at": self.expired_at.isoformat() if self.expired_at else None,
            "last_updated_at": self.last_updated_at.isoformat(),
        }