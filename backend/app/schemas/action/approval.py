"""Human approval schemas."""

from __future__ import annotations

import datetime as dt
from enum import StrEnum

from pydantic import BaseModel, Field


class ApprovalStatus(StrEnum):
    """Approval request lifecycle status."""

    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


class ApprovalRequest(BaseModel):
    """Human approval request for a proposed action."""

    approval_id: str = Field(
        default_factory=lambda: f"apr_{__import__('uuid').uuid4().hex[:12]}",
        description="Unique approval identifier",
    )
    action_id: str = Field(..., description="Action being approved")
    action_snapshot_hash: str = Field(..., description="SHA256 of action snapshot at approval time")
    status: ApprovalStatus = Field(default=ApprovalStatus.PENDING)
    requested_at: dt.datetime = Field(default_factory=dt.datetime.utcnow)
    expires_at: dt.datetime = Field(..., description="Expiration timestamp")
    approved_at: dt.datetime | None = None
    rejected_at: dt.datetime | None = None
    decision_reason: str | None = Field(
        default=None, description="Human-provided reason for decision"
    )
    decided_by: str | None = Field(
        default=None, description="Human identifier who made decision"
    )

    @property
    def is_expired(self) -> bool:
        return dt.datetime.utcnow() > self.expires_at

    @property
    def is_terminal(self) -> bool:
        return self.status in (
            ApprovalStatus.APPROVED,
            ApprovalStatus.REJECTED,
            ApprovalStatus.EXPIRED,
        )

    def approve(self, decided_by: str, reason: str | None = None) -> None:
        if self.status != ApprovalStatus.PENDING:
            raise ValueError(f"Cannot approve approval in status {self.status}")
        if self.is_expired:
            raise ValueError("Cannot approve expired approval")
        self.status = ApprovalStatus.APPROVED
        self.approved_at = dt.datetime.utcnow()
        self.decided_by = decided_by
        self.decision_reason = reason

    def reject(self, decided_by: str, reason: str | None = None) -> None:
        if self.status != ApprovalStatus.PENDING:
            raise ValueError(f"Cannot reject approval in status {self.status}")
        self.status = ApprovalStatus.REJECTED
        self.rejected_at = dt.datetime.utcnow()
        self.decided_by = decided_by
        self.decision_reason = reason