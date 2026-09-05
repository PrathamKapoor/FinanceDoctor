"""M3 Diagnosis output schema.

This is the senior reasoner's structured output - the final diagnosis
with hypothesis ranking, leading hypothesis, and recommended action.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator


class AlternativeHypothesis(BaseModel):
    """An alternative hypothesis considered but not selected as leading."""

    hypothesis: str = Field(..., description="Hypothesis identifier")
    score: float = Field(..., ge=0.0, le=1.0, description="Relative score (0-1)")
    reason: str = Field(..., description="Why this hypothesis was not selected as leading")


class DiagnosisOutput(BaseModel):
    """M3 Senior Financial Doctor diagnosis output.

    This is the authoritative diagnosis that feeds into the Policy Engine.
    """

    diagnosis_id: str = Field(..., pattern=r"^diag_[a-zA-Z0-9_]+$")
    incident_type: str = Field(..., description="Type of incident investigated")
    leading_hypothesis: str = Field(..., description="The leading hypothesis identifier")
    confidence: float = Field(
        ..., ge=0.0, le=1.0, description="Model-assessed confidence in leading hypothesis (0-1)"
    )
    summary: str = Field(
        ..., min_length=50, description="Natural language explanation citing evidence"
    )
    supporting_evidence_ids: list[str] = Field(
        default_factory=list, description="Evidence IDs supporting the leading hypothesis"
    )
    contradicting_evidence_ids: list[str] = Field(
        default_factory=list, description="Evidence IDs that contradict the leading hypothesis"
    )
    alternative_hypotheses: list[dict[str, Any]] = Field(
        default_factory=list, description="Alternative hypotheses with scores and reasons"
    )
    recommended_action_type: str = Field(
        ..., description="Recommended action type (must match Policy Engine allowlist)"
    )
    action_rationale: str = Field(
        ..., min_length=20, description="Why this action is recommended"
    )
    uncertainties: list[str] = Field(
        default_factory=list, description="Explicit uncertainties and limitations"
    )

    @field_validator("alternative_hypotheses")
    @classmethod
    def _validate_alternatives(cls, v: list[dict[str, Any]]) -> list[dict[str, Any]]:
        for alt in v:
            if not all(k in alt for k in ("hypothesis", "score", "reason")):
                raise ValueError("Each alternative must have hypothesis, score, reason")
            if not 0.0 <= alt["score"] <= 1.0:
                raise ValueError("Alternative score must be 0-1")
        return v

    @field_validator("recommended_action_type")
    @classmethod
    def _validate_action_type(cls, v: str) -> str:
        allowed = {"CREATE_PAYMENT_LINK", "ISSUE_REFUND"}
        if v not in allowed:
            raise ValueError(f"Action type must be one of {allowed}")
        return v

    @field_validator("confidence")
    @classmethod
    def _confidence_not_calibrated(cls, v: float) -> float:
        # This is model-assessed confidence, not calibrated probability
        return v