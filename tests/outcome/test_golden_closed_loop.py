"""Stage 5 — Golden closed-loop test.

The first end-to-end closed-loop test spanning Stages 1-5:

  seed=42
  PAYMENT_METHOD_FAILURE_SPIKE
       ↓
  Anomaly detected (Stage 1)
       ↓
  M2.7 investigation (Stage 3)
       ↓
  M3 diagnosis (Stage 3)
       ↓
  PAYMENT_METHOD_DEGRADATION
       ↓
  CREATE_PAYMENT_LINK (Stage 4)
       ↓
  Policy evaluation
       ↓
  HUMAN_APPROVAL_REQUIRED
       ↓
  Human approves
       ↓
  Action execution
       ↓
  Stub Payment Link created
       ↓
  Simulated provider payment
       ↓
  payment_link.paid webhook
       ↓
  Target outcome updated
       ↓
  OutcomeEvaluator
       ↓
  Recovery metrics calculated
       ↓
  Case summary updated

Verifies the entire lineage.
"""

from __future__ import annotations

import pytest
from backend.app.adapters.razorpay.stub import StubRazorpayAdapter
from backend.app.agents.m3 import run_m3_diagnosis
from backend.app.agents.orchestrator import run_investigation
from backend.app.agents.workers import run_all_workers
from backend.app.schemas.action.action import ProposedAction
from backend.app.schemas.action.approval import ApprovalStatus
from backend.app.schemas.action.execution import ExecutionStatus
from backend.app.schemas.outcome.enums import (
    OutcomeStatus,
    TargetOutcomeStatus,
)
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
from backend.app.services.outcome.stub_provider import StubProviderSimulator
from backend.app.services.synthetic_data import (
    SyntheticMerchantConfig,
    generate_merchant_world,
)

SECRET = "test_webhook_secret"


@pytest.mark.asyncio
async def test_golden_closed_loop():
    # ---- Stage 1: world + incident ----
    config = SyntheticMerchantConfig()
    world = generate_merchant_world(config)
    inject_incident(world, IncidentConfig())

    # ---- Stage 3: investigation + diagnosis ----
    investigation = await run_investigation(world, "PAYMENT_METHOD_FAILURE_SPIKE")
    assert investigation.diagnosis_ref is not None

    engine = AnalyticsEngine(world)
    bundle = build_bundle(world, engine)
    worker_outputs = await run_all_workers(bundle, world)
    diagnosis = await run_m3_diagnosis(bundle, worker_outputs)
    assert diagnosis.recommended_action_type == "CREATE_PAYMENT_LINK"

    # ---- Stage 4: action + policy + approval ----
    planner = ActionPlanner(world)
    action = planner.plan(diagnosis, investigation_id=investigation.investigation_id)

    assert isinstance(action, ProposedAction)
    assert action.diagnosis_id == diagnosis.diagnosis_id
    assert action.investigation_id == investigation.investigation_id
    assert len(action.targets) > 0
    snapshot = planner.create_snapshot(action)
    policy_engine = PolicyEngine(world)
    decision = policy_engine.evaluate(action, diagnosis, investigation, snapshot)
    if decision.decision.value != "HUMAN_APPROVAL_REQUIRED":
        for c in decision.checks:
            if c.status.value == "FAIL":
                print(f"FAIL: {c.check}: {c.message} actual={c.actual} limit={c.limit}")
    assert decision.decision.value == "HUMAN_APPROVAL_REQUIRED"

    approval_service = ApprovalService(ttl_minutes=60)
    approval = approval_service.create_approval(action, decision)
    approval_service.approve(approval.approval_id, "human_reviewer", "Looks good")
    assert approval.status == ApprovalStatus.APPROVED

    # ---- Stage 5: outcome layer (singleton stores) ----
    outcomes = OutcomeStore()
    audit = AuditStore()
    evaluator = OutcomeEvaluator(outcomes, audit)
    initializer = OutcomeInitializer(outcomes, audit, evaluator)
    handler = OutcomeWebhookHandler(outcomes, audit, evaluator, webhook_secret=SECRET)
    # hermetic: inject a single shared stub adapter so the executor and
    # the provider simulator operate on the same in-memory payment links.
    # The webhook handler then observes links created during execution.
    stub_adapter = StubRazorpayAdapter(world, webhook_secret=SECRET)
    executor = ActionExecutor(outcome_initializer=initializer, adapter=stub_adapter)
    execution = await executor.execute(action, approval)
    assert execution.status == ExecutionStatus.SUCCEEDED
    assert execution.execution_id is not None
    assert execution.provider_reference is not None

    # ---- Verify outcome was initialised deterministically ----
    outcome = outcomes.get_outcome_by_action(action.action_id)
    assert outcome is not None
    assert outcome.execution_id == execution.execution_id
    assert outcome.investigation_id == investigation.investigation_id
    assert outcome.diagnosis_id == diagnosis.diagnosis_id
    assert outcome.approval_id == approval.approval_id

    # Each target should have a payment_link_id assigned.
    targets = outcomes.list_targets_for_outcome(outcome.outcome_id)
    assert len(targets) == len(action.targets)
    assert all(t.payment_link_id is not None for t in targets)
    assert all(t.status == TargetOutcomeStatus.PENDING for t in targets)

    # ---- Stage 5: simulate provider payment -> webhook ----
    # Simulate that the FIRST target's link was paid.
    simulator = StubProviderSimulator(stub_adapter, SECRET)
    first_target = targets[0]
    simulator.mark_payment_link_paid(first_target.payment_link_id)

    payload, body = simulator.build_payment_link_paid_payload(first_target.payment_link_id)
    from backend.app.adapters.razorpay.models import NormalizedWebhookEvent

    event = NormalizedWebhookEvent(
        event="payment_link.paid",
        payload=payload["payload"],
        raw=payload,
    )
    result = handler.process_event(event)
    assert result["status"] == "processed"
    assert result["target_status"] == "PAID"

    # ---- Verify outcome aggregation ----
    refreshed = outcomes.get_outcome(outcome.outcome_id)
    assert refreshed.amount_recovered_minor == first_target.expected_amount_minor
    assert refreshed.targets_succeeded == 1
    assert refreshed.status == OutcomeStatus.PARTIALLY_RECOVERED

    # ---- Verify treatment effectiveness ----
    eff = evaluator.compute_effectiveness(outcome.outcome_id)
    assert eff.targets_recovered == 1
    assert eff.targets_unrecovered == 0
    assert eff.targets_pending == len(targets) - 1
    assert eff.recovery_rate == pytest.approx(1 / len(targets))
    assert eff.amount_remaining_minor == (
        refreshed.amount_targeted_minor - refreshed.amount_recovered_minor
    )

    # ---- Verify audit trail ----
    events = audit.list_for_entity("outcome", outcome.outcome_id)
    audit_types = {e.event_type.value for e in events}
    assert "OUTCOME_INITIALIZED" in audit_types
    assert "OUTCOME_RECALCULATED" in audit_types

    target_audits = audit.list_for_entity("target_outcome", first_target.target_outcome_id)
    target_audit_types = {e.event_type.value for e in target_audits}
    assert "TARGET_PAYMENT_CONFIRMED" in target_audit_types

    # ---- Verify the full lineage IDs survive ----
    assert investigation.investigation_id is not None
    assert diagnosis.diagnosis_id is not None
    assert action.action_id is not None
    assert approval.approval_id is not None
    assert execution.execution_id is not None
    assert execution.provider_reference is not None
    assert outcome.outcome_id is not None

    # ---- Metrics ----
    metrics = handler.metrics
    assert metrics["events_processed"] == 1
    assert metrics["events_duplicated"] == 0
    assert metrics["targets_evaluated"] == 1
    assert metrics["aggregation_latency_ms_avg"] >= 0


@pytest.mark.asyncio
async def test_partial_recovery_batch():
    """10-target batch: 7 paid, 2 pending, 1 expired -> PARTIALLY_RECOVERED."""
    from backend.app.adapters.razorpay.models import NormalizedWebhookEvent
    from backend.app.schemas.outcome.intervention_outcome import InterventionOutcome
    from backend.app.schemas.outcome.target_outcome import RecoveryTargetOutcome

    outcomes = OutcomeStore()
    audit = AuditStore()
    evaluator = OutcomeEvaluator(outcomes, audit)
    handler = OutcomeWebhookHandler(outcomes, audit, evaluator, webhook_secret=SECRET)
    stub_adapter = StubRazorpayAdapter(
        generate_merchant_world(SyntheticMerchantConfig()), webhook_secret=SECRET
    )
    simulator = StubProviderSimulator(stub_adapter, SECRET)

    outcome = InterventionOutcome(
        action_id="act_batch",
        investigation_id="inv_batch",
        diagnosis_id="diag_batch",
        currency="INR",
    )
    outcomes.save_outcome(outcome)

    targets: list[RecoveryTargetOutcome] = []
    for i in range(10):
        link_id = f"plink_{i}"
        simulator.seed_payment_link(link_id, amount_minor=1000, reference_id=f"ref_{i}")
        target = RecoveryTargetOutcome(
            outcome_id=outcome.outcome_id,
            target_id=f"act_batch:pay_{i}",
            payment_id=f"pay_{i}",
            payment_link_id=link_id,
            provider_reference=f"ref_{i}",
            currency="INR",
            expected_amount_minor=1000,
        )
        outcomes.save_target(target)
        targets.append(target)

    evaluator.recalculate(outcome.outcome_id)
    assert outcomes.get_outcome(outcome.outcome_id).status == OutcomeStatus.PENDING

    # 7 paid
    for i in range(7):
        simulator.mark_payment_link_paid(targets[i].payment_link_id)
        payload, body = simulator.build_payment_link_paid_payload(targets[i].payment_link_id)
        event = NormalizedWebhookEvent(
            event="payment_link.paid",
            payload=payload["payload"],
            raw=payload,
        )
        handler.process_event(event)

    # 1 expired
    simulator.mark_payment_link_expired(targets[7].payment_link_id)
    expired_event = NormalizedWebhookEvent(
        event="payment_link.cancelled",
        payload={"payment_link": {"id": targets[7].payment_link_id}},
        raw={"event": "payment_link.cancelled"},
    )
    handler.process_event(expired_event)

    # 2 still pending
    refreshed = outcomes.get_outcome(outcome.outcome_id)
    assert refreshed.targets_total == 10
    assert refreshed.targets_succeeded == 7
    assert refreshed.targets_pending == 2
    assert refreshed.targets_expired == 1
    assert refreshed.amount_recovered_minor == 7000
    assert refreshed.amount_targeted_minor == 10000
    assert refreshed.status == OutcomeStatus.PARTIALLY_RECOVERED
    assert refreshed.conversion_rate == pytest.approx(0.7)

    eff = evaluator.compute_effectiveness(outcome.outcome_id)
    assert eff.recovery_rate == pytest.approx(0.7)
    assert eff.revenue_recovery_rate == pytest.approx(0.7)
