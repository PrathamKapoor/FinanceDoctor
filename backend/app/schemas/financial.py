"""Pydantic schemas for deterministic analytics outputs (Stage 1).

These are the machine-readable contracts that later M2.7/M3 stages will consume. Every number
is computed, never invented.
"""

from __future__ import annotations

import datetime as dt

from pydantic import BaseModel, Field


class AttemptMetrics(BaseModel):
    total_attempts: int = Field(ge=0)
    successful_attempts: int = Field(ge=0)
    failed_attempts: int = Field(ge=0)
    success_rate: float
    failure_rate: float


class WindowComparison(BaseModel):
    baseline: AttemptMetrics
    current: AttemptMetrics
    absolute_delta: float
    relative_delta: float


class TimeBucketStat(BaseModel):
    bucket: str
    attempt_count: int = Field(ge=0)
    failure_count: int = Field(ge=0)
    failure_rate: float


class MethodStat(BaseModel):
    method: str
    attempt_count: int = Field(ge=0)
    failure_count: int = Field(ge=0)
    failure_rate: float
    baseline_failure_rate: float
    delta: float


class CohortStat(BaseModel):
    cohort: str
    attempt_count: int = Field(ge=0)
    failure_count: int = Field(ge=0)
    failure_rate: float
    baseline_failure_rate: float
    delta: float


class ReasonStat(BaseModel):
    reason: str
    failure_count: int = Field(ge=0)
    failure_rate: float


class MonetaryStat(BaseModel):
    currency: str
    total_amount_minor: int
    failed_amount_minor: int


class AnomalyResult(BaseModel):
    metric: str = "payment_failure_rate"
    method: str
    baseline: float
    baseline_mean: float
    baseline_std: float
    current: float
    absolute_delta: float
    relative_delta: float
    sample_size: int = Field(ge=0)
    anomaly_score: float
    threshold: float
    is_anomalous: bool


class IncidentSummary(BaseModel):
    type: str
    start_time: dt.datetime
    end_time: dt.datetime
    affected_dimension: str | None = None
    affected_value: str | None = None
    is_injected: bool