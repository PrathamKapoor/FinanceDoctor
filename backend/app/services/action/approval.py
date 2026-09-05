"""Human approval service for action approval workflow."""

from __future__ import annotations

from typing import Any

from backend.app.schemas.action.approval import ApprovalRequest


class ApprovalError(Exception):
    """Approval service error."""
    pass


class ApprovalService:
    """Manages human approval requests for proposed actions."""

    def __init__(self, ttl_minutes: int = 60):
        self._ttl_minutes = ttl_minutes
        self._approvals: dict[str, Any] = {}

    def create_approval(self, action, decision) -> ApprovalRequest:
        """Create an approval request for an approved action."""
        if not hasattr(action, "action_id"):
            raise ValueError("Action must have action_id")

        import datetime as dt

        approval = ApprovalRequest(
            action_id=action.action_id,
            action_snapshot_hash=action.compute_hash() if hasattr(action, "compute_hash") else "",
            expires_at=dt.datetime.utcnow() + dt.timedelta(minutes=self._ttl_minutes),
        )

        self._approvals[approval.approval_id] = approval
        return approval

    def get_approval(self, approval_id: str) -> Any | None:
        """Retrieve an approval by ID."""
        return self._approvals.get(approval_id)

    def approve(self, approval_id: str, decided_by: str, reason: str | None = None) -> Any:
        """Approve an approval request."""
        approval = self._approvals.get(approval_id)
        if not approval:
            raise ValueError(f"Approval {approval_id} not found")

        if approval.status != "PENDING":
            raise ValueError(f"Cannot approve approval in status {approval.status}")

        if approval.is_expired:
            approval.status = "EXPIRED"
            raise ValueError("Cannot approve expired approval")

        approval.approve(decided_by=decided_by, reason=reason)
        return approval

    def reject(self, approval_id: str, decided_by: str, reason: str | None = None) -> Any:
        """Reject an approval request."""
        approval = self._approvals.get(approval_id)
        if not approval:
            raise ValueError(f"Approval {approval_id} not found")

        if approval.status != "PENDING":
            raise ValueError(f"Cannot reject approval in status {approval.status}")

        approval.reject(decided_by=decided_by, reason=reason)
        return approval

    def check_expired(self) -> list:
        """Check for expired approvals and update their status."""
        expired = []
        for approval in self._approvals.values():
            if approval.status == "PENDING" and approval.is_expired:
                approval.status = "EXPIRED"
                expired.append(approval)
        return expired

    def get_approvals_for_action(self, action_id: str) -> list:
        """Get all approvals for a specific action."""
        return [a for a in self._approvals.values() if a.action_id == action_id]

    def can_execute(self, action, approval_id: str) -> bool:
        """Check if an action can be executed given an approval."""
        approval = self._approvals.get(approval_id)
        if not approval:
            return False

        if approval.action_id != action.action_id:
            return False

        if approval.status != "APPROVED":
            return False

        if approval.is_expired:
            return False

        # Verify action hasn't been modified
        # This would require the action snapshot hash
        return True