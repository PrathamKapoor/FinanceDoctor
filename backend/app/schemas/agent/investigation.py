"""Investigation state machine and core schemas."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class InvestigationState(StrEnum):
    """Explicit investigation states - every transition is observable."""

    CREATED = "CREATED"
    EVIDENCE_PREPARING = "EVIDENCE_PREPARING"
    WORKERS_RUNNING = "WORKERS_RUNNING"
    EVIDENCE_ASSEMBLED = "EVIDENCE_ASSEMBLED"
    DIAGNOSIS_RUNNING = "DIAGNOSIS_RUNNING"
    DIAGNOSIS_COMPLETE = "DIAGNOSIS_COMPLETE"
    FAILED = "FAILED"


# Valid state transitions
VALID_TRANSITIONS: dict[str, list[str]] = {
    "CREATED": ["EVIDENCE_PREPARING", "FAILED"],
    "EVIDENCE_PREPARING": ["WORKERS_RUNNING", "FAILED"],
    "WORKERS_RUNNING": ["EVIDENCE_ASSEMBLED", "FAILED"],
    "EVIDENCE_ASSEMBLED": ["DIAGNOSIS_RUNNING", "FAILED"],
    "DIAGNOSIS_RUNNING": ["DIAGNOSIS_COMPLETE", "FAILED"],
    "DIAGNOSIS_COMPLETE": [],
    "FAILED": [],
}


class Investigation(BaseModel):
    """An investigation instance tracking the full lifecycle."""

    investigation_id: str = Field(..., pattern=r"^inv_[a-zA-Z0-9_]+$")
    incident_type: str = Field(..., description="Type of incident being investigated")
    state: InvestigationState = Field(default=InvestigationState.CREATED)
    anomaly_detected: bool = False
    anomaly_score: float | None = None
    evidence_bundle_ref: str | None = None  # Reference to stored EvidenceBundle
    worker_outputs_ref: dict[str, str] = Field(default_factory=dict)  # worker -> ref
    diagnosis_ref: str | None = None  # Reference to DiagnosisOutput
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: datetime | None = None
    error: str | None = None
    trace_id: str | None = None

    def can_transition(self, new_state: InvestigationState) -> bool:
        return new_state.value in VALID_TRANSITIONS.get(self.state.value, [])

    def transition(self, new_state: InvestigationState) -> None:
        if not self.can_transition(new_state):
            raise ValueError(f"Invalid transition: {self.state} -> {new_state}")
        self.state = new_state
        self.updated_at = datetime.utcnow()
        if new_state == InvestigationState.DIAGNOSIS_COMPLETE:
            self.completed_at = datetime.utcnow()


class EvidenceBundleRef(BaseModel):
    """Reference to an evidence bundle stored in the evidence store."""

    scope: str = Field(..., description="Scope identifier (e.g., investigation ID)")
    evidence_count: int = Field(ge=0)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    schema_version: str = "1.0"