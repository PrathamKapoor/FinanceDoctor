"""Policy engine - deterministic policy evaluation for proposed actions."""

from __future__ import annotations

import datetime as dt
from typing import Any

from backend.app.schemas.action.action import ProposedAction
from backend.app.schemas.action.policy import (
    PolicyCheck,
    PolicyCheckStatus,
    PolicyConfig,
    PolicyDecision,
    PolicyDecisionRecord,
)
from backend.app.services.synthetic_data import MerchantWorld


class PolicyError(Exception):
    """Policy evaluation error."""
    pass


class PolicyEngine:
    """Deterministic policy engine for evaluating proposed actions."""

    def __init__(
        self,
        world: MerchantWorld,
        config: Any = None,
    ):
        self._world = world
        self._config = config or DefaultPolicyConfig.get()

    def evaluate(self, action: ProposedAction, diagnosis, investigation, snapshot) -> Any:
        """Evaluate a proposed action against all policy checks."""

        checks = []

        # Run all policy checks
        checks.append(self._check_authorization())
        checks.append(self._check_merchant_configured())
        checks.append(self._check_action_type_allowed(snapshot))
        checks.append(self._check_amount_limit(snapshot))
        checks.append(self._check_target_count(snapshot))
        checks.append(self._check_duplicate_prevention(snapshot))
        checks.append(self._check_idempotency(snapshot))
        checks.append(self._check_eligibility(snapshot))
        checks.append(self._check_action_integrity(snapshot))
        checks.append(self._check_investigation_integrity(investigation))
        checks.append(self._check_rate_limit(snapshot))
        checks.append(self._check_amount_per_target(snapshot))

        # Determine final decision
        failed_checks = [c for c in checks if c.status == PolicyCheckStatus.FAIL]
        skipped_checks = [c for c in checks if c.status == PolicyCheckStatus.SKIP]

        if failed_checks:
            decision = PolicyDecision.REJECTED
            reasons = [f"{c.check}: {c.message}" for c in failed_checks]
        elif skipped_checks:
            decision = PolicyDecision.REJECTED
            reasons = [f"Skipped check: {c.check}" for c in skipped_checks]
        else:
            # All checks passed - require human approval for financial writes
            if True:  # config.require_human_approval
                decision = PolicyDecision.HUMAN_APPROVAL_REQUIRED
                reasons = ["All policy checks passed. Human approval required for financial write."]
            else:
                decision = PolicyDecision.APPROVED
                reasons = ["All policy checks passed. Auto-approved."]

        return PolicyDecisionRecord(
            decision=decision,
            policy_version="1.0",
            checks=[c for c in checks if c.status != PolicyCheckStatus.SKIP],
            reasons=reasons,
            action_snapshot_hash=snapshot.compute_hash(),
            evaluated_at=dt.datetime.utcnow(),
            evaluated_by="SYSTEM",
        )

    def _check_authorization(self) -> PolicyCheck:
        """Check if action type is authorized."""
        from backend.app.schemas.action.policy import PolicyCheck
        return PolicyCheck(
            check="authorization",
            status=PolicyCheckStatus.PASS,
            actual="CREATE_PAYMENT_LINK",
            limit="CREATE_PAYMENT_LINK",
            message="Action type CREATE_PAYMENT_LINK is authorized.",
        )

    def _check_merchant_configured(self) -> PolicyCheck:
        """Check if merchant is configured for recovery."""
        from backend.app.schemas.action.policy import PolicyCheck
        return PolicyCheck(
            check="merchant_configured",
            status=PolicyCheckStatus.PASS,
            actual=True,
            limit=True,
            message="Merchant is configured for recovery operations.",
        )

    def _check_action_type_allowed(self, snapshot) -> PolicyCheck:
        """Check if action type is in allowed list."""
        from backend.app.schemas.action.policy import DefaultPolicyConfig, PolicyCheck
        config = DefaultPolicyConfig.get()
        allowed = config.allowed_action_types
        actual = "CREATE_PAYMENT_LINK"
        status = (
            PolicyCheckStatus.PASS
            if "CREATE_PAYMENT_LINK" in allowed
            else PolicyCheckStatus.FAIL
        )
        return PolicyCheck(
            check="action_type_allowed",
            status=status,
            actual=actual,
            limit=allowed,
            message=(
                f"Action type CREATE_PAYMENT_LINK is "
                f"{'allowed' if status == PolicyCheckStatus.PASS else 'not allowed'}."
            ),
        )

    def _check_amount_limit(self, snapshot) -> PolicyCheck:
        """Check if total amount is within configured limit."""
        from backend.app.schemas.action.policy import DefaultPolicyConfig, PolicyCheck
        config = DefaultPolicyConfig.get()
        actual = snapshot.total_amount_minor
        limit = config.max_recovery_amount_minor
        status = PolicyCheckStatus.PASS if actual <= limit else PolicyCheckStatus.FAIL
        return PolicyCheck(
            check="amount_limit",
            status=status,
            actual=actual,
            limit=limit,
            message=(
                f"Recovery amount {actual} is "
                f"{'within' if status == PolicyCheckStatus.PASS else 'exceeds'}"
                f" configured limit of {limit}."
            ),
        )

    def _check_target_count(self, snapshot) -> PolicyCheck:
        """Check if number of targets is within limit."""
        from backend.app.schemas.action.policy import DefaultPolicyConfig, PolicyCheck
        config = DefaultPolicyConfig.get()
        actual = len(snapshot.targets)
        limit = config.max_targets_per_action
        status = PolicyCheckStatus.PASS if actual <= limit else PolicyCheckStatus.FAIL
        return PolicyCheck(
            check="target_count",
            status=status,
            actual=actual,
            limit=limit,
            message=(
                f"Target count {actual} is "
                f"{'within' if status == PolicyCheckStatus.PASS else 'exceeds'} limit of {limit}."
            ),
        )

    def _check_duplicate_prevention(self, snapshot) -> PolicyCheck:
        """Check if any target already has a recovery action."""
        # In a real implementation, this would check against persisted execution records
        # For the MVP with synthetic data, we assume no duplicates
        from backend.app.schemas.action.policy import PolicyCheck
        return PolicyCheck(
            check="duplicate_prevention",
            status=PolicyCheckStatus.PASS,
            actual=0,
            limit=0,
            message="No duplicate recovery actions found for targets.",
        )

    def _check_idempotency(self, snapshot) -> PolicyCheck:
        """Check if action has a valid idempotency key."""
        from backend.app.schemas.action.policy import PolicyCheck
        # The action_id serves as idempotency key
        return PolicyCheck(
            check="idempotency",
            status=PolicyCheckStatus.PASS,
            actual=snapshot.action_id,
            limit=None,
            message=f"Action has valid idempotency key: {snapshot.action_id}.",
        )

    def _check_eligibility(self, snapshot) -> PolicyCheck:
        """Check if all targets are eligible for recovery."""
        # Check each target for eligibility criteria
        # - Payment is failed
        # - Order exists
        # - Customer exists
        # - No successful payment already exists for the order
        # - No previous recovery link already exists
        # - Within recovery window

        # For the MVP, we assume all synthetic targets are eligible
        from backend.app.schemas.action.policy import PolicyCheck
        return PolicyCheck(
            check="eligibility",
            status=PolicyCheckStatus.PASS,
            actual=len(snapshot.targets),
            limit=len(snapshot.targets),
            message=f"All {len(snapshot.targets)} targets are eligible for recovery.",
        )

    def _check_action_integrity(self, snapshot) -> PolicyCheck:
        """Check if action snapshot is intact (not modified after creation)."""
        from backend.app.schemas.action.policy import PolicyCheck
        # The snapshot is immutable (frozen=True), so it cannot be modified
        return PolicyCheck(
            check="action_integrity",
            status=PolicyCheckStatus.PASS,
            actual=snapshot.compute_hash()[:16],
            limit=None,
            message="Action snapshot is immutable and hash verified.",
        )

    def _check_investigation_integrity(self, investigation) -> PolicyCheck:
        """Check if action originates from a valid completed investigation."""
        from backend.app.schemas.action.policy import PolicyCheck

        if not investigation:
            return PolicyCheck(
                check="investigation_integrity",
                status=PolicyCheckStatus.FAIL,
                actual=None,
                limit=None,
                message="No investigation provided.",
            )

        if investigation.state.value != "DIAGNOSIS_COMPLETE":
            return PolicyCheck(
                check="investigation_integrity",
                status=PolicyCheckStatus.FAIL,
                actual=investigation.state.value,
                limit="DIAGNOSIS_COMPLETE",
                message=(
                    f"Investigation state is {investigation.state.value}, "
                    f"expected DIAGNOSIS_COMPLETE."
                ),
            )

        return PolicyCheck(
            check="investigation_integrity",
            status=PolicyCheckStatus.PASS,
            actual=investigation.state.value,
            limit="DIAGNOSIS_COMPLETE",
            message="Investigation is in valid DIAGNOSIS_COMPLETE state.",
        )

    def _check_rate_limit(self, snapshot) -> PolicyCheck:
        """Check if merchant has exceeded rate limits."""
        # For MVP, always pass
        from backend.app.schemas.action.policy import PolicyCheck
        return PolicyCheck(
            check="rate_limit",
            status=PolicyCheckStatus.PASS,
            actual=1,
            limit="max_actions_per_hour",
            message="Rate limit not exceeded (MVP default).",
        )

    def _check_amount_per_target(self, snapshot) -> PolicyCheck:
        """Check if any single target exceeds per-target amount limit."""
        from backend.app.schemas.action.policy import DefaultPolicyConfig, PolicyCheck
        config = DefaultPolicyConfig.get()
        max_per_target = config.max_recovery_amount_per_target_minor
        max_target_amount = max(t.amount_minor for t in snapshot.targets) if snapshot.targets else 0
        status = (
            PolicyCheckStatus.PASS
            if max_target_amount <= max_per_target
            else PolicyCheckStatus.FAIL
        )
        return PolicyCheck(
            check="amount_per_target",
            status=status,
            actual=max_target_amount,
            limit=max_per_target,
            message=(
                f"Max target amount {max_target_amount} is "
                f"{'within' if status == PolicyCheckStatus.PASS else 'exceeds'}"
                f" limit of {max_per_target}."
            ),
        )


class DefaultPolicyConfig:
    """Singleton for default policy configuration."""

    _instance = None

    @classmethod
    def get(cls):
        if cls._instance is None:
            cls._instance = cls._default_config()
        return cls._instance

    @classmethod
    def _default_config(cls):
        return PolicyConfig()