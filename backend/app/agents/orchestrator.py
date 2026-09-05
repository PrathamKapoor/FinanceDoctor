"""Investigation Orchestrator - drives the full investigation pipeline."""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from backend.app.agents.m3 import run_m3_diagnosis
from backend.app.agents.workers import run_all_workers
from backend.app.schemas.agent.diagnosis import DiagnosisOutput
from backend.app.schemas.agent.investigation import Investigation, InvestigationState
from backend.app.schemas.evidence import EvidenceBundle
from backend.app.services.analytics import AnalyticsEngine
from backend.app.services.evidence import EvidenceStore, build_bundle, flatten
from backend.app.services.synthetic_data import MerchantWorld


class OrchestratorError(Exception):
    """Orchestrator error."""

    def __init__(self, investigation_id: str, message: str, state: str | None = None):
        self.investigation_id = investigation_id
        self.state = state
        super().__init__(f"Investigation {investigation_id} ({state}): {message}")


class InvestigationOrchestrator:
    """Orchestrates the full investigation pipeline: anomaly -> evidence ->
    workers -> M3 -> diagnosis."""

    def __init__(
        self,
        world: MerchantWorld,
        evidence_store: EvidenceStore | None = None,
        model_client=None,
    ) -> None:
        self._world = world
        self._evidence_store = evidence_store
        self._model_client = model_client
        self._analytics = AnalyticsEngine(world)
        self._current_investigation: Investigation | None = None

    async def run_investigation(
        self,
        incident_type: str,
        baseline_window: tuple[dt.datetime, dt.datetime] | None = None,
        current_window: tuple[dt.datetime, dt.datetime] | None = None,
    ) -> Investigation:
        """Run a complete investigation from anomaly detection to diagnosis."""

        # Create investigation record
        investigation = Investigation(
            investigation_id=f"inv_{uuid.uuid4().hex[:12]}",
            incident_type=incident_type,
            state=InvestigationState.CREATED,
        )
        self._current_investigation = investigation

        try:
            # Phase 1: Evidence Preparation
            investigation.transition(InvestigationState.EVIDENCE_PREPARING)
            await self._prepare_evidence(investigation, baseline_window, current_window)

            # Phase 2: Run M2.7 Workers
            investigation.transition(InvestigationState.WORKERS_RUNNING)
            await self._run_workers(investigation)

            # Phase 3: Assemble Evidence Bundle
            investigation.transition(InvestigationState.EVIDENCE_ASSEMBLED)
            evidence_bundle = await self._assemble_bundle(investigation)

            # Phase 4: M3 Diagnosis
            investigation.transition(InvestigationState.DIAGNOSIS_RUNNING)
            diagnosis = await self._run_diagnosis(investigation, evidence_bundle)

            # Phase 5: Complete
            investigation.transition(InvestigationState.DIAGNOSIS_COMPLETE)
            investigation.diagnosis_ref = diagnosis.diagnosis_id

            return investigation

        except Exception as e:
            investigation.transition(InvestigationState.FAILED)
            investigation.error = str(e)
            raise OrchestratorError(
                investigation.investigation_id, str(e), investigation.state.value
            ) from e

    async def _prepare_evidence(
        self,
        investigation: Investigation,
        baseline_window: tuple | None,
        current_window: tuple | None,
    ) -> None:
        """Configure analytics engine with appropriate windows."""
        # The analytics engine is already configured with the world's windows
        # This phase validates that we have the right data
        if not self._world.incident:
            raise OrchestratorError(
                investigation.investigation_id,
                "No incident injected in world",
                investigation.state.value,
            )

        # Run analytics to compute anomaly
        anomaly = self._analytics.anomaly()
        investigation.anomaly_detected = anomaly.is_anomalous
        investigation.anomaly_score = anomaly.anomaly_score

        if not anomaly.is_anomalous:
            raise OrchestratorError(
                investigation.investigation_id,
                "No anomaly detected - investigation not warranted",
                investigation.state.value,
            )

    async def _run_workers(self, investigation: Investigation) -> dict[str, Any]:
        """Run all M2.7 workers concurrently."""
        # We need a fresh analytics engine for the bundle
        bundle = build_bundle(self._world, self._analytics)

        worker_outputs = await run_all_workers(bundle, self._world, self._model_client)

        # Store worker outputs (in practice would persist to evidence store)
        investigation.worker_outputs_ref = {
            worker: f"worker_output_{worker}_{investigation.investigation_id}"
            for worker in ["temporal", "payment_method", "cohort", "failure_reason"]
        }

        return worker_outputs

    async def _assemble_bundle(self, investigation: Investigation) -> EvidenceBundle:
        """Build and persist the final evidence bundle."""
        bundle = build_bundle(self._world, self._analytics)

        # Persist to evidence store if available
        if self._evidence_store:
            scope = f"investigation:{investigation.investigation_id}"
            flattened = flatten(bundle)
            self._evidence_store.write(scope, flattened)

        investigation.evidence_bundle_ref = f"investigation:{investigation.investigation_id}"
        return bundle

    async def _run_diagnosis(
        self, investigation: Investigation, evidence_bundle: EvidenceBundle
    ) -> DiagnosisOutput:
        """Run M3 diagnosis with the assembled evidence."""
        # We need to re-run workers to get their outputs for M3
        # In practice, we'd retrieve from store, but for now re-run
        bundle = build_bundle(self._world, self._analytics)
        worker_outputs = await run_all_workers(bundle, self._world, self._model_client)

        diagnosis = await run_m3_diagnosis(
            evidence_bundle=bundle,
            worker_outputs=worker_outputs,
            model_client=self._model_client,
        )

        return diagnosis


async def run_investigation(
    world: MerchantWorld,
    incident_type: str = "PAYMENT_METHOD_FAILURE_SPIKE",
    evidence_store: Any = None,
    model_client=None,
) -> Investigation:
    """Convenience function to run a complete investigation."""
    orchestrator = InvestigationOrchestrator(world, evidence_store, model_client)
    return await orchestrator.run_investigation(incident_type)