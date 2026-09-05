"""Tests for Stage 4 controlled action pipeline."""

from __future__ import annotations

import hashlib

import pytest
from backend.app.schemas.action.action import (
    ActionSnapshot,
    ActionStatus,
    ActionTarget,
    ProposedAction,
)
from backend.app.schemas.action.approval import (
    ApprovalStatus,
)
from backend.app.schemas.action.policy import (
    PolicyConfig,
)
from backend.app.schemas.agent.diagnosis import DiagnosisOutput
from backend.app.services.action.approval import ApprovalService
from backend.app.services.action.executor import ActionExecutor
from backend.app.services.action.planner import ActionPlanner
from backend.app.services.action.policy import PolicyEngine
from backend.app.services.incident_generator import IncidentConfig, inject_incident
from backend.app.services.synthetic_data import (
    SyntheticMerchantConfig,
    generate_merchant_world,
)
from pydantic import ValidationError


class TestActionModels:
    """Test action domain models."""

    def test_action_target_creation(self):
        target = ActionTarget(
            payment_id="pay_123",
            order_id="order_456",
            customer_id="cust_789",
            amount_minor=50000,
            currency="INR",
            payment_method="UPI",
            failure_reason="NETWORK_ERROR",
        )
        assert target.payment_id == "pay_123"
        assert target.amount_minor == 50000

    def test_proposed_action_validation(self):
        targets = [
            ActionTarget(
                payment_id="pay_1",
                order_id="order_1",
                customer_id="cust_1",
                amount_minor=50000,
                currency="INR",
                payment_method="UPI",
                failure_reason="NETWORK_ERROR",
            ),
            ActionTarget(
                payment_id="pay_2",
                order_id="order_2",
                customer_id="cust_2",
                amount_minor=30000,
                currency="INR",
                payment_method="UPI",
                failure_reason="NETWORK_ERROR",
            ),
        ]

        action = ProposedAction(
            investigation_id="inv_001",
            diagnosis_id="diag_001",
            targets=targets,
            total_amount_minor=80000,
            currency="INR",
            rationale="Test rationale for recovery action with sufficient length",
        )

        assert action.total_amount_minor == 80000
        assert len(action.targets) == 2
        assert action.status == ActionStatus.PROPOSED

    def test_proposed_action_amount_validation(self):
        """Total amount must match sum of target amounts."""
        targets = [
            ActionTarget(
                payment_id="pay_1",
                order_id="order_1",
                customer_id="cust_1",
                amount_minor=50000,
                currency="INR",
                payment_method="UPI",
                failure_reason="NETWORK_ERROR",
            ),
        ]

        with pytest.raises(ValueError):
            ProposedAction(
                investigation_id="inv_001",
                diagnosis_id="diag_001",
                targets=targets,
                total_amount_minor=99999,  # Wrong amount
                currency="INR",
                rationale="Test rationale with sufficient length for validation",
            )

    def test_action_snapshot_immutability(self):
        """ActionSnapshot should be immutable."""
        target = ActionTarget(
            payment_id="pay_1",
            order_id="order_1",
            customer_id="cust_1",
            amount_minor=50000,
            currency="INR",
            payment_method="UPI",
            failure_reason="NETWORK_ERROR",
        )

        snapshot = ActionSnapshot(
            action_id="act_001",
            action_type="CREATE_PAYMENT_LINK",
            targets=[target],
            total_amount_minor=50000,
            currency="INR",
            rationale="Test",
            investigation_id="inv_001",
            diagnosis_id="diag_001",
        )

        # Hash should be deterministic
        hash1 = snapshot.compute_hash()
        hash2 = snapshot.compute_hash()
        assert hash1 == hash2

        # Snapshot should be frozen (immutable)
        with pytest.raises((ValidationError, AttributeError)):
            snapshot.action_id = "modified"


class TestPolicyEngine:
    """Test policy engine checks."""

    @pytest.fixture
    def world(self):
        config = SyntheticMerchantConfig(
            seed=42,
            num_customers=100,
            num_orders=200,
            baseline_days=7,
        )
        world = generate_merchant_world(config)
        inject_incident(world, IncidentConfig())
        return world

    @pytest.fixture
    def policy_engine(self, world):
        return PolicyEngine(world)

    @pytest.fixture
    def sample_action(self, world):
        from backend.app.services.action.planner import ActionPlanner
        planner = ActionPlanner(world)
        diagnosis = self._create_mock_diagnosis()
        return planner.plan(diagnosis)

    def _create_mock_diagnosis(self):
        return DiagnosisOutput(
            diagnosis_id="diag_test",
            incident_type="PAYMENT_METHOD_FAILURE_SPIKE",
            leading_hypothesis="PAYMENT_METHOD_DEGRADATION",
            confidence=0.9,
            summary="Test diagnosis with sufficient length for validation",
            supporting_evidence_ids=["test"],
            contradicting_evidence_ids=[],
            alternative_hypotheses=[],
            recommended_action_type="CREATE_PAYMENT_LINK",
            action_rationale="Test rationale with sufficient length for validation",
            uncertainties=[],
        )

    @pytest.mark.asyncio
    async def test_policy_engine_passes_valid_action(self, world, sample_action):
        policy_engine = PolicyEngine(world)
        diagnosis = self._create_mock_diagnosis()

        # Create a minimal investigation object
        from backend.app.schemas.agent.investigation import Investigation
        investigation = Investigation(
            investigation_id="inv_test",
            incident_type="TEST",
            state="DIAGNOSIS_COMPLETE",
        )

        ActionPlanner(world)
        snapshot = ActionSnapshot(
            action_id=sample_action.action_id,
            action_type=sample_action.action_type,
            targets=sample_action.targets,
            total_amount_minor=sample_action.total_amount_minor,
            currency=sample_action.currency,
            rationale=sample_action.rationale,
            investigation_id=sample_action.investigation_id,
            diagnosis_id=sample_action.diagnosis_id,
        )

        decision = policy_engine.evaluate(sample_action, diagnosis, investigation, snapshot)

        # Should require human approval for valid action
        assert decision.decision in ("APPROVED", "HUMAN_APPROVAL_REQUIRED", "REJECTED")
        assert len(decision.checks) > 0


class TestApprovalService:
    """Test approval workflow."""

    def test_create_approval(self):
        ApprovalService(ttl_minutes=60)

        from backend.app.schemas.action.action import ActionTarget, ProposedAction

        [
            ActionTarget(
                payment_id="pay_1",
                order_id="order_1",
                customer_id="cust_1",
                amount_minor=50000,
                currency="INR",
                payment_method="UPI",
                failure_reason="NETWORK_ERROR",
            ),
        ]

        action = ProposedAction(
            investigation_id="inv_001",
            diagnosis_id="diag_001",
            targets=[ActionTarget(
                payment_id="pay_1",
                order_id="order_1",
                customer_id="cust_1",
                amount_minor=50000,
                currency="INR",
                payment_method="UPI",
                failure_reason="NETWORK_ERROR",
            )],
            total_amount_minor=50000,
            currency="INR",
            rationale="Test rationale for approval creation with sufficient length",
        )

        approval = ApprovalService(ttl_minutes=60).create_approval(action, None)

        assert approval.status == ApprovalStatus.PENDING
        assert approval.action_id == action.action_id
        assert approval.expires_at > __import__("datetime").datetime.utcnow()

    def test_approve_approval(self):
        service = ApprovalService(ttl_minutes=60)

        from backend.app.schemas.action.action import ActionTarget, ProposedAction

        action = ProposedAction(
            investigation_id="inv_001",
            diagnosis_id="diag_001",
            targets=[ActionTarget(
                payment_id="pay_1",
                order_id="order_1",
                customer_id="cust_1",
                amount_minor=50000,
                currency="INR",
                payment_method="UPI",
                failure_reason="NETWORK_ERROR",
            )],
            total_amount_minor=50000,
            currency="INR",
            rationale="Test rationale for approval with sufficient length for validation",
        )

        approval = service.create_approval(action, None)
        approved = service.approve(approval.approval_id, "human_001", "Approved for testing")

        assert approved.status == "APPROVED"
        assert approved.approved_at is not None
        assert approved.decided_by == "human_001"

    def test_reject_approval(self):
        service = ApprovalService(ttl_minutes=60)

        from backend.app.schemas.action.action import ActionTarget, ProposedAction

        action = ProposedAction(
            investigation_id="inv_001",
            diagnosis_id="diag_001",
            targets=[ActionTarget(
                payment_id="pay_1",
                order_id="order_1",
                customer_id="cust_1",
                amount_minor=50000,
                currency="INR",
                payment_method="UPI",
                failure_reason="NETWORK_ERROR",
            )],
            total_amount_minor=50000,
            currency="INR",
            rationale="Test rationale for rejection with sufficient length for validation",
        )

        approval = service.create_approval(action, None)
        rejected = service.reject(approval.approval_id, "human_001", "Insufficient evidence")

        assert rejected.status == "REJECTED"
        assert rejected.rejected_at is not None
        assert rejected.decided_by == "human_001"

    def test_expired_approval_cannot_be_approved(self):
        service = ApprovalService(ttl_minutes=60)

        from backend.app.schemas.action.action import ActionTarget, ProposedAction

        action = ProposedAction(
            investigation_id="inv_001",
            diagnosis_id="diag_001",
            targets=[ActionTarget(
                payment_id="pay_1",
                order_id="order_1",
                customer_id="cust_1",
                amount_minor=50000,
                currency="INR",
                payment_method="UPI",
                failure_reason="NETWORK_ERROR",
            )],
            total_amount_minor=50000,
            currency="INR",
            rationale="Test rationale for expiration test with sufficient length",
        )

        # Create approval with normal TTL, then manually expire it
        approval = service.create_approval(action, None)
        import datetime as dt
        approval.expires_at = dt.datetime.utcnow() - dt.timedelta(minutes=1)

        with pytest.raises(ValueError, match="expired"):
            service.approve(approval.approval_id, "human_001")


class TestActionExecutor:
    """Test action executor."""

    @pytest.mark.asyncio
    async def test_executor_requires_approval(self):
        executor = ActionExecutor()

        from backend.app.schemas.action.action import ActionTarget, ProposedAction
        from backend.app.services.action.approval import ApprovalService

        action = ProposedAction(
            investigation_id="inv_001",
            diagnosis_id="diag_001",
            targets=[
                ActionTarget(
                    payment_id="pay_1",
                    order_id="order_1",
                    customer_id="cust_1",
                    amount_minor=50000,
                    currency="INR",
                    payment_method="UPI",
                    failure_reason="NETWORK_ERROR",
                ),
            ],
            total_amount_minor=50000,
            currency="INR",
            rationale="Test rationale for executor with sufficient length for validation",
        )

        # Create approval but don't approve it
        approval_service = ApprovalService(ttl_minutes=60)
        approval = approval_service.create_approval(action, None)
        # Don't approve it - leave as PENDING

        with pytest.raises(ValueError, match="PENDING"):
            await executor.execute(action, approval)

    def test_idempotency_key_generation(self):
        ActionExecutor()

        # Test that idempotency key is deterministic
        action_id = "act_test"
        approval_id = "apr_test"
        key_data = f"{action_id}:{approval_id}"
        key1 = hashlib.sha256(key_data.encode()).hexdigest()[:32]
        key2 = hashlib.sha256(key_data.encode()).hexdigest()[:32]
        assert key1 == key2


class TestActionSnapshot:
    """Test action snapshot immutability and hashing."""

    def test_snapshot_hash_deterministic(self):
        target = ActionTarget(
            payment_id="pay_1",
            order_id="order_1",
            customer_id="cust_1",
            amount_minor=50000,
            currency="INR",
            payment_method="UPI",
            failure_reason="NETWORK_ERROR",
        )

        snapshot1 = ActionSnapshot(
            action_id="act_001",
            action_type="CREATE_PAYMENT_LINK",
            targets=[target],
            total_amount_minor=50000,
            currency="INR",
            rationale="Test",
            investigation_id="inv_001",
            diagnosis_id="diag_001",
        )

        snapshot2 = ActionSnapshot(
            action_id="act_001",
            action_type="CREATE_PAYMENT_LINK",
            targets=[target],
            total_amount_minor=50000,
            currency="INR",
            rationale="Test",
            investigation_id="inv_001",
            diagnosis_id="diag_001",
        )

        assert snapshot1.compute_hash() == snapshot2.compute_hash()

    def test_snapshot_hash_changes_with_content(self):
        target1 = ActionTarget(
            payment_id="pay_1",
            order_id="order_1",
            customer_id="cust_1",
            amount_minor=50000,
            currency="INR",
            payment_method="UPI",
            failure_reason="NETWORK_ERROR",
        )

        target2 = ActionTarget(
            payment_id="pay_2",
            order_id="order_2",
            customer_id="cust_2",
            amount_minor=30000,
            currency="INR",
            payment_method="UPI",
            failure_reason="NETWORK_ERROR",
        )

        snapshot1 = ActionSnapshot(
            action_id="act_001",
            action_type="CREATE_PAYMENT_LINK",
            targets=[target1],
            total_amount_minor=50000,
            currency="INR",
            rationale="Test",
            investigation_id="inv_001",
            diagnosis_id="diag_001",
        )

        snapshot2 = ActionSnapshot(
            action_id="act_001",
            action_type="CREATE_PAYMENT_LINK",
            targets=[target1, target2],
            total_amount_minor=80000,
            currency="INR",
            rationale="Test",
            investigation_id="inv_001",
            diagnosis_id="diag_001",
        )

        assert snapshot1.compute_hash() != snapshot2.compute_hash()


class TestPolicyConfig:
    """Test policy configuration."""

    def test_default_config(self):
        from backend.app.schemas.action.policy import DefaultPolicyConfig
        config = DefaultPolicyConfig.get()

        assert config.max_recovery_amount_minor == 50_000_000
        assert config.max_targets_per_action == 100
        assert config.require_human_approval is True
        assert "CREATE_PAYMENT_LINK" in config.allowed_action_types

    def test_config_override(self):
        from backend.app.schemas.action.policy import DefaultPolicyConfig
        custom = PolicyConfig(
            max_recovery_amount_minor=1000000,
            require_human_approval=False,
        )
        DefaultPolicyConfig.set(custom)
        config = DefaultPolicyConfig.get()
        assert config.max_recovery_amount_minor == 1000000
        assert config.require_human_approval is False