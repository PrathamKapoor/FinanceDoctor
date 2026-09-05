"""Investigation API endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from backend.app.agents.orchestrator import run_investigation
from backend.app.agents.traceability import get_trace_store
from backend.app.db.database import get_session
from backend.app.services.incident_generator import IncidentConfig, inject_incident
from backend.app.services.synthetic_data import SyntheticMerchantConfig, generate_merchant_world

router = APIRouter(prefix="/investigations", tags=["investigations"])


class InvestigationCreateRequest(BaseModel):
    incident_type: str = Field(default="PAYMENT_METHOD_FAILURE_SPIKE")
    seed: int | None = None
    num_orders: int | None = None
    num_customers: int | None = None


class InvestigationResponse(BaseModel):
    investigation_id: str
    incident_type: str
    state: str
    anomaly_detected: bool
    anomaly_score: float | None
    diagnosis_id: str | None
    created_at: str
    completed_at: str | None


class DiagnosisResponse(BaseModel):
    diagnosis_id: str
    incident_type: str
    leading_hypothesis: str
    confidence: float
    summary: str
    recommended_action_type: str
    action_rationale: str
    alternative_hypotheses: list[dict]


@router.post("", response_model=InvestigationResponse, status_code=201)
async def create_investigation(
    request: Request,
    payload: InvestigationCreateRequest,
    session=Depends(get_session),
) -> InvestigationResponse:
    """Create and run a new investigation."""

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

    # Get model client
    model_client = None  # Will use factory default (stub)

    # Run investigation
    investigation = await run_investigation(world, payload.incident_type, model_client=model_client)

    return InvestigationResponse(
        investigation_id=investigation.investigation_id,
        incident_type=investigation.incident_type,
        state=investigation.state.value,
        anomaly_detected=investigation.anomaly_detected,
        anomaly_score=investigation.anomaly_score,
        diagnosis_id=investigation.diagnosis_ref,
        created_at=investigation.created_at.isoformat(),
        completed_at=investigation.completed_at.isoformat() if investigation.completed_at else None,
    )


@router.get("/{investigation_id}", response_model=InvestigationResponse)
async def get_investigation(investigation_id: str) -> InvestigationResponse:
    """Get investigation status (stub - would query DB in production)."""
    # In a real implementation, this would query the database
    raise HTTPException(status_code=404, detail="Investigation not found - not yet persisted")


@router.get("/{investigation_id}/diagnosis", response_model=DiagnosisResponse)
async def get_diagnosis(investigation_id: str) -> DiagnosisResponse:
    """Get diagnosis for an investigation (stub)."""
    raise HTTPException(status_code=404, detail="Diagnosis not found - not yet persisted")


@router.get("/{investigation_id}/traces")
async def get_investigation_traces(investigation_id: str) -> dict[str, Any]:
    """Get model call traces for an investigation."""
    trace_store = get_trace_store()
    traces = trace_store.get_by_investigation(investigation_id)
    return {
        "investigation_id": investigation_id,
        "traces": [t.model_dump() for t in traces],
    }


@router.get("/traces")
async def get_all_traces() -> dict[str, Any]:
    """Get all model call traces."""
    trace_store = get_trace_store()
    # Access internal store
    all_traces = list(trace_store._traces.values())
    return {
        "count": len(all_traces),
        "traces": [t.model_dump() for t in all_traces],
    }