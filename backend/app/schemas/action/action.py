"""Action domain models - core action types and snapshots."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, field_validator


class ActionType(StrEnum):
    """Allowed action types. MVP only supports CREATE_PAYMENT_LINK."""

    CREATE_PAYMENT_LINK = "CREATE_PAYMENT_LINK"


class ActionStatus(StrEnum):
    """Lifecycle status of a proposed action."""

    PROPOSED = "PROPOSED"
    PLANNED = "PLANNED"
    POLICY_EVALUATED = "POLICY_EVALUATED"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    EXECUTING = "EXECUTING"
    EXECUTED = "EXECUTED"
    FAILED = "FAILED"


class ActionTarget(BaseModel):
    """A single financial target for recovery action."""

    payment_id: str = Field(..., description="Razorpay payment ID (e.g., pay_...)")
    order_id: str = Field(..., description="Razorpay order ID (e.g., order_...)")
    customer_id: str = Field(..., description="Razorpay customer ID (e.g., cust_...)")
    amount_minor: int = Field(..., ge=0, description="Amount in minor units (paise for INR)")
    currency: str = Field(..., min_length=3, max_length=3)
    payment_method: str = Field(..., description="Payment method (UPI, CARD, etc.)")
    failure_reason: str = Field(..., description="Failure reason code")


class ProposedAction(BaseModel):
    """A proposed recovery action derived from M3 diagnosis."""

    action_id: str = Field(
        default_factory=lambda: f"act_{__import__('uuid').uuid4().hex[:12]}",
        description="Unique action identifier",
    )
    investigation_id: str = Field(..., description="Source investigation ID")
    diagnosis_id: str = Field(..., description="Source diagnosis ID")
    action_type: ActionType = Field(default=ActionType.CREATE_PAYMENT_LINK)
    targets: list[ActionTarget] = Field(..., min_length=1, description="Targets for recovery")
    total_amount_minor: int = Field(..., ge=0, description="Total amount in minor units")
    currency: str = Field(..., min_length=3, max_length=3)
    status: ActionStatus = Field(default=ActionStatus.PROPOSED)
    rationale: str = Field(..., min_length=20, description="Why this action is recommended")
    created_at: dt.datetime = Field(default_factory=dt.datetime.utcnow)
    updated_at: dt.datetime = Field(default_factory=dt.datetime.utcnow)

    @field_validator("targets")
    @classmethod
    def _validate_targets_not_empty(cls, v: list[ActionTarget]) -> list[ActionTarget]:
        if not v:
            raise ValueError("At least one target required")
        return v

    @field_validator("total_amount_minor")
    @classmethod
    def _validate_amount_matches_targets(cls, v: int, info) -> int:
        if "targets" in info.data:
            expected = sum(t.amount_minor for t in info.data["targets"])
            if v != expected:
                raise ValueError(
                    f"total_amount_minor ({v}) must equal sum of target amounts ({expected})"
                )
        return v


class ActionSnapshot(BaseModel):
    """Immutable snapshot of a proposed action at the time of policy evaluation."""

    action_id: str
    action_type: ActionType
    targets: list[ActionTarget]
    total_amount_minor: int
    currency: str
    rationale: str
    investigation_id: str
    diagnosis_id: str
    eligibility_results: dict[str, Any] = Field(default_factory=dict)
    evidence_references: list[str] = Field(default_factory=list)
    created_at: dt.datetime = Field(default_factory=dt.datetime.utcnow)

    def compute_hash(self) -> str:
        """Compute deterministic SHA256 hash of the snapshot."""
        # Use a canonical JSON representation for hashing
        data = {
            "action_id": self.action_id,
            "action_type": self.action_type.value,
            "targets": [t.model_dump() for t in self.targets],
            "total_amount_minor": self.total_amount_minor,
            "currency": self.currency,
            "rationale": self.rationale,
            "investigation_id": self.investigation_id,
            "diagnosis_id": self.diagnosis_id,
            "eligibility_results": self.eligibility_results,
            "evidence_references": sorted(self.evidence_references),
        }
        canonical = json.dumps(data, sort_keys=True, separators=(",", ":"), default=str)
        return hashlib.sha256(canonical.encode()).hexdigest()

    class Config:
        frozen = True  # Immutable after creation