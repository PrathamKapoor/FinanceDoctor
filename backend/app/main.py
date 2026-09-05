"""FastAPI application factory (Stage 5 wiring + Stage 6 demo-case integration)."""

from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.app.adapters.razorpay.webhook import router as webhook_router
from backend.app.agents import investigation_router
from backend.app.config import get_settings, validate_startup
from backend.app.routers import action, case, demo, demo_case, health, outcome
from backend.app.services.demo.session import DemoSessionStore
from backend.app.services.outcome.case_summary import CaseSummaryService
from backend.app.services.outcome.outcome_evaluator import OutcomeEvaluator
from backend.app.services.outcome.outcome_initializer import OutcomeInitializer
from backend.app.services.outcome.outcome_store import AuditStore, OutcomeStore
from backend.app.services.outcome.outcome_webhook_handler import (
    OutcomeWebhookHandler,
)


def create_app() -> FastAPI:
    app = FastAPI(title="Financial Doctor", version="0.6.0")
    app.state.world = None

    # Fail fast on dangerous provider combinations (never silent fallback).
    settings = get_settings()
    validate_startup(settings)

    # Explicit CORS origins from configuration (no wildcards with credentials).
    # The frontend runs from a Vite dev server or the bundled static build;
    # no secrets are exposed and writes stay gated by policy + human approval.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.parsed_cors_origins(),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Stage 6 — demo case sessions (process-local).
    app.state.demo_store = DemoSessionStore()

    # Stage 5 — outcome layer singletons.
    outcome_store = OutcomeStore()
    audit_store = AuditStore()
    evaluator = OutcomeEvaluator(outcome_store, audit_store)
    initializer = OutcomeInitializer(outcome_store, audit_store, evaluator)
    webhook_handler = OutcomeWebhookHandler(
        outcome_store=outcome_store,
        audit_store=audit_store,
        evaluator=evaluator,
        webhook_secret=settings.razorpay_webhook_secret,
    )

    app.state.outcome_store = outcome_store
    app.state.audit_store = audit_store
    app.state.outcome_evaluator = evaluator
    app.state.outcome_initializer = initializer
    app.state.webhook_handler = webhook_handler
    # Case-summary resolvers — populated by the action router on the
    # first investigation / action creation. The outcome router reads
    # these lazily.
    app.state.case_resolvers = {}

    app.include_router(health.router)
    app.include_router(demo.router)
    app.include_router(webhook_router)
    app.include_router(investigation_router)
    app.include_router(action.router)
    app.include_router(outcome.router)
    app.include_router(case.router)
    app.include_router(demo_case.router)

    # Single-process deployment: serve the production frontend build if it
    # exists (``npm run build`` in frontend/). Dev keeps using the Vite server.
    dist_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "frontend",
        "dist",
    )
    if os.path.isdir(dist_dir):
        app.mount("/", StaticFiles(directory=dist_dir, html=True), name="frontend")
    return app


# Re-export case-summary service factory so the action router can wire
# its resolvers into the FastAPI app state.
__all__ = ["create_app", "CaseSummaryService"]


app = create_app()