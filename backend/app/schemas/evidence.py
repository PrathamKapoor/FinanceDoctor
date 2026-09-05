"""Pydantic schemas for deterministic evidence objects and the evidence bundle.

Evidence is machine-readable: typed, numeric where possible, with explicit units/values, and
never stored as prose.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from backend.app.schemas.financial import (
    AnomalyResult,
    CohortStat,
    IncidentSummary,
    MethodStat,
    MonetaryStat,
    ReasonStat,
    TimeBucketStat,
    WindowComparison,
)


class Evidence(BaseModel):
    id: str
    kind: str
    metric: str
    value: Any = None
    unit: str | None = None
    baseline: Any = None
    current: Any = None
    delta: Any = None
    window: str | None = None
    dimension: str | None = None
    source: str = "deterministic"


class EvidenceBundle(BaseModel):
    incident: IncidentSummary
    overall: WindowComparison
    temporal: list[TimeBucketStat] = Field(default_factory=list)
    baseline_daily: list[TimeBucketStat] = Field(default_factory=list)
    payment_methods: list[MethodStat] = Field(default_factory=list)
    cohorts: list[CohortStat] = Field(default_factory=list)
    failure_reasons: list[ReasonStat] = Field(default_factory=list)
    monetary: MonetaryStat
    anomaly: AnomalyResult