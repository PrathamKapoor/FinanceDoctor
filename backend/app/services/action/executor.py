"""Action executor - executes approved actions via Razorpay adapter.

The executor is the deterministic bridge between a human-approved
``ProposedAction`` and a verified provider write. It also serves as the
*execution-to-outcome boundary* for Stage 5: when execution succeeds,
the executor hands the per-target adapter results to an injected
:class:`OutcomeInitializer`, which deterministically creates the matching
``InterventionOutcome`` + ``RecoveryTargetOutcome`` records. No LLM call
is involved in the initialization; the outcome layer is left in the
``PENDING`` state waiting on provider webhooks.
"""

from __future__ import annotations

import datetime as dt
import hashlib
from typing import Any

from backend.app.adapters.razorpay.factory import create_razorpay_adapter
from backend.app.schemas.action.execution import ActionExecution, ExecutionStatus


class ExecutionError(Exception):
    """Action execution error."""

    pass


class ActionExecutor:
    """Executes approved actions via the Razorpay adapter."""

    def __init__(
        self,
        model_client=None,
        outcome_initializer=None,
        world=None,
        adapter=None,
    ) -> None:
        self._adapter = adapter
        self._model_client = model_client
        self._executions: dict[str, Any] = {}
        self._outcome_initializer = outcome_initializer
        # Track the per-target adapter results of the most recent
        # execution for each execution_id. The outcome initializer
        # consumes this information via the per-target manifest it
        # builds in :meth:`execute`.
        self._last_execution_links: dict[str, list[Any]] = {}
        # Optional MerchantWorld for stub mode; the factory needs it.
        self._world = world

    async def _get_adapter(self):
        if self._adapter is None:
            self._adapter = await create_razorpay_adapter(self._world)
        return self._adapter

    async def execute(self, action, approval, idempotency_key: str | None = None) -> Any:
        """Execute an approved action against the Razorpay adapter.

        On success the executor delegates to the injected
        ``OutcomeInitializer`` to deterministically build the matching
        ``InterventionOutcome`` + ``RecoveryTargetOutcome`` records.
        This is the *execution-to-outcome boundary*: after this call
        returns, the outcome layer is in ``PENDING`` waiting on
        provider webhooks.
        """
        # Validate preconditions
        self._validate_execution(action, approval)
        execution = self._create_execution_record(action, approval, idempotency_key)
        try:
            execution.mark_executing()

            # Get adapter
            adapter = await self._get_adapter()

            # Execute based on action type
            if action.action_type.value == "CREATE_PAYMENT_LINK":
                links = await self._execute_create_payment_link(adapter, action)
            else:
                raise ValueError(f"Unsupported action type: {action.action_type}")

            if not links:
                raise ExecutionError("Adapter returned no payment links")

            primary_ref = links[0].provider_id

            # Mark success using the primary link as the canonical
            # provider reference. The full set of links is preserved
            # for the outcome layer below.
            execution.mark_succeeded(
                provider_ref=primary_ref,
                provider_response={
                    "links": [
                        {
                            "provider_id": link.provider_id,
                            "amount_minor": link.amount_minor,
                            "reference_id": link.reference_id,
                        }
                        for link in links
                    ]
                },
            )

            # Store execution record
            self._executions[execution.execution_id] = execution
            self._last_execution_links[execution.execution_id] = links

            # Hand the per-target results to the outcome layer.
            if self._outcome_initializer is not None:
                targets_with_links: list[dict[str, Any]] = []
                for action_target, link in zip(action.targets, links, strict=False):
                    targets_with_links.append(
                        {
                            "payment_id": action_target.payment_id,
                            "order_id": action_target.order_id,
                            "customer_id": action_target.customer_id,
                            "payment_method": action_target.payment_method,
                            "failure_reason": action_target.failure_reason,
                            "amount_minor": action_target.amount_minor,
                            "currency": action_target.currency,
                            "payment_link_id": getattr(link, "provider_id", None),
                            "provider_reference": getattr(link, "reference_id", None),
                        }
                    )
                self._outcome_initializer.initialize_outcome_for_execution(
                    action=action,
                    approval=approval,
                    execution=execution,
                    targets_with_links=targets_with_links,
                )

            return execution

        except Exception as e:
            execution.mark_failed(
                error_code=type(e).__name__,
                error_message=str(e),
                provider_response={},
            )
            self._executions[execution.execution_id] = execution
            raise ExecutionError(f"Execution failed: {e}") from e

    def _validate_execution(self, action, approval) -> None:
        """Validate preconditions for execution."""
        # Check approval status
        if not approval:
            raise ValueError("No approval provided")

        if approval.status != "APPROVED":
            raise ValueError(f"Approval status is {approval.status}, not APPROVED")

        if approval.is_expired:
            raise ValueError("Approval has expired")

        # Verify action matches approval
        if approval.action_id != action.action_id:
            raise ValueError("Approval action_id does not match action")

        # Verify action hasn't been modified (snapshot hash)
        if hasattr(action, "compute_hash"):
            if action.compute_hash() != approval.action_snapshot_hash:
                raise ValueError("Action has been modified after approval")

    def _create_execution_record(self, action, approval, idempotency_key: str | None) -> Any:
        """Create an execution record."""
        # Generate deterministic idempotency key if not provided
        if idempotency_key is None:
            key_data = f"{action.action_id}:{approval.approval_id}"
            idempotency_key = hashlib.sha256(key_data.encode()).hexdigest()[:32]

        execution = ActionExecution(
            action_id=action.action_id,
            approval_id=approval.approval_id,
            status=ExecutionStatus.PENDING,
            provider="razorpay",
            provider_operation="create_payment_link",
            idempotency_key=idempotency_key,
        )

        return execution

    async def _execute_create_payment_link(self, adapter, action) -> list[Any]:
        """Execute CREATE_PAYMENT_LINK via Razorpay adapter.

        Returns one ``NormalizedPaymentLink`` per target so the outcome
        layer can track each target individually.
        """
        results: list[Any] = []

        for target in action.targets:
            link = await adapter.create_payment_link(
                amount_minor=target.amount_minor,
                currency=target.currency,
                reference_id=f"{action.action_id}_{target.payment_id}",
                description=f"Recovery for failed payment {target.payment_id}",
                customer_name=None,
                customer_email=None,
                customer_phone=None,
                expire_by=int(
                    (
                        dt.datetime.utcnow() + dt.timedelta(hours=24)
                    ).timestamp()
                ),
                notify_sms=True,
                notify_email=True,
                reminder_enable=True,
            )
            results.append(link)

        return results

    def get_execution(self, execution_id: str) -> Any | None:
        """Get an execution record by ID."""
        return self._executions.get(execution_id)

    def get_executions_for_action(self, action_id: str) -> list:
        """Get all executions for an action."""
        return [e for e in self._executions.values() if e.action_id == action_id]