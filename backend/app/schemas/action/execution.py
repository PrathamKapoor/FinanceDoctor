"""Action execution schemas."""

from __future__ import annotations

import datetime as dt
from enum import StrEnum

from pydantic import BaseModel, Field


class ExecutionStatus(StrEnum):
    """Action execution lifecycle status."""

    PENDING = "PENDING"
    EXECUTING = "EXECUTING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


class ActionExecution(BaseModel):
    """Record of an action execution attempt."""

    execution_id: str = Field(
        default_factory=lambda: f"exe_{__import__('uuid').uuid4().hex[:12]}",
        description="Unique execution identifier",
    )
    action_id: str = Field(..., description="Action being executed")
    approval_id: str | None = Field(default=None, description="Associated approval ID")
    status: ExecutionStatus = Field(default=ExecutionStatus.PENDING)
    provider: str = Field(default="razorpay", description="Provider identifier")
    provider_operation: str | None = Field(default=None, description="Provider operation name")
    provider_reference: str | None = Field(
        default=None, description="Provider's reference ID (e.g., plink_...)"
    )
    idempotency_key: str = Field(..., description="Deterministic key for idempotency")
    started_at: dt.datetime = Field(default_factory=dt.datetime.utcnow)
    completed_at: dt.datetime | None = None
    error_code: str | None = None
    error_message: str | None = None
    provider_request: dict = Field(default_factory=dict, description="Request sent to provider")
    provider_response: dict = Field(default_factory=dict, description="Response from provider")

    def mark_executing(self) -> None:
        self.status = ExecutionStatus.EXECUTING

    def mark_succeeded(
        self,
        provider_ref: str,
        provider_response: dict,
    ) -> None:
        self.status = ExecutionStatus.SUCCEEDED
        self.completed_at = dt.datetime.utcnow()
        self.provider_reference = provider_ref
        self.provider_response = provider_response

    def mark_failed(
        self,
        error_code: str,
        error_message: str,
        provider_response: dict | None = None,
    ) -> None:
        self.status = ExecutionStatus.FAILED
        self.completed_at = dt.datetime.utcnow()
        self.error_code = error_code
        self.error_message = error_message
        if provider_response:
            self.provider_response = provider_response