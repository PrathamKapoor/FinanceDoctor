"""Case summary API endpoint - serves a complete Financial Doctor journey
(stored as deterministic references across Stages 1-5).
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from backend.app.routers.outcome import build_case_summary_service

router = APIRouter(prefix="/cases", tags=["cases"])


class CaseSummaryResponse(BaseModel):
    case_summary_id: str
    incident_type: str | None
    investigation_id: str | None
    diagnosis_id: str | None
    action_id: str | None
    approval_id: str | None
    execution_id: str | None
    outcome_id: str | None
    symptom: str | None
    diagnosis: str | None
    prescription: str | None
    approval_status: str | None
    treatment_status: str | None
    outcome_status: str | None
    lineage: list[dict]
    treatment_effectiveness: dict | None


@router.get("/{action_id}", response_model=CaseSummaryResponse)
async def get_case_for_action(action_id: str, request: Request) -> CaseSummaryResponse:
    service = build_case_summary_service(request)
    summary = service.build_for_action(action_id)
    if summary.action_id is None:
        raise HTTPException(status_code=404, detail="Case not found")
    return CaseSummaryResponse(**summary.model_dump(mode="json"))


__all__ = ["router"]