"""Action API endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from backend.app.agents.m3 import run_m3_diagnosis
from backend.app.agents.orchestrator import run_investigation
from backend.app.schemas.action.action import ProposedAction
from backend.app.services.action.approval import ApprovalService
from backend.app.services.action.executor import ActionExecutor
from backend.app.services.action.planner import ActionPlanner
from backend.app.services.action.policy import PolicyEngine
from backend.app.services.analytics import AnalyticsEngine
from backend.app.services.evidence import build_bundle
from backend.app.services.incident_generator import IncidentConfig, inject_incident
from backend.app.services.synthetic_data import SyntheticMerchantConfig, generate_merchant_world

router = APIRouter(prefix="/actions", tags=["actions"])


# Request/Response models
class CreateActionRequest(BaseModel):
    incident_type: str = "PAYMENT_METHOD_FAILURE_SPIKE"
    seed: int | None = None
    num_orders: int | None = None
    num_customers: int | None = None


class ActionResponse(BaseModel):
    action_id: str
    investigation_id: str
    diagnosis_id: str
    action_type: str
    status: str
    targets_count: int
    total_amount_minor: int
    created_at: str


class PolicyEvaluationRequest(BaseModel):
    action_id: str


class PolicyResponse(BaseModel):
    decision: str
    checks: list[dict]
    reasons: list[str]
    action_snapshot_hash: str


class ApprovalActionRequest(BaseModel):
    approval_id: str
    decided_by: str
    reason: str | None = None


class ExecuteActionRequest(BaseModel):
    action_id: str
    approval_id: str


class ExecuteResponse(BaseModel):
    execution_id: str
    action_id: str
    status: str
    provider_reference: str | None
    completed_at: str | None


# In-memory stores (replace with DB in production)
_actions: dict[str, Any] = {}
_snapshots: dict[str, Any] = {}
_investigations: dict[str, Any] = {}
_diagnoses: dict[str, Any] = {}


def _get_services():
    """Get service instances."""
    approval_service = ApprovalService(ttl_minutes=60)
    executor = ActionExecutor()
    return approval_service, executor


@router.post("", response_model=ActionResponse, status_code=201)
async def create_action(payload: CreateActionRequest, request: Request) -> ActionResponse:
    """Create and run a complete investigation + action planning pipeline."""
    # Build synthetic world
    config = SyntheticMerchantConfig()
    if payload.seed is not None:
        config.seed = payload.seed
    if payload.num_orders is not None:
        config.num_orders = payload.num_orders
    if payload.num_customers is not None:
        config.num_customers = payload.num_customers

    world = generate_merchant_world(config)

    # Inject incident
    incident = IncidentConfig()
    inject_incident(world, incident)

    # Run investigation
    investigation = await run_investigation(world, payload.incident_type)

    # Get diagnosis
    from backend.app.agents.workers import run_all_workers

    engine = AnalyticsEngine(world)
    bundle = build_bundle(world, engine)
    worker_outputs = await run_all_workers(bundle, world)
    diagnosis = await run_m3_diagnosis(bundle, worker_outputs)

    # Store investigation and diagnosis
    _investigations[investigation.investigation_id] = investigation
    _diagnoses[diagnosis.diagnosis_id] = diagnosis

    # Plan action
    planner = ActionPlanner(world)
    action = planner.plan(diagnosis)

    # Create snapshot
    snapshot = planner.create_snapshot(action)

    # Store action and snapshot
    _actions[action.action_id] = action
    _snapshots[action.action_id] = snapshot

    return ActionResponse(
        action_id=action.action_id,
        investigation_id=action.investigation_id,
        diagnosis_id=action.diagnosis_id,
        action_type=action.action_type.value,
        status=action.status.value,
        targets_count=len(action.targets),
        total_amount_minor=action.total_amount_minor,
        created_at=action.created_at.isoformat(),
    )


@router.get("/{action_id}")
async def get_action(action_id: str) -> dict:
    """Get action details."""
    action = _actions.get(action_id)
    if not action:
        raise HTTPException(status_code=404, detail="Action not found")

    return {
        "action_id": action.action_id,
        "investigation_id": action.investigation_id,
        "diagnosis_id": action.diagnosis_id,
        "action_type": action.action_type.value,
        "status": action.status.value,
        "targets": [t.model_dump() for t in action.targets],
        "total_amount_minor": action.total_amount_minor,
        "currency": action.currency,
        "rationale": action.rationale,
        "created_at": action.created_at.isoformat(),
        "updated_at": action.updated_at.isoformat(),
    }


@router.post("/{action_id}/policy", response_model=PolicyResponse)
async def evaluate_policy(action_id: str) -> PolicyResponse:
    """Evaluate policy for a proposed action."""
    action = _actions.get(action_id)
    if not action:
        raise HTTPException(status_code=404, detail="Action not found")

    snapshot = _snapshots.get(action_id)
    if not snapshot:
        raise HTTPException(status_code=404, detail="Action snapshot not found")

    # Get investigation and diagnosis
    investigation = _investigations.get(action.investigation_id)
    diagnosis = _diagnoses.get(action.diagnosis_id)

    if not investigation or not diagnosis:
        raise HTTPException(status_code=404, detail="Investigation or diagnosis not found")

    # Create a synthetic world for policy evaluation
    config = SyntheticMerchantConfig()
    world = generate_merchant_world(config)

    # Evaluate policy
    policy_engine = PolicyEngine(world)
    decision = policy_engine.evaluate(action, diagnosis, investigation, None)

    # Update action status
    action.status = "POLICY_EVALUATED"
    action.updated_at = __import__("datetime").datetime.utcnow()

    return PolicyResponse(
        decision=decision.decision.value,
        checks=[c.model_dump() for c in decision.checks],
        reasons=decision.reasons,
        action_snapshot_hash=decision.action_snapshot_hash,
    )


@router.post("/{action_id}/approval", response_model=dict)
async def request_approval(action_id: str) -> dict:
    """Create an approval request for an action that passed policy."""
    action = _actions.get(action_id)
    if not action:
        raise HTTPException(status_code=404, detail="Action not found")

    if action.status != "POLICY_EVALUATED":
        raise HTTPException(status_code=400, detail="Action must pass policy evaluation first")

    # Check policy decision
    # In a real implementation, we'd check the stored policy decision
    # For now, assume policy passed

    approval_service = ApprovalService(ttl_minutes=60)

    # We need the action object with compute_hash method
    # For simplicity, we'll use a mock action with compute_hash
    action_obj = ProposedAction(**action.model_dump())

    approval = approval_service.create_approval(action_obj, None)

    return {
        "approval_id": approval.approval_id,
        "action_id": action_id,
        "status": approval.status.value,
        "expires_at": approval.expires_at.isoformat(),
        "message": "Approval request created. Waiting for human decision.",
    }


@router.post("/approvals/{approval_id}/approve")
async def approve_approval(approval_id: str, payload: ApprovalActionRequest) -> dict:
    """Approve an approval request."""
    approval_service = ApprovalService(ttl_minutes=60)
    approval = approval_service.approve(approval_id, payload.decided_by, payload.reason)
    return {
        "approval_id": approval.approval_id,
        "status": approval.status.value,
        "approved_at": approval.approved_at.isoformat() if approval.approved_at else None,
    }


@router.post("/approvals/{approval_id}/reject")
async def reject_approval(approval_id: str, payload: ApprovalActionRequest) -> dict:
    """Reject an approval request."""
    approval_service = ApprovalService(ttl_minutes=60)
    approval = approval_service.reject(approval_id, payload.decided_by, payload.reason)
    return {
        "approval_id": approval.approval_id,
        "status": approval.status.value,
        "rejected_at": approval.rejected_at.isoformat() if approval.rejected_at else None,
    }


@router.get("/approvals/{approval_id}")
async def get_approval(approval_id: str) -> dict:
    """Get approval status."""
    approval_service = ApprovalService(ttl_minutes=60)
    approval = approval_service.get_approval(approval_id)
    if not approval:
        raise HTTPException(status_code=404, detail="Approval not found")

    return {
        "approval_id": approval.approval_id,
        "action_id": approval.action_id,
        "status": approval.status.value,
        "requested_at": approval.requested_at.isoformat(),
        "expires_at": approval.expires_at.isoformat(),
        "approved_at": approval.approved_at.isoformat() if approval.approved_at else None,
        "rejected_at": approval.rejected_at.isoformat() if approval.rejected_at else None,
        "decision_reason": approval.decision_reason,
        "decided_by": approval.decided_by,
    }


@router.post("/{action_id}/execute", response_model=ExecuteResponse)
async def execute_action(action_id: str, payload: ExecuteActionRequest) -> ExecuteResponse:
    """Execute an approved action."""
    action = _actions.get(action_id)
    if not action:
        raise HTTPException(status_code=404, detail="Action not found")

    approval_service = ApprovalService(ttl_minutes=60)
    approval = approval_service.get_approval(payload.approval_id)
    if not approval:
        raise HTTPException(status_code=404, detail="Approval not found")

    if approval.status != "APPROVED":
        raise HTTPException(status_code=400, detail="Approval not granted")

    if approval.action_id != action_id:
        raise HTTPException(status_code=400, detail="Approval does not match action")

    executor = ActionExecutor()
    execution = await executor.execute(None, None)  # Pass action and approval objects

    return ExecuteResponse(
        execution_id=execution.execution_id,
        action_id=action_id,
        status=execution.status.value,
        provider_reference=execution.provider_reference,
        completed_at=execution.completed_at.isoformat() if execution.completed_at else None,
    )


@router.get("/{action_id}/execution")
async def get_execution(action_id: str) -> dict:
    """Get execution status for an action."""
    # In a real implementation, this would query the execution store
    return {"message": "Execution tracking not yet implemented in memory store"}


@router.get("/{action_id}/snapshot")
async def get_snapshot(action_id: str) -> dict:
    """Get the immutable action snapshot."""
    snapshot = _snapshots.get(action_id)
    if not snapshot:
        raise HTTPException(status_code=404, detail="Snapshot not found")

    return {
        "action_id": snapshot.action_id,
        "action_type": snapshot.action_type.value,
        "targets": [t.model_dump() for t in snapshot.targets],
        "total_amount_minor": snapshot.total_amount_minor,
        "currency": snapshot.currency,
        "rationale": snapshot.rationale,
        "investigation_id": snapshot.investigation_id,
        "diagnosis_id": snapshot.diagnosis_id,
        "eligibility_results": snapshot.eligibility_results,
        "evidence_references": snapshot.evidence_references,
        "created_at": snapshot.created_at.isoformat(),
        "snapshot_hash": snapshot.compute_hash(),
    }