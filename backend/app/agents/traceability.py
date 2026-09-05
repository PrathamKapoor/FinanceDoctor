"""Traceability and model call logging for auditability."""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from pydantic import BaseModel, Field


class ModelCallTrace(BaseModel):
    """A single model invocation trace record."""

    trace_id: str = Field(default_factory=lambda: f"trc_{uuid.uuid4().hex[:12]}")
    investigation_id: str | None = None
    worker: str | None = Field(
        default=None,
        description="Worker name (temporal, payment_method, etc.) or 'm3'",
    )
    model: str = Field(..., description="Model identifier (e.g., 'MiniMax-M2.7', 'stub')")
    prompt_version: str = Field(default="1.0", description="Prompt version used")
    started_at: dt.datetime = Field(default_factory=dt.datetime.utcnow)
    completed_at: dt.datetime | None = None
    status: str = Field(default="started", description="started, completed, failed")
    input_evidence_ids: list[str] = Field(default_factory=list)
    output_summary: str | None = None
    error: str | None = None
    latency_ms: int | None = None

    def complete(self, output: Any | None = None, error: str | None = None) -> None:
        self.completed_at = dt.datetime.utcnow()
        self.latency_ms = int((self.completed_at - self.started_at).total_seconds() * 1000)
        if error:
            self.status = "failed"
            self.error = error
        else:
            self.status = "completed"
            if output:
                self.output_summary = str(output)[:500]


class TraceStore:
    """In-memory trace store (replace with persistent store in production)."""

    def __init__(self) -> None:
        self._traces: dict[str, ModelCallTrace] = {}

    def add(self, trace: ModelCallTrace) -> None:
        self._traces[trace.trace_id] = trace

    def get(self, trace_id: str) -> ModelCallTrace | None:
        return self._traces.get(trace_id)

    def get_by_investigation(self, investigation_id: str) -> list[ModelCallTrace]:
        return [t for t in self._traces.values() if t.investigation_id == investigation_id]

    def get_by_worker(self, worker: str) -> list[ModelCallTrace]:
        return [t for t in self._traces.values() if t.worker == worker]


# Global trace store instance
_trace_store = TraceStore()


def get_trace_store() -> TraceStore:
    return _trace_store


def create_trace(
    investigation_id: str | None,
    worker: str | None,
    model: str,
    prompt_version: str = "1.0",
    input_evidence_ids: list[str] | None = None,
) -> ModelCallTrace:
    """Create and register a new trace record."""
    trace = ModelCallTrace(
        investigation_id=investigation_id,
        worker=worker,
        model=model,
        prompt_version=prompt_version,
        input_evidence_ids=input_evidence_ids or [],
    )
    _trace_store.add(trace)
    return trace


def log_model_call(
    investigation_id: str | None,
    worker: str | None,
    model: str,
    prompt_version: str,
    input_evidence_ids: list[str],
    output: Any,
    error: str | None = None,
) -> ModelCallTrace:
    """Convenience function to log a complete model call."""
    trace = create_trace(investigation_id, worker, model, prompt_version, input_evidence_ids)
    trace.complete(output=output, error=error)
    return trace