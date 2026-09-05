"""Demo case session — the in-memory state machine backing the Stage 6 UI.

This module re-uses the exact Stage 1–5 service objects that the golden
closed-loop test exercises, so the demo never bypasses a safety boundary:

    DETECT → INVESTIGATE → DIAGNOSE → PRESCRIBE → POLICY CHECK
           → HUMAN APPROVAL → ACT → OBSERVE → MEASURE

The session is process-local and thread-safe. The frontend reads a single
aggregated read-model; mutations (approve / reject / execute / simulate) go
through the same deterministic services used in production tests.
"""

from __future__ import annotations

import datetime as dt
import threading
import uuid
from typing import Any

from backend.app.adapters.razorpay.stub import StubRazorpayAdapter
from backend.app.agents.m3 import run_m3_diagnosis
from backend.app.agents.orchestrator import run_investigation
from backend.app.agents.workers import run_all_workers
from backend.app.config import get_settings
from backend.app.schemas.action.action import ActionSnapshot, ProposedAction
from backend.app.schemas.action.approval import ApprovalRequest
from backend.app.schemas.action.execution import ActionExecution
from backend.app.schemas.action.policy import PolicyDecisionRecord
from backend.app.schemas.agent.diagnosis import DiagnosisOutput
from backend.app.schemas.agent.investigation import Investigation
from backend.app.schemas.evidence import EvidenceBundle
from backend.app.services.action.approval import ApprovalService
from backend.app.services.action.executor import ActionExecutor
from backend.app.services.action.planner import ActionPlanner
from backend.app.services.action.policy import PolicyEngine
from backend.app.services.analytics import AnalyticsEngine
from backend.app.services.evidence import build_bundle
from backend.app.services.incident_generator import IncidentConfig, inject_incident
from backend.app.services.outcome.outcome_evaluator import OutcomeEvaluator
from backend.app.services.outcome.outcome_initializer import OutcomeInitializer
from backend.app.services.outcome.outcome_store import AuditStore, OutcomeStore
from backend.app.services.outcome.outcome_webhook_handler import OutcomeWebhookHandler
from backend.app.services.synthetic_data import (
    SyntheticMerchantConfig,
    generate_merchant_world,
)

# Journey stage keys in the canonical order the UI renders.
STAGE_SYMPTOM = "symptom"
STAGE_INVESTIGATION = "investigation"
STAGE_DIAGNOSIS = "diagnosis"
STAGE_PRESCRIPTION = "prescription"
STAGE_SAFETY = "safety_check"
STAGE_APPROVAL = "approval"
STAGE_TREATMENT = "treatment"
STAGE_OUTCOME = "outcome"

STAGE_ORDER: tuple[str, ...] = (
    STAGE_SYMPTOM,
    STAGE_INVESTIGATION,
    STAGE_DIAGNOSIS,
    STAGE_PRESCRIPTION,
    STAGE_SAFETY,
    STAGE_APPROVAL,
    STAGE_TREATMENT,
    STAGE_OUTCOME,
)


class DemoCaseSession:
    """One Financial Doctor case, holding every Stage 1–5 artifact."""

    def __init__(self, case_id: str) -> None:
        self.case_id = case_id
        self.started_at = dt.datetime.utcnow()
        self.mode = "demo"  # stub Razorpay provider

        # Stage 1
        self.world: Any = None
        self.config: SyntheticMerchantConfig | None = None

        # Stage 3
        self.investigation: Investigation | None = None
        self.bundle: EvidenceBundle | None = None
        self.worker_outputs: dict[str, Any] = {}
        self.diagnosis: DiagnosisOutput | None = None

        # Stage 4
        self.action: ProposedAction | None = None
        self.snapshot: ActionSnapshot | None = None
        self.policy_decision: PolicyDecisionRecord | None = None
        self.approval_service: ApprovalService = ApprovalService(ttl_minutes=60)
        self.approval: ApprovalRequest | None = None

        # Stage 5 services (self-contained, like the golden test)
        self.outcome_store = OutcomeStore()
        self.audit_store = AuditStore()
        self.evaluator = OutcomeEvaluator(self.outcome_store, self.audit_store)
        self.initializer = OutcomeInitializer(
            self.outcome_store, self.audit_store, self.evaluator
        )
        self.webhook_secret: str = get_settings().razorpay_webhook_secret
        self.webhook_handler = OutcomeWebhookHandler(
            self.outcome_store,
            self.audit_store,
            self.evaluator,
            webhook_secret=self.webhook_secret,
        )
        self.stub_adapter: StubRazorpayAdapter | None = None
        self.executor: ActionExecutor | None = None
        self.execution: ActionExecution | None = None

        # Ordered timeline entries {stage, status, timestamp, note}.
        self.timeline: list[dict[str, Any]] = []

        # Stage 7A — consultation metadata (question/answer records only;
        # never financial state, never consulted by deterministic math).
        self.consultations: list[dict[str, Any]] = []
        self.last_consult_at: float | None = None

    def completed_stage(self, stage: str, status: str, note: str | None = None) -> None:
        self.timeline.append(
            {
                "stage": stage,
                "status": status,
                "timestamp": dt.datetime.utcnow().isoformat(),
                "note": note,
            }
        )


class DemoSessionStore:
    """Thread-safe registry of demo case sessions."""

    def __init__(self) -> None:
        self._sessions: dict[str, DemoCaseSession] = {}
        self._lock = threading.RLock()

    def put(self, session: DemoCaseSession) -> DemoCaseSession:
        with self._lock:
            self._sessions[session.case_id] = session
        return session

    def get(self, case_id: str) -> DemoCaseSession | None:
        with self._lock:
            return self._sessions.get(case_id)

    def clear(self) -> None:
        with self._lock:
            self._sessions.clear()


async def run_demo_case(
    *,
    seed: int | None = None,
    num_orders: int | None = None,
    num_customers: int | None = None,
) -> DemoCaseSession:
    """Build a known seeded incident up to the human-approval gate.

    Mirrors ``tests/outcome/test_golden_closed_loop.py`` exactly. The stub
    M2.7 / M3 models run deterministically, so the whole investigation and
    diagnosis are complete by the time this returns; only the human decision
    (and downstream effects) remain outstanding.
    """
    case_id = f"case_{uuid.uuid4().hex[:12]}"
    session = DemoCaseSession(case_id)

    # ---- Stage 1: world + incident ----
    config = SyntheticMerchantConfig()
    if seed is not None:
        config.seed = seed
    if num_orders is not None:
        config.num_orders = num_orders
    if num_customers is not None:
        config.num_customers = num_customers
    session.config = config

    world = generate_merchant_world(config)
    inject_incident(world, IncidentConfig())
    session.world = world

    session.stub_adapter = StubRazorpayAdapter(world, webhook_secret=session.webhook_secret)
    session.executor = ActionExecutor(
        outcome_initializer=session.initializer, adapter=session.stub_adapter, world=world
    )
    session.completed_stage(
        STAGE_SYMPTOM, "detected", note="Payment failure anomaly identified"
    )

    # ---- Stage 3: investigation + diagnosis ----
    session.investigation = await run_investigation(world, "PAYMENT_METHOD_FAILURE_SPIKE")
    engine = AnalyticsEngine(world)
    bundle = build_bundle(world, engine)
    worker_outputs = await run_all_workers(bundle, world)
    diagnosis = await run_m3_diagnosis(bundle, worker_outputs)
    session.bundle = bundle
    session.worker_outputs = worker_outputs
    session.diagnosis = diagnosis
    session.completed_stage(
        STAGE_INVESTIGATION, "complete", note="Four evidence domains analyzed"
    )
    session.completed_stage(
        STAGE_DIAGNOSIS, "complete", note=f"Leading hypothesis: {diagnosis.leading_hypothesis}"
    )

    # ---- Stage 4: prescription + policy ----
    planner = ActionPlanner(world)
    action = planner.plan(diagnosis, investigation_id=session.investigation.investigation_id)
    session.action = action
    snapshot = planner.create_snapshot(action)
    session.snapshot = snapshot
    session.completed_stage(
        STAGE_PRESCRIPTION,
        "proposed",
        note=f"{action.action_type.value} · {len(action.targets)} eligible targets",
    )

    policy_engine = PolicyEngine(world)
    decision = policy_engine.evaluate(action, diagnosis, session.investigation, snapshot)
    session.policy_decision = decision
    session.completed_stage(
        STAGE_SAFETY, decision.decision.value, note="Deterministic policy evaluation"
    )

    # ---- Stage 4: approval request (PENDING) ----
    approval = session.approval_service.create_approval(action, decision)
    session.approval = approval
    session.completed_stage(
        STAGE_APPROVAL, "PENDING", note="Awaiting human decision"
    )
    return session