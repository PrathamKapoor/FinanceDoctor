"""M3 Senior Financial Doctor diagnosis implementation."""

from __future__ import annotations

import json
from typing import Any

from backend.app.agents.models import create_model_client
from backend.app.agents.prompts import get_m3_diagnosis_prompt
from backend.app.schemas.agent.diagnosis import DiagnosisOutput
from backend.app.schemas.evidence import EvidenceBundle


class M3DiagnosisError(Exception):
    """M3 diagnosis error."""

    pass


class M3Diagnoser:
    """M3 Senior Financial Doctor - produces the final diagnosis."""

    def __init__(self, model_client=None):
        self._model_client = model_client or create_model_client()

    async def diagnose(
        self,
        evidence_bundle: EvidenceBundle,
        worker_outputs: dict[str, Any],
    ) -> DiagnosisOutput:
        """Run M3 diagnosis over the complete evidence bundle and worker outputs."""

        # Prepare the complete evidence bundle for M3
        evidence_for_m3 = self._prepare_m3_evidence(evidence_bundle, worker_outputs)

        # Load system prompt
        system_prompt = get_m3_diagnosis_prompt()

        # Build user prompt
        user_prompt = self._build_user_prompt(evidence_for_m3)

        # Call M3 model with structured output
        try:
            result = await self._model_client.generate(
                prompt=user_prompt,
                system_prompt=system_prompt,
                temperature=0.1,
                max_tokens=4096,
                response_schema=DiagnosisOutput,
            )
            return result  # type: ignore[return-value]
        except Exception as e:
            raise M3DiagnosisError(f"M3 diagnosis failed: {e}") from e

    def _prepare_m3_evidence(
        self, bundle: EvidenceBundle, worker_outputs: dict[str, Any]
    ) -> dict[str, Any]:
        """Prepare the complete evidence package for M3."""
        return {
            "incident": bundle.incident.model_dump(),
            "overall": bundle.overall.model_dump(),
            "temporal": [t.model_dump() for t in bundle.temporal],
            "baseline_daily": [b.model_dump() for b in bundle.baseline_daily],
            "payment_methods": [m.model_dump() for m in bundle.payment_methods],
            "cohorts": [c.model_dump() for c in bundle.cohorts],
            "failure_reasons": [r.model_dump() for r in bundle.failure_reasons],
            "monetary": bundle.monetary.model_dump(),
            "anomaly": bundle.anomaly.model_dump(),
            "worker_findings": {
                k: v.model_dump() if hasattr(v, "model_dump") else v
                for k, v in worker_outputs.items()
            },
        }

    def _build_user_prompt(self, evidence: dict[str, Any]) -> str:
        return (
            "You are the Senior Financial Doctor (M3). Analyze the complete evidence bundle "
            "and M2.7 worker findings below. Produce a senior diagnosis with hypothesis ranking, "
            "leading hypothesis, and recommended intervention.\n\n"
            "EVIDENCE BUNDLE:\n"
            f"{json.dumps(evidence, indent=2, default=str)}"
        )


async def run_m3_diagnosis(
    evidence_bundle: EvidenceBundle,
    worker_outputs: dict[str, Any],
    model_client=None,
) -> DiagnosisOutput:
    """Convenience function to run M3 diagnosis."""
    diagnoser = M3Diagnoser(model_client)
    return await diagnoser.diagnose(evidence_bundle, worker_outputs)