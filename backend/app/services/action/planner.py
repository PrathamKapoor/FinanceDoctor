"""Action planner - converts M3 diagnosis into a structured proposed action."""

from __future__ import annotations

from backend.app.schemas.action.action import (
    ActionSnapshot,
    ActionTarget,
    ProposedAction,
)
from backend.app.services.synthetic_data import MerchantWorld


class PlannerError(Exception):
    """Action planner error."""
    pass


class ActionPlanner:
    """Converts M3 diagnosis into a structured ProposedAction."""

    def __init__(self, world: MerchantWorld):
        self._world = world

    def plan(self, diagnosis, investigation_id: str | None = None) -> ProposedAction:
        """Create a ProposedAction from an M3 diagnosis."""
        # Validate diagnosis
        self._validate_diagnosis(diagnosis)

        # Determine eligible targets from the world
        targets = self._select_targets(diagnosis)

        if not targets:
            raise PlannerError("No eligible targets found for recovery")
        # Calculate total amount
        sum(t.amount_minor for t in targets)

        # Build action
        from backend.app.schemas.action.action import ActionStatus, ActionType
        action = ProposedAction(
            investigation_id=(
                investigation_id
                if investigation_id is not None
                else getattr(diagnosis, "investigation_id", "unknown")
            ),
            diagnosis_id=diagnosis.diagnosis_id,
            action_type=ActionType(diagnosis.recommended_action_type),
            targets=targets,
            total_amount_minor=sum(t.amount_minor for t in targets),
            currency=targets[0].currency if targets else "INR",
            status=ActionStatus.PLANNED,
            rationale=diagnosis.action_rationale,
        )
        return action

    def _validate_diagnosis(self, diagnosis) -> None:
        """Validate that the diagnosis supports action planning."""
        if not hasattr(diagnosis, "recommended_action_type"):
            raise PlannerError("Diagnosis missing recommended_action_type")

        if not hasattr(diagnosis, "action_rationale") or not diagnosis.action_rationale:
            raise PlannerError("Diagnosis missing action_rationale")

        if not hasattr(diagnosis, "diagnosis_id"):
            raise PlannerError("Diagnosis missing diagnosis_id")

    def _select_targets(self, diagnosis) -> list:
        # For the MVP, we select all failed payments from the incident window
        # that match the affected method from the diagnosis
        max_targets = 100  # align with PolicyEngine max_targets_per_action

        affected_method = None
        if hasattr(diagnosis, "leading_hypothesis"):
            if ("UPI" in diagnosis.leading_hypothesis or
                    "PAYMENT_METHOD_DEGRADATION" in diagnosis.leading_hypothesis):
                affected_method = "UPI"

        # Get all failed payments from the incident window
        eligible = []
        for payment in self._world.payments:
            if payment.status.value != "FAILED":
                continue

            # Check if payment is in incident window (if incident exists)
            if affected_method and payment.method.value != affected_method:
                continue
            order = next((o for o in self._world.orders if o.id == payment.order_id), None)
            if not order:
                continue

            customer = next((c for c in self._world.customers if c.id == order.customer_id), None)
            if not customer:
                continue

            target = ActionTarget(
                payment_id=payment.razorpay_payment_id,
                order_id=order.razorpay_order_id,
                customer_id=customer.razorpay_customer_id,
                amount_minor=payment.amount_minor,
                currency=payment.currency,
                payment_method=payment.method.value,
                failure_reason=payment.error_code or "UNKNOWN",
            )
            eligible.append(target)
            if len(eligible) >= max_targets:
                break

        return eligible
    def create_snapshot(self, action) -> ActionSnapshot:
        """Create an immutable snapshot of the action for policy evaluation."""
        from backend.app.schemas.action.action import ActionSnapshot

        return ActionSnapshot(
            action_id=action.action_id,
            action_type=action.action_type,
            targets=action.targets,
            total_amount_minor=action.total_amount_minor,
            currency=action.currency,
            rationale=action.rationale,
            investigation_id=action.investigation_id,
            diagnosis_id=action.diagnosis_id,
            eligibility_results={},  # Will be populated by policy engine
            evidence_references=[],  # Will be populated by policy engine
        )