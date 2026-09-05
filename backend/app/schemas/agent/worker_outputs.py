"""M2.7 Worker output schemas.

Each worker returns a strictly validated structured output.
These are the internal contracts between M2.7 workers and the orchestrator/M3.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field, field_validator


class SupportedHypothesis(StrEnum):
    """Hypotheses that workers can support or contradict."""

    PAYMENT_METHOD_DEGRADATION = "PAYMENT_METHOD_DEGRADATION"
    TEMPORAL_SPIKE = "TEMPORAL_SPIKE"
    CUSTOMER_BEHAVIOR_CHANGE = "CUSTOMER_BEHAVIOR_CHANGE"
    FRAUD_SPIKE = "FRAUD_SPIKE"
    INFRASTRUCTURE_ISSUE = "INFRASTRUCTURE_ISSUE"
    CHECKOUT_PROBLEM = "CHECKOUT_PROBLEM"
    GENERAL_PAYMENT_FAILURE = "GENERAL_PAYMENT_FAILURE"


class WorkerOutputBase(BaseModel):
    """Base class for all M2.7 worker outputs."""

    worker: str = Field(..., description="Worker identifier (e.g., 'temporal')")
    finding: str = Field(..., min_length=10, description="Natural language finding citing evidence")
    evidence_ids: list[str] = Field(
        default_factory=list, description="IDs of evidence items referenced in finding"
    )
    supports: list[SupportedHypothesis] = Field(
        default_factory=list, description="Hypotheses supported by this finding"
    )
    contradicts: list[SupportedHypothesis] = Field(
        default_factory=list, description="Hypotheses contradicted by this finding"
    )
    confidence: float = Field(
        ..., ge=0.0, le=1.0, description="Worker's confidence in this finding (0-1)"
    )

    @field_validator("evidence_ids")
    @classmethod
    def _validate_evidence_ids(cls, v: list[str]) -> list[str]:
        for eid in v:
            if not eid or not isinstance(eid, str):
                raise ValueError("evidence_ids must be non-empty strings")
        return v


class TemporalWorkerOutput(WorkerOutputBase):
    """Output from the temporal investigation worker."""

    worker: str = Field(default="temporal", pattern="^temporal$")
    # Additional temporal-specific fields can be added here
    anomaly_detected: bool = Field(default=False, description="Whether temporal anomaly detected")
    peak_window: str | None = Field(default=None, description="Time window of peak anomaly")


class PaymentMethodWorkerOutput(WorkerOutputBase):
    """Output from the payment method investigation worker."""

    worker: str = Field(default="payment_method", pattern="^payment_method$")
    affected_methods: list[str] = Field(
        default_factory=list, description="Payment methods with significant deviation"
    )
    max_delta: float = Field(default=0.0, ge=0.0, description="Maximum failure rate delta observed")


class CohortWorkerOutput(WorkerOutputBase):
    """Output from the customer cohort investigation worker."""

    worker: str = Field(default="cohort", pattern="^cohort$")
    affected_cohorts: list[str] = Field(
        default_factory=list, description="Cohorts with significant deviation"
    )
    returning_bias: float | None = Field(
        default=None, description="Additional returning-customer impact if detected"
    )


class FailureReasonWorkerOutput(WorkerOutputBase):
    """Output from the failure reason investigation worker."""

    worker: str = Field(default="failure_reason", pattern="^failure_reason$")
    dominant_reason: str | None = Field(default=None, description="Most prevalent failure reason")
    dominance_ratio: float = Field(
        default=0.0, ge=0.0, le=1.0, description="Share of top reason in current failures"
    )