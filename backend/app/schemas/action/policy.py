"""Policy engine schemas."""

from __future__ import annotations

import datetime as dt
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class PolicyCheckStatus(StrEnum):
    """Result of an individual policy check."""

    PASS = "PASS"
    FAIL = "FAIL"
    SKIP = "SKIP"


class PolicyCheck(BaseModel):
    """Individual policy check result."""

    check: str = Field(..., description="Check identifier (e.g., 'amount_limit')")
    status: PolicyCheckStatus = Field(..., description="PASS, FAIL, or SKIP")
    actual: Any = Field(default=None, description="Actual value measured")
    limit: Any = Field(default=None, description="Configured limit")
    message: str = Field(..., description="Human-readable explanation")
    evaluated_at: dt.datetime = Field(default_factory=dt.datetime.utcnow)


class PolicyDecision(StrEnum):
    """Final policy decision."""

    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    HUMAN_APPROVAL_REQUIRED = "HUMAN_APPROVAL_REQUIRED"


class PolicyDecisionRecord(BaseModel):
    """Complete policy evaluation result."""

    decision: PolicyDecision = Field(..., description="Final decision")
    policy_version: str = Field(default="1.0", description="Policy schema version")
    checks: list[PolicyCheck] = Field(default_factory=list, description="Individual check results")
    reasons: list[str] = Field(default_factory=list, description="Human-readable decision reasons")
    action_snapshot_hash: str = Field(
        ..., description="SHA256 of action snapshot at evaluation time"
    )
    evaluated_at: dt.datetime = Field(default_factory=dt.datetime.utcnow)
    evaluated_by: str = Field(default="SYSTEM", description="SYSTEM or MODEL")

    @property
    def passed(self) -> bool:
        return all(c.status == PolicyCheckStatus.PASS for c in self.checks)

    @property
    def failed_checks(self) -> list[PolicyCheck]:
        return [c for c in self.checks if c.status == PolicyCheckStatus.FAIL]


class PolicyConfig(BaseModel):
    """Configurable policy thresholds."""

    max_recovery_amount_minor: int = Field(
        default=50_000_000, description="Max total recovery amount in minor units (₹500,000)"
    )
    max_targets_per_action: int = Field(
        default=100, description="Max targets per action"
    )
    max_actions_per_hour: int = Field(
        default=10, description="Max actions per hour per merchant"
    )
    require_human_approval: bool = Field(
        default=True, description="Require human approval for financial writes"
    )
    allowed_action_types: list[str] = Field(
        default=["CREATE_PAYMENT_LINK"], description="Allowed action type identifiers"
    )
    max_recovery_window_hours: int = Field(
        default=24, description="Max hours after failure to allow recovery"
    )
    approval_ttl_minutes: int = Field(
        default=60, description="Approval validity in minutes"
    )
    max_recovery_amount_per_target_minor: int = Field(
        default=1_000_000, description="Max amount per single target (10,000 INR)"
    )
    require_merchant_configured: bool = Field(
        default=True, description="Merchant must be configured for recovery"
    )
    max_actions_per_day: int = Field(
        default=50, description="Max actions per day per merchant"
    )


class DefaultPolicyConfig:
    """Singleton for default policy configuration."""

    _instance: PolicyConfig | None = None

    @classmethod
    def get(cls) -> PolicyConfig:
        if cls._instance is None:
            cls._instance = PolicyConfig()
        return cls._instance

    @classmethod
    def set(cls, config: PolicyConfig) -> None:
        cls._instance = config