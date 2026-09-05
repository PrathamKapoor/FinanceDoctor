"""M2.7 Investigation Worker implementations.

Each worker runs independently, receives a constrained evidence slice,
and returns structured findings validated against Pydantic schemas.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from backend.app.agents.models import create_model_client, default_m27_model
from backend.app.agents.prompts import (
    get_cohort_prompt,
    get_failure_reason_prompt,
    get_payment_method_prompt,
    get_temporal_prompt,
)
from backend.app.schemas.agent.worker_outputs import (
    CohortWorkerOutput,
    FailureReasonWorkerOutput,
    PaymentMethodWorkerOutput,
    TemporalWorkerOutput,
)
from backend.app.schemas.evidence import EvidenceBundle
from backend.app.services.synthetic_data import MerchantWorld


class WorkerError(Exception):
    """Worker execution error."""

    def __init__(self, worker: str, message: str, original_error: Exception | None = None):
        self.worker = worker
        self.message = message
        self.original_error = original_error
        super().__init__(f"{worker}: {message}")


class BaseWorker:
    """Base class for M2.7 investigation workers."""

    def __init__(
        self,
        worker_name: str,
        prompt_loader: Callable[[], str],
        output_schema: type,
        model_client=None,
    ) -> None:
        self.worker_name = worker_name
        self._prompt_loader = prompt_loader
        self._output_schema = output_schema
        self._model_client = model_client or create_model_client()

    async def run(
        self,
        evidence_bundle: EvidenceBundle,
        world: MerchantWorld,
        *,
        model: str | None = None,
    ) -> Any:
        """Execute the worker with the given evidence bundle.

        ``model`` optionally pins the worker to a model id; by default
        workers use the configured M2.7 model, keeping M2.7 (investigation)
        and M3 (diagnosis) responsibilities distinct in live mode.
        """
        # Prepare evidence slice for this worker
        evidence_slice = self._prepare_evidence(evidence_bundle)

        # Load system prompt
        system_prompt = self._prompt_loader()

        # Construct user prompt with evidence
        user_prompt = self._build_user_prompt(evidence_slice)

        # Call model with structured output
        try:
            result = await self._model_client.generate(
                prompt=user_prompt,
                system_prompt=system_prompt,
                temperature=0.1,
                max_tokens=2048,
                response_schema=self._output_schema,
                model=model or default_m27_model(),
            )
            return result
        except Exception as e:
            raise WorkerError(self.worker_name, f"Model generation failed: {e}") from e

    def _prepare_evidence(self, bundle: EvidenceBundle) -> dict[str, Any]:
        """Extract the relevant evidence slice for this worker. Override in subclasses."""
        raise NotImplementedError

    def _build_user_prompt(self, evidence_slice: dict[str, Any]) -> str:
        """Build the user prompt with the evidence slice."""
        import json
        return (
            "Analyze the following deterministic evidence and return your structured finding.\n\n"
            "EVIDENCE:\n"
            f"{json.dumps(evidence_slice, indent=2, default=str)}"
        )


class TemporalWorker(BaseWorker):
    """Temporal investigation worker - analyzes time-based patterns."""

    def __init__(self, model_client=None):
        super().__init__(
            worker_name="temporal",
            prompt_loader=get_temporal_prompt,
            output_schema=TemporalWorkerOutput,
            model_client=model_client,
        )

    def _prepare_evidence(self, bundle: EvidenceBundle) -> dict[str, Any]:
        return {
            "baseline_daily": [b.model_dump() for b in bundle.baseline_daily],
            "temporal": [t.model_dump() for t in bundle.temporal],
            "anomaly": bundle.anomaly.model_dump(),
            "overall": bundle.overall.model_dump(),
        }


class PaymentMethodWorker(BaseWorker):
    """Payment method investigation worker - analyzes method-level patterns."""

    def __init__(self, model_client=None):
        super().__init__(
            worker_name="payment_method",
            prompt_loader=get_payment_method_prompt,
            output_schema=PaymentMethodWorkerOutput,
            model_client=model_client,
        )

    def _prepare_evidence(self, bundle: EvidenceBundle) -> dict[str, Any]:
        return {
            "payment_methods": [m.model_dump() for m in bundle.payment_methods],
            "failure_reasons": [r.model_dump() for r in bundle.failure_reasons],
        }


class CohortWorker(BaseWorker):
    """Customer cohort investigation worker - analyzes cohort-level patterns."""

    def __init__(self, model_client=None):
        super().__init__(
            worker_name="cohort",
            prompt_loader=get_cohort_prompt,
            output_schema=CohortWorkerOutput,
            model_client=model_client,
        )

    def _prepare_evidence(self, bundle: EvidenceBundle) -> dict[str, Any]:
        return {
            "cohorts": [c.model_dump() for c in bundle.cohorts],
            "payment_methods": [m.model_dump() for m in bundle.payment_methods],
        }


class FailureReasonWorker(BaseWorker):
    """Failure reason investigation worker - analyzes failure reason patterns."""

    def __init__(self, model_client=None):
        super().__init__(
            worker_name="failure_reason",
            prompt_loader=get_failure_reason_prompt,
            output_schema=FailureReasonWorkerOutput,
            model_client=model_client,
        )

    def _prepare_evidence(self, bundle: EvidenceBundle) -> dict[str, Any]:
        return {
            "failure_reasons": [r.model_dump() for r in bundle.failure_reasons],
            "payment_methods": [m.model_dump() for m in bundle.payment_methods],
        }


async def run_all_workers(
    evidence_bundle: EvidenceBundle,
    world: MerchantWorld,
    model_client=None,
    worker_model: str | None = None,
) -> dict[str, Any]:
    """Run all M2.7 workers concurrently and return their outputs."""
    workers = [
        TemporalWorker(model_client),
        PaymentMethodWorker(model_client),
        CohortWorker(model_client),
        FailureReasonWorker(model_client),
    ]

    results = {}
    for worker in workers:
        try:
            result = await worker.run(evidence_bundle, world, model=worker_model)
            results[worker.worker_name] = result
        except WorkerError as e:
            # Log error but continue with other workers
            results[worker.worker_name] = {"error": e.message, "worker": e.worker}

    return results