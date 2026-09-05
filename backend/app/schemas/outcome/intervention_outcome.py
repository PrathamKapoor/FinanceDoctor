"""InterventionOutcome - aggregate measured result of a recovery action.

Stage 5 introduces this domain object. The Financial Doctor does not
declare success when it writes a prescription — it declares success
based on the measured patient outcome. ``InterventionOutcome`` is that
measurement.
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from pydantic import BaseModel, Field, field_validator

from backend.app.schemas.outcome.enums import OutcomeStatus, assert_outcome_transition


class InterventionOutcome(BaseModel):
    """Aggregate outcome for a single intervention (e.g. one CREATE_PAYMENT_LINK batch)."""

    outcome_id: str = Field(
        default_factory=lambda: f"out_{uuid.uuid4().hex[:12]}",
        description="Unique outcome identifier",
    )
    action_id: str = Field(..., description="Action that produced this outcome")
    execution_id: str | None = Field(
        default=None,
        description="Execution record that spawned this outcome (None if not yet executed)",
    )
    investigation_id: str = Field(..., description="Source investigation ID")
    diagnosis_id: str = Field(..., description="Source diagnosis ID")
    approval_id: str | None = Field(default=None, description="Approval that authorized execution")

    status: OutcomeStatus = Field(
        default=OutcomeStatus.PENDING,
        description="Current aggregate status; transitions are deterministic",
    )

    # Target rollups — kept in sync by the OutcomeEvaluator.
    targets_total: int = Field(default=0, ge=0)
    targets_pending: int = Field(default=0, ge=0)
    targets_succeeded: int = Field(default=0, ge=0)
    targets_failed: int = Field(default=0, ge=0)
    targets_expired: int = Field(default=0, ge=0)

    # Money — all integer minor units, no floats.
    currency: str = Field(default="INR", min_length=3, max_length=3)
    amount_targeted_minor: int = Field(default=0, ge=0)
    amount_recovered_minor: int = Field(default=0, ge=0)

    conversion_rate: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Deterministic recovered/targeted ratio (0.0–1.0); None when undefined",
    )

    created_at: dt.datetime = Field(
        default_factory=dt.datetime.utcnow,
        description="Initialisation timestamp (used for time-to-recovery metrics)",
    )

    first_observed_at: dt.datetime | None = Field(
        default=None, description="First provider-confirmed observation timestamp"
    )
    last_updated_at: dt.datetime = Field(default_factory=dt.datetime.utcnow)
    finalized_at: dt.datetime | None = Field(default=None, description="Set on terminal status")

    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("targets_expired")
    @classmethod
    def _check_target_counts(cls, v: int, info) -> int:
        parts = info.data
        succeeded = parts.get("targets_succeeded", 0)
        failed = parts.get("targets_failed", 0)
        expired = v
        pending = parts.get("targets_pending", 0)
        total = parts.get("targets_total", 0)
        if succeeded + failed + expired + pending != total:
            raise ValueError(
                "targets_total must equal succeeded + failed + expired + pending"
            )
        return v

    @field_validator("amount_recovered_minor")
    def _check_recovered_within_target(cls, v: int, info) -> int:
        targeted = info.data.get("amount_targeted_minor", 0)
        if v > targeted:
            raise ValueError(
                f"amount_recovered_minor ({v}) cannot exceed amount_targeted_minor ({targeted})"
            )
        return v

    def transition(self, new_status: OutcomeStatus) -> None:
        """Apply a deterministic aggregate status transition.

        Raises ``ValueError`` if the transition is not in the allowed
        table. The evaluator is the only legitimate caller.
        """
        assert_outcome_transition(self.status, new_status)
        self.status = new_status
        self.last_updated_at = dt.datetime.utcnow()
        if new_status in (
            OutcomeStatus.RECOVERED,
            OutcomeStatus.NO_RECOVERY,
            OutcomeStatus.EXPIRED,
            OutcomeStatus.FAILED,
        ):
            self.finalized_at = self.last_updated_at

    def is_terminal(self) -> bool:
        return self.finalized_at is not None

    def to_summary(self) -> dict[str, Any]:
        """Compact dict summary (used by case summaries)."""
        return {
            "outcome_id": self.outcome_id,
            "action_id": self.action_id,
            "execution_id": self.execution_id,
            "investigation_id": self.investigation_id,
            "diagnosis_id": self.diagnosis_id,
            "approval_id": self.approval_id,
            "status": self.status.value,
            "targets_total": self.targets_total,
            "targets_pending": self.targets_pending,
            "targets_succeeded": self.targets_succeeded,
            "targets_failed": self.targets_failed,
            "targets_expired": self.targets_expired,
            "amount_targeted_minor": self.amount_targeted_minor,
            "amount_recovered_minor": self.amount_recovered_minor,
            "conversion_rate": self.conversion_rate,
            "first_observed_at": (
                self.first_observed_at.isoformat() if self.first_observed_at else None
            ),
            "last_updated_at": self.last_updated_at.isoformat(),
            "finalized_at": self.finalized_at.isoformat() if self.finalized_at else None,
        }