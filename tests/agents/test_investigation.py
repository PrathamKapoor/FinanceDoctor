"""Tests for Stage 3 agentic investigation engine."""

from __future__ import annotations

import pytest
from backend.app.agents.m3 import run_m3_diagnosis
from backend.app.agents.orchestrator import InvestigationOrchestrator, run_investigation
from backend.app.agents.workers import (
    CohortWorker,
    FailureReasonWorker,
    PaymentMethodWorker,
    TemporalWorker,
    run_all_workers,
)
from backend.app.schemas.agent.diagnosis import DiagnosisOutput
from backend.app.schemas.agent.worker_outputs import (
    CohortWorkerOutput,
    FailureReasonWorkerOutput,
    PaymentMethodWorkerOutput,
    TemporalWorkerOutput,
)
from backend.app.services.incident_generator import IncidentConfig, inject_incident
from backend.app.services.synthetic_data import (
    SyntheticMerchantConfig,
    generate_merchant_world,
)


class TestWorkerSchemas:
    """Test that worker output schemas validate correctly."""

    def test_temporal_worker_output_valid(self):
        output = TemporalWorkerOutput(
            worker="temporal",
            finding="Test finding citing evidence",
            evidence_ids=["temporal.anomaly"],
            supports=["TEMPORAL_SPIKE"],
            contradicts=[],
            confidence=0.9,
            anomaly_detected=True,
            peak_window="2026-07-31T14:37:00/2026-07-31T17:37:00",
        )
        assert output.worker == "temporal"
        assert output.confidence == 0.9

    def test_payment_method_worker_output_valid(self):
        output = PaymentMethodWorkerOutput(
            worker="payment_method",
            finding="Test finding",
            evidence_ids=["payment_method.UPI.failure_rate"],
            supports=["PAYMENT_METHOD_DEGRADATION"],
            contradicts=[],
            confidence=0.95,
            affected_methods=["UPI"],
            max_delta=0.35,
        )
        assert output.worker == "payment_method"
        assert output.max_delta == 0.35

    def test_cohort_worker_output_valid(self):
        output = CohortWorkerOutput(
            worker="cohort",
            finding="Test finding",
            evidence_ids=["cohort.RETURNING.delta"],
            supports=["PAYMENT_METHOD_DEGRADATION"],
            contradicts=["CUSTOMER_BEHAVIOR_CHANGE"],
            confidence=0.85,
            affected_cohorts=["RETURNING"],
            returning_bias=0.15,
        )
        assert output.returning_bias == 0.15

    def test_failure_reason_worker_output_valid(self):
        output = FailureReasonWorkerOutput(
            worker="failure_reason",
            finding="Test finding",
            evidence_ids=["failure_reason.NETWORK_ERROR"],
            supports=["INFRASTRUCTURE_ISSUE"],
            contradicts=["FRAUD_SPIKE"],
            confidence=0.9,
            dominant_reason="NETWORK_ERROR",
            dominance_ratio=0.82,
        )
        assert output.dominance_ratio == 0.82

    def test_diagnosis_output_valid(self):
        diag = DiagnosisOutput(
            diagnosis_id="diag_001",
            incident_type="PAYMENT_METHOD_FAILURE_SPIKE",
            leading_hypothesis="PAYMENT_METHOD_DEGRADATION",
            confidence=0.91,
            summary="Test summary with evidence citations that is long enough to pass validation",
            supporting_evidence_ids=["anomaly.payment_failure_rate"],
            contradicting_evidence_ids=[],
            alternative_hypotheses=[
                {
                    "hypothesis": "GENERAL_PAYMENT_FAILURE",
                    "score": 0.05,
                    "reason": "Other methods normal",
                },
            ],
            recommended_action_type="CREATE_PAYMENT_LINK",
            action_rationale="Payment link re-collection for failed payments",
            uncertainties=["Root cause not definitively identified"],
        )
        assert diag.leading_hypothesis == "PAYMENT_METHOD_DEGRADATION"
        assert diag.recommended_action_type == "CREATE_PAYMENT_LINK"

    def test_diagnosis_invalid_action_type(self):
        with pytest.raises(ValueError):
            DiagnosisOutput(
                diagnosis_id="diag_001",
                incident_type="PAYMENT_METHOD_FAILURE_SPIKE",
                leading_hypothesis="PAYMENT_METHOD_DEGRADATION",
                confidence=0.9,
                summary="Test",
                recommended_action_type="INVALID_ACTION",
                action_rationale="Test",
            )

    def test_confidence_bounds(self):
        with pytest.raises(ValueError):
            DiagnosisOutput(
                diagnosis_id="diag_001",
                incident_type="TEST",
                leading_hypothesis="TEST",
                confidence=1.5,  # > 1.0
                summary="Test",
                recommended_action_type="CREATE_PAYMENT_LINK",
                action_rationale="Test",
            )


class TestM27Workers:
    """Test M2.7 workers with stub model client."""

    @pytest.fixture
    def world_with_incident(self):
        config = SyntheticMerchantConfig(
            seed=42, num_customers=500, num_orders=1000, baseline_days=14
        )
        world = generate_merchant_world(config)
        inject_incident(world, IncidentConfig())
        return world

    @pytest.mark.asyncio
    async def test_temporal_worker_runs(self, world_with_incident):
        from backend.app.services.analytics import AnalyticsEngine
        from backend.app.services.evidence import build_bundle

        engine = AnalyticsEngine(world_with_incident)
        bundle = build_bundle(world_with_incident, engine)

        worker = TemporalWorker()
        result = await worker.run(bundle, world_with_incident)

        assert isinstance(result, TemporalWorkerOutput)
        assert result.worker == "temporal"
        assert 0.0 <= result.confidence <= 1.0
        assert len(result.evidence_ids) > 0
        assert result.anomaly_detected is True

    @pytest.mark.asyncio
    async def test_payment_method_worker_runs(self, world_with_incident):
        from backend.app.services.analytics import AnalyticsEngine
        from backend.app.services.evidence import build_bundle

        engine = AnalyticsEngine(world_with_incident)
        bundle = build_bundle(world_with_incident, engine)

        worker = PaymentMethodWorker()
        result = await worker.run(bundle, world_with_incident)

        assert isinstance(result, PaymentMethodWorkerOutput)
        assert result.worker == "payment_method"
        assert "UPI" in result.affected_methods
        assert result.max_delta > 0.3

    @pytest.mark.asyncio
    async def test_cohort_worker_runs(self, world_with_incident):
        from backend.app.services.analytics import AnalyticsEngine
        from backend.app.services.evidence import build_bundle

        engine = AnalyticsEngine(world_with_incident)
        bundle = build_bundle(world_with_incident, engine)

        worker = CohortWorker()
        result = await worker.run(bundle, world_with_incident)

        assert isinstance(result, CohortWorkerOutput)
        assert result.worker == "cohort"
        assert "RETURNING" in result.affected_cohorts

    @pytest.mark.asyncio
    async def test_failure_reason_worker_runs(self, world_with_incident):
        from backend.app.services.analytics import AnalyticsEngine
        from backend.app.services.evidence import build_bundle

        engine = AnalyticsEngine(world_with_incident)
        bundle = build_bundle(world_with_incident, engine)

        worker = FailureReasonWorker()
        result = await worker.run(bundle, world_with_incident)

        assert isinstance(result, FailureReasonWorkerOutput)
        assert result.worker == "failure_reason"
        assert result.dominant_reason == "NETWORK_ERROR"
        assert result.dominance_ratio > 0.7

    @pytest.mark.asyncio
    async def test_all_workers_run_concurrently(self, world_with_incident):
        from backend.app.services.analytics import AnalyticsEngine
        from backend.app.services.evidence import build_bundle

        engine = AnalyticsEngine(world_with_incident)
        bundle = build_bundle(world_with_incident, engine)

        results = await run_all_workers(bundle, world_with_incident)

        assert "temporal" in results
        assert "payment_method" in results
        assert "cohort" in results
        assert "failure_reason" in results

        for worker_name, result in results.items():
            assert "error" not in result, f"Worker {worker_name} failed: {result.get('error')}"


class TestM3Diagnosis:
    """Test M3 diagnosis with stub model client."""

    @pytest.fixture
    def world_with_incident(self):
        config = SyntheticMerchantConfig(
            seed=42, num_customers=500, num_orders=1000, baseline_days=14
        )
        world = generate_merchant_world(config)
        inject_incident(world, IncidentConfig())
        return world

    @pytest.mark.asyncio
    async def test_m3_diagnosis_runs(self, world_with_incident):
        from backend.app.services.analytics import AnalyticsEngine
        from backend.app.services.evidence import build_bundle

        engine = AnalyticsEngine(world_with_incident)
        bundle = build_bundle(world_with_incident, engine)

        # First run workers
        worker_outputs = await run_all_workers(bundle, world_with_incident)

        # Then run M3
        diagnosis = await run_m3_diagnosis(bundle, worker_outputs)

        assert isinstance(diagnosis, DiagnosisOutput)
        assert diagnosis.leading_hypothesis == "PAYMENT_METHOD_DEGRADATION"
        assert diagnosis.recommended_action_type == "CREATE_PAYMENT_LINK"
        assert 0.0 <= diagnosis.confidence <= 1.0
        assert len(diagnosis.supporting_evidence_ids) > 0
        assert len(diagnosis.alternative_hypotheses) >= 3
        assert len(diagnosis.uncertainties) > 0

    @pytest.mark.asyncio
    async def test_diagnosis_contains_correct_hypothesis(self, world_with_incident):
        from backend.app.services.analytics import AnalyticsEngine
        from backend.app.services.evidence import build_bundle

        engine = AnalyticsEngine(world_with_incident)
        bundle = build_bundle(world_with_incident, engine)

        worker_outputs = await run_all_workers(bundle, world_with_incident)
        diagnosis = await run_m3_diagnosis(bundle, worker_outputs)

        # Verify the leading hypothesis matches ground truth
        assert diagnosis.leading_hypothesis == "PAYMENT_METHOD_DEGRADATION"

        # Verify UPI is mentioned in evidence
        evidence_ids = diagnosis.supporting_evidence_ids
        assert any("UPI" in eid for eid in evidence_ids)


class TestInvestigationOrchestrator:
    """Test the full investigation pipeline."""

    @pytest.mark.asyncio
    async def test_full_investigation_runs(self):
        config = SyntheticMerchantConfig(
            seed=42, num_customers=200, num_orders=500, baseline_days=7
        )
        world = generate_merchant_world(config)
        inject_incident(world, IncidentConfig())

        investigation = await run_investigation(world)

        assert investigation.incident_type == "PAYMENT_METHOD_FAILURE_SPIKE"
        assert investigation.state.value == "DIAGNOSIS_COMPLETE"
        assert investigation.anomaly_detected is True
        assert investigation.anomaly_score > 3.0
        assert investigation.diagnosis_ref is not None
        assert investigation.completed_at is not None

    @pytest.mark.asyncio
    async def test_investigation_state_transitions(self):
        config = SyntheticMerchantConfig(
            seed=42, num_customers=100, num_orders=200, baseline_days=7
        )
        world = generate_merchant_world(config)
        inject_incident(world, IncidentConfig())

        orchestrator = InvestigationOrchestrator(world)

        # Check initial state
        assert orchestrator._current_investigation is None

        investigation = await orchestrator.run_investigation("PAYMENT_METHOD_FAILURE_SPIKE")

        # Verify final state
        assert investigation.state.value == "DIAGNOSIS_COMPLETE"

    @pytest.mark.asyncio
    async def test_investigation_fails_without_incident(self):
        """Investigation should fail if no incident is injected."""
        config = SyntheticMerchantConfig(
            seed=42, num_customers=100, num_orders=200, baseline_days=7
        )
        world = generate_merchant_world(config)
        # No incident injected!

        from backend.app.agents.orchestrator import OrchestratorError

        with pytest.raises(OrchestratorError) as exc_info:
            await run_investigation(world)

        assert "No incident injected" in str(exc_info.value)


class TestInvestigationStateMachine:
    """Test investigation state machine transitions."""

    def test_valid_transitions(self):
        from backend.app.schemas.agent.investigation import Investigation, InvestigationState

        inv = Investigation(investigation_id="inv_test", incident_type="TEST")

        # Valid transitions
        inv.transition(InvestigationState.EVIDENCE_PREPARING)
        assert inv.state == InvestigationState.EVIDENCE_PREPARING

        inv.transition(InvestigationState.WORKERS_RUNNING)
        assert inv.state == InvestigationState.WORKERS_RUNNING

        inv.transition(InvestigationState.EVIDENCE_ASSEMBLED)
        assert inv.state == InvestigationState.EVIDENCE_ASSEMBLED

        inv.transition(InvestigationState.DIAGNOSIS_RUNNING)
        assert inv.state == InvestigationState.DIAGNOSIS_RUNNING

        inv.transition(InvestigationState.DIAGNOSIS_COMPLETE)
        assert inv.state == InvestigationState.DIAGNOSIS_COMPLETE

    def test_invalid_transition_raises(self):
        from backend.app.schemas.agent.investigation import Investigation, InvestigationState

        inv = Investigation(investigation_id="inv_test", incident_type="TEST")

        with pytest.raises(ValueError):
            inv.transition(InvestigationState.DIAGNOSIS_COMPLETE)  # Can't jump from CREATED


class TestGoldenInvestigation:
    """Golden test for the known incident with seed=42."""

    @pytest.mark.asyncio
    async def test_golden_investigation_matches_ground_truth(self):
        """The known PAYMENT_METHOD_FAILURE_SPIKE with seed=42 must produce correct diagnosis."""
        config = SyntheticMerchantConfig(
            seed=42,
            num_customers=4000,
            num_orders=6000,
            baseline_days=30,
        )
        world = generate_merchant_world(config)
        inject_incident(world, IncidentConfig())

        investigation = await run_investigation(world)

        # Verify investigation completed successfully
        assert investigation.state.value == "DIAGNOSIS_COMPLETE"
        assert investigation.anomaly_detected is True
        assert investigation.anomaly_score > 10.0  # z > 10

        # The diagnosis should match ground truth
        from backend.app.services.analytics import AnalyticsEngine
        from backend.app.services.evidence import build_bundle

        engine = AnalyticsEngine(world)
        bundle = build_bundle(world, engine)
        worker_outputs = await run_all_workers(bundle, world)
        diagnosis = await run_m3_diagnosis(bundle, worker_outputs)

        # Verify ground truth matches
        assert diagnosis.leading_hypothesis == "PAYMENT_METHOD_DEGRADATION"
        assert diagnosis.recommended_action_type == "CREATE_PAYMENT_LINK"

        # Evidence should reference UPI specifically
        evidence_ids = diagnosis.supporting_evidence_ids
        assert any("UPI" in eid for eid in evidence_ids)

        # NETWORK_ERROR should be dominant
        assert any("NETWORK_ERROR" in eid for eid in evidence_ids)

        # Cohort effect should be noted
        assert any("RETURNING" in eid or "cohort" in eid.lower() for eid in evidence_ids)

        # Alternative hypotheses should be present and scored low
        alt_scores = [alt["score"] for alt in diagnosis.alternative_hypotheses]
        assert all(s < 0.1 for s in alt_scores)  # All alternatives should be low confidence