"""Development/demo endpoints for the Stage 1 financial substrate.

These exist to validate the deterministic substrate. They are NOT the production API.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from backend.app.db.database import get_session_factory
from backend.app.schemas.incidents import IncidentConfig, IncidentGroundTruth
from backend.app.services.analytics import AnalyticsEngine
from backend.app.services.evidence import build_bundle, flatten
from backend.app.services.financial_state import persist_world, reset_db
from backend.app.services.incident_generator import inject_incident
from backend.app.services.synthetic_data import (
    SyntheticMerchantConfig,
    generate_merchant_world,
)

router = APIRouter(tags=["demo"])


class SeedRequest(BaseModel):
    seed: int | None = Field(default=None)
    num_orders: int | None = Field(default=None)
    num_customers: int | None = Field(default=None)
    baseline_failure_rate: float | None = Field(default=None)


def _require_world(request: Request):
    world = getattr(request.app.state, "world", None)
    if world is None:
        raise HTTPException(status_code=409, detail="No world seeded. Call POST /demo/seed first.")
    return world


@router.post("/demo/seed")
def seed(request: Request, payload: SeedRequest | None = None) -> dict[str, object]:
    config = SyntheticMerchantConfig()
    if payload is not None:
        if payload.seed is not None:
            config.seed = payload.seed
        if payload.num_orders is not None:
            config.num_orders = payload.num_orders
        if payload.num_customers is not None:
            config.num_customers = payload.num_customers
        if payload.baseline_failure_rate is not None:
            config.baseline_failure_rate = payload.baseline_failure_rate

    world = generate_merchant_world(config)
    reset_db()
    with get_session_factory()() as session:
        persist_world(session, world)
    request.app.state.world = world
    return summarize_world(world)


def summarize_world(world) -> dict[str, object]:
    engine = AnalyticsEngine(world)
    total_attempts = len(world.attempts)
    summary = {
        "merchant": world.merchant.name,
        "period_days": world.config.baseline_days,
        "customers": len(world.customers),
        "orders": len(world.orders),
        "payments": len(world.payments),
        "payment_attempts": total_attempts,
        "baseline": {
            "success_rate": round(engine.overall().baseline.success_rate, 4),
            "failure_rate": round(engine.overall().baseline.failure_rate, 4),
        },
    }
    if world.incident is not None and world.ground_truth is not None:
        summary["incident"] = _incident_summary(world)
    return summary


def _incident_summary(world) -> dict[str, object]:
    gt: IncidentGroundTruth = world.ground_truth
    engine = AnalyticsEngine(world)
    current = engine.overall().current
    return {
        "type": gt.incident_type,
        "start": gt.start_time.isoformat(),
        "end": gt.end_time.isoformat(),
        "affected_dimension": gt.affected_dimension,
        "affected_value": gt.affected_value,
        "current_success_rate": round(current.success_rate, 4),
        "current_failure_rate": round(current.failure_rate, 4),
    }


@router.post("/demo/inject-incident")
def inject(request: Request) -> dict[str, object]:
    world = _require_world(request)
    incident = IncidentConfig()
    ground_truth = inject_incident(world, incident)
    reset_db()
    with get_session_factory()() as session:
        persist_world(session, world)
    return ground_truth.model_dump()


@router.get("/demo/metrics")
def metrics(request: Request) -> dict[str, object]:
    world = _require_world(request)
    engine = AnalyticsEngine(world)
    current = engine.overall().current
    return {
        "overall": {
            "baseline": engine.overall().baseline.model_dump(),
            "current": current.model_dump(),
            "absolute_delta": engine.overall().absolute_delta,
            "relative_delta": engine.overall().relative_delta,
        },
        "payment_methods": [m.model_dump() for m in engine.payment_methods()],
        "cohorts": [c.model_dump() for c in engine.cohorts()],
        "failure_reasons": [r.model_dump() for r in engine.failure_reasons()],
        "monetary": engine.monetary().model_dump(),
        "anomaly": engine.anomaly().model_dump(),
    }


@router.get("/demo/evidence")
def evidence(request: Request) -> dict[str, object]:
    world = _require_world(request)
    engine = AnalyticsEngine(world)
    bundle = build_bundle(world, engine)
    evidence_items = flatten(bundle)
    return {"bundle": bundle.model_dump(), "evidence": [e.model_dump() for e in evidence_items]}