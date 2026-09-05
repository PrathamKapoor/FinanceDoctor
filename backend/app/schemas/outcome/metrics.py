"""Treatment effectiveness metrics + case summary lineage.

These schemas are the *output* of the outcome layer. They are
deterministically derived from the underlying ``InterventionOutcome``
+ ``RecoveryTargetOutcome`` records — never computed by an LLM.
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from pydantic import BaseModel, Field


class TreatmentEffectiveness(BaseModel):
    """Deterministically computed effectiveness metrics for one intervention.

    A field is ``None`` whenever the metric cannot be calculated yet
    (e.g. time-to-first-recovery before any target has been paid).
    """

    intervention_outcome_id: str = Field(..., description="Parent outcome ID")

    targets_total: int = Field(..., ge=0)
    targets_recovered: int = Field(..., ge=0)
    targets_pending: int = Field(..., ge=0)
    targets_unrecovered: int = Field(
        ..., ge=0, description="Sum of failed + expired targets"
    )

    currency: str = Field(default="INR", min_length=3, max_length=3)
    amount_targeted_minor: int = Field(..., ge=0)
    amount_recovered_minor: int = Field(..., ge=0)
    amount_remaining_minor: int = Field(..., ge=0)

    recovery_rate: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="targets_recovered / targets_total (None if total == 0)",
    )
    revenue_recovery_rate: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="amount_recovered / amount_targeted (None if targeted == 0)",
    )

    time_to_first_recovery_seconds: float | None = Field(
        default=None, description="seconds from outcome init -> first PAID target"
    )
    time_to_last_recovery_seconds: float | None = Field(
        default=None, description="seconds from outcome init -> last PAID target"
    )

    computed_at: dt.datetime = Field(default_factory=dt.datetime.utcnow)


class CaseSummaryEntry(BaseModel):
    """One node in the lineage chain.

    Each entry holds a reference to a single artifact in the financial
    doctor journey: incident, investigation, diagnosis, action, policy,
    approval, execution, outcome.
    """

    stage: str = Field(..., description="Pipeline stage (incident, investigation, ...)")
    reference_id: str = Field(..., description="ID of the underlying record")
    status: str | None = None
    timestamp: dt.datetime | None = None
    notes: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class FinancialCaseSummary(BaseModel):
    """Deterministically assembled end-to-end case summary.

    This is the *contract* a future UI consumes. It is never produced
    by an LLM — it is rebuilt from structured records.
    """

    case_summary_id: str = Field(
        default_factory=lambda: f"cs_{uuid.uuid4().hex[:12]}",
        description="Synthetic case summary ID (UI convenience)",
    )

    incident_type: str | None = None
    investigation_id: str | None = None
    diagnosis_id: str | None = None
    action_id: str | None = None
    policy_decision_id: str | None = None
    approval_id: str | None = None
    execution_id: str | None = None
    outcome_id: str | None = None

    symptom: str | None = None
    diagnosis: str | None = None
    prescription: str | None = None
    approval_status: str | None = None
    treatment_status: str | None = None
    outcome_status: str | None = None

    lineage: list[CaseSummaryEntry] = Field(default_factory=list)
    treatment_effectiveness: TreatmentEffectiveness | None = None

    generated_at: dt.datetime = Field(default_factory=dt.datetime.utcnow)

    def journey_label(self, stage: str) -> str:
        """Stable label for the UI journey."""
        return stage.upper()