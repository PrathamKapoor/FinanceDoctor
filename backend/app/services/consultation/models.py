"""Consultation domain models — the read-only question/answer layer (Stage 7A).

The consultation service reasons over a ``ConsultationContext`` built
deterministically from the ``CaseView`` read-model. It never receives action
services, adapters, or mutation handles — architecturally, there is nothing
for a prompt-injected model to call even if it tried.
"""

from __future__ import annotations

import datetime as dt
import uuid
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class AnswerType(StrEnum):
    """What kind of question the consultation answered."""

    INCIDENT = "incident"
    DIAGNOSIS = "diagnosis"
    EVIDENCE = "evidence"
    TREATMENT = "treatment"
    SAFETY = "safety"
    OUTCOME = "outcome"
    GENERAL = "general"
    REFUSED = "refused"


class ConsultationSection(StrEnum):
    """Case sections an answer may reference (drives UI highlighting)."""

    INCIDENT = "incident"
    METRICS = "metrics"
    INVESTIGATION = "investigation"
    DIAGNOSIS = "diagnosis"
    EVIDENCE = "evidence"
    TREATMENT = "treatment"
    POLICY = "policy"
    APPROVAL = "approval"
    EXECUTION = "execution"
    OUTCOME = "outcome"


class ConsultationTimings(BaseModel):
    """Basic performance observability. No secrets, ever."""

    context_build_ms: int = 0
    model_latency_ms: int = 0
    speech_latency_ms: int = 0
    total_latency_ms: int = 0


class ConsultationContext(BaseModel):
    """AI-safe, redacted, structured case context for the consultation model.

    Built deterministically from ``CaseView`` by ``ConsultationContextBuilder``.
    Contains exact metric strings the model may quote (``key_figures``) and no
    secrets, credentials, or per-target customer identifiers.
    """

    case_id: str
    incident: dict[str, Any] = Field(default_factory=dict)
    metrics: dict[str, Any] = Field(default_factory=dict)
    investigation: dict[str, Any] = Field(default_factory=dict)
    diagnosis: dict[str, Any] = Field(default_factory=dict)
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    recommended_action: dict[str, Any] = Field(default_factory=dict)
    policy_status: dict[str, Any] = Field(default_factory=dict)
    approval_status: dict[str, Any] = Field(default_factory=dict)
    execution_status: dict[str, Any] = Field(default_factory=dict)
    outcome: dict[str, Any] = Field(default_factory=dict)
    key_figures: dict[str, str] = Field(
        default_factory=dict,
        description="Exact display strings the model may quote (amounts, rates).",
    )


class ConsultationRequest(BaseModel):
    """Inbound question for one case."""

    question: str = Field(..., min_length=1, max_length=1000)


class ConsultationResponse(BaseModel):
    """Validated answer. The only model output the frontend ever sees."""

    consultation_id: str = Field(
        default_factory=lambda: f"cons_{uuid.uuid4().hex[:12]}"
    )
    case_id: str
    question: str
    answer: str = Field(..., min_length=1, max_length=4000)
    answer_type: AnswerType = AnswerType.GENERAL
    referenced_sections: list[ConsultationSection] = Field(default_factory=list)
    generated_at: dt.datetime = Field(default_factory=dt.datetime.utcnow)
    model: str = "stub"
    timings: ConsultationTimings = Field(default_factory=ConsultationTimings)


class ConsultationRecord(BaseModel):
    """Minimal per-case consultation history entry (metadata only)."""

    consultation_id: str
    case_id: str
    question: str
    answer: str
    answer_type: AnswerType
    referenced_sections: list[ConsultationSection] = Field(default_factory=list)
    model: str = "stub"
    created_at: dt.datetime = Field(default_factory=dt.datetime.utcnow)


class SpeechResult(BaseModel):
    """Synthesized audio. The stub returns an explicit placeholder WAV."""

    mime_type: str = "audio/wav"
    data_base64: str = Field(..., description="Base64-encoded audio bytes")
    byte_size: int = Field(ge=0)
    duration_ms: int | None = None
    provider: str = "stub"
    voice: str | None = None


__all__ = [
    "AnswerType",
    "ConsultationSection",
    "ConsultationTimings",
    "ConsultationContext",
    "ConsultationRequest",
    "ConsultationResponse",
    "ConsultationRecord",
    "SpeechResult",
]
