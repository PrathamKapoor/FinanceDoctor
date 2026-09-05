"""ModelClient abstraction and implementations.

This module provides a provider-independent interface for LLM calls,
with both a live MiniMax implementation and a deterministic stub for testing.
"""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any, Protocol, runtime_checkable

import httpx
from pydantic import BaseModel, Field


@runtime_checkable
class ModelClient(Protocol):
    """Abstract interface for LLM model calls."""

    async def generate(
        self,
        prompt: str,
        *,
        system_prompt: str | None = None,
        temperature: float = 0.1,
        max_tokens: int = 2048,
        response_schema: type[BaseModel] | None = None,
        model: str | None = None,
    ) -> BaseModel | str:
        """Generate a response from the model.

        Args:
            prompt: The user prompt
            system_prompt: Optional system prompt
            temperature: Sampling temperature (0.0-1.0)
            max_tokens: Maximum tokens in response
            response_schema: Optional Pydantic model for structured output
            model: Optional model id override (e.g. M2.7 for workers).
                Defaults to the client's configured model (M3).

        Returns:
            Either a validated Pydantic model (if schema provided) or raw string
        """
        ...

    async def close(self) -> None:
        """Close any underlying connections."""
        ...


class ModelConfig(BaseModel):
    """Configuration for model clients."""

    minimax_m27_model: str = Field(default="MiniMax-M2.7", description="M2.7 model identifier")
    minimax_m3_model: str = Field(default="MiniMax-M3", description="M3 model identifier")
    minimax_api_key: str = Field(default="", description="MiniMax API key")
    minimax_base_url: str = Field(
        default="https://api.minimax.chat/v1", description="MiniMax API base URL"
    )
    minimax_group_id: str = Field(default="", description="MiniMax group ID")
    max_tokens_override: int | None = Field(
        default=None,
        description="Optional ceiling applied to every live request "
        "(env MINIMAX_MAX_TOKENS). Reasoning models need headroom; "
        "unset preserves each caller's budget.",
    )


class StubModelClient:
    """Deterministic stub model client for testing without API calls."""

    def __init__(self, config: ModelConfig | None = None) -> None:
        self.config = config or ModelConfig()
        self._call_log: list[dict[str, Any]] = []

    async def generate(
        self,
        prompt: str,
        *,
        system_prompt: str | None = None,
        temperature: float = 0.1,
        max_tokens: int = 2048,
        response_schema: type[BaseModel] | None = None,
        model: str | None = None,
    ) -> BaseModel | str:
        """Return deterministic stub responses based on prompt content."""
        self._call_log.append(
            {
                "prompt": prompt[:200],
                "system_prompt": system_prompt[:200] if system_prompt else None,
                "temperature": temperature,
                "response_schema": response_schema.__name__ if response_schema else None,
            }
        )

        if response_schema is None:
            return "Stub response"

        # Return deterministic instances based on schema type
        schema_name = response_schema.__name__

        if schema_name == "TemporalWorkerOutput":
            from backend.app.schemas.agent.worker_outputs import (
                SupportedHypothesis,
                TemporalWorkerOutput,
            )
            return TemporalWorkerOutput(
                worker="temporal",
                finding="The anomaly is concentrated in a 3-hour window on 2026-07-31 14:37-17:37. "
                "Baseline daily failure rate mean=0.0476, std=0.0160. Current window rate=0.2175. "
                "Z-score=10.85 indicates a statistically significant temporal spike.",
                evidence_ids=["temporal.anomaly", "baseline_daily.mean", "baseline_daily.std"],
                supports=[SupportedHypothesis.TEMPORAL_SPIKE],
                contradicts=[],
                confidence=0.95,
                anomaly_detected=True,
                peak_window="2026-07-31T14:37:00/2026-07-31T17:37:00",
            )

        if schema_name == "PaymentMethodWorkerOutput":
            from backend.app.schemas.agent.worker_outputs import (
                PaymentMethodWorkerOutput,
                SupportedHypothesis,
            )
            return PaymentMethodWorkerOutput(
                worker="payment_method",
                finding=(
                    "UPI failure rate spiked to 0.3824 (baseline 0.0336, delta=0.3488). "
                    "Other methods (CARD 0.0645, NETBANKING 0.0204, WALLET 0.0) "
                    "remain near baseline. "
                    "90% of UPI failures are NETWORK_ERROR. Strong evidence for "
                    "UPI-specific degradation."
                ),
                evidence_ids=[
                    "payment_method.UPI.failure_rate",
                    "payment_method.UPI.baseline_failure_rate",
                    "payment_method.UPI.delta",
                    "failure_reason.NETWORK_ERROR",
                ],
                supports=[SupportedHypothesis.PAYMENT_METHOD_DEGRADATION],
                contradicts=[
                    SupportedHypothesis.GENERAL_PAYMENT_FAILURE,
                    SupportedHypothesis.CUSTOMER_BEHAVIOR_CHANGE,
                ],
                confidence=0.97,
                affected_methods=["UPI"],
                max_delta=0.3488,
            )

        if schema_name == "CohortWorkerOutput":
            from backend.app.schemas.agent.worker_outputs import (
                CohortWorkerOutput,
                SupportedHypothesis,
            )
            return CohortWorkerOutput(
                worker="cohort",
                finding=(
                    "RETURNING customers show higher failure rate "
                    "(0.2333 vs baseline 0.0449, delta=0.1884) "
                    "than NEW customers (0.1846 vs baseline 0.0462, delta=0.1384). "
                    "Returning bias in incident window suggests cohort-specific impact, "
                    "but both cohorts affected, so not exclusively cohort-driven."
                ),
                evidence_ids=[
                    "cohort.RETURNING.failure_rate",
                    "cohort.RETURNING.baseline_failure_rate",
                    "cohort.RETURNING.delta",
                    "cohort.NEW.failure_rate",
                    "cohort.NEW.delta",
                ],
                supports=[SupportedHypothesis.PAYMENT_METHOD_DEGRADATION],
                contradicts=[SupportedHypothesis.CUSTOMER_BEHAVIOR_CHANGE],
                confidence=0.82,
                affected_cohorts=["RETURNING", "NEW"],
                returning_bias=0.15,
            )

        if schema_name == "FailureReasonWorkerOutput":
            from backend.app.schemas.agent.worker_outputs import (
                FailureReasonWorkerOutput,
                SupportedHypothesis,
            )
            return FailureReasonWorkerOutput(
                worker="failure_reason",
                finding="NETWORK_ERROR accounts for 72/87=82.8% of current failures "
                "(vs ~10% baseline). Strongly correlates with UPI method spike. "
                "Other reasons (BANK_DECLINED, INSUFFICIENT_FUNDS, UNKNOWN) near baseline. "
                "Points to infrastructure/network issue rather than customer-funding issues.",
                evidence_ids=["failure_reason.NETWORK_ERROR", "failure_reason.BANK_DECLINED"],
                supports=[
                    SupportedHypothesis.PAYMENT_METHOD_DEGRADATION,
                    SupportedHypothesis.INFRASTRUCTURE_ISSUE,
                ],
                contradicts=[
                    SupportedHypothesis.CUSTOMER_BEHAVIOR_CHANGE,
                    SupportedHypothesis.FRAUD_SPIKE,
                ],
                confidence=0.94,
                dominant_reason="NETWORK_ERROR",
                dominance_ratio=0.828,
            )

        if schema_name == "DiagnosisOutput":
            from backend.app.schemas.agent.diagnosis import DiagnosisOutput
            return DiagnosisOutput(
                diagnosis_id="diag_001",
                incident_type="PAYMENT_METHOD_FAILURE_SPIKE",
                leading_hypothesis="PAYMENT_METHOD_DEGRADATION",
                confidence=0.91,
                summary=(
                    "A statistically significant payment failure anomaly was detected "
                    "(z=10.85, p<<0.001). "
                    "The anomaly is concentrated in UPI payments during a 3-hour window "
                    "on 2026-07-31. "
                    "UPI failure rate spiked from 3.36% baseline to 38.24% "
                    "(delta=34.88pp). "
                    "90% of UPI failures are NETWORK_ERROR. "
                    "Both NEW and RETURNING cohorts affected, with RETURNING more "
                    "impacted. "
                    "Evidence strongly supports UPI payment-method degradation due to "
                    "network/gateway issue. "
                    "Recommended action: CREATE_PAYMENT_LINK for affected customers."
                ),
                supporting_evidence_ids=[
                    "anomaly.payment_failure_rate",
                    "payment_method.UPI.failure_rate",
                    "payment_method.UPI.delta",
                    "failure_reason.NETWORK_ERROR",
                    "cohort.RETURNING.delta",
                ],
                contradicting_evidence_ids=[],
                alternative_hypotheses=[
                    {
                        "hypothesis": "GENERAL_PAYMENT_FAILURE",
                        "score": 0.05,
                        "reason": "Other payment methods remain near baseline rates",
                    },
                    {
                        "hypothesis": "CUSTOMER_BEHAVIOR_CHANGE",
                        "score": 0.03,
                        "reason": "Both NEW and RETURNING cohorts affected, not cohort-specific",
                    },
                    {
                        "hypothesis": "FRAUD_SPIKE",
                        "score": 0.01,
                        "reason": "Failure reason is NETWORK_ERROR, not fraud indicators",
                    },
                ],
                recommended_action_type="CREATE_PAYMENT_LINK",
                action_rationale=(
                    "Payment Link re-collection is the verified recovery action for "
                    "failed payments. "
                    "Affected UPI customers can be sent new payment links to complete "
                    "their transactions."
                ),
                uncertainties=[
                    "Root cause of NETWORK_ERROR not definitively identified "
                    "(gateway vs network vs bank)",
                    "Duration of degradation unknown - may be transient or persistent",
                ],
            )

        # Default: return a minimal valid instance
        return response_schema()

    async def close(self) -> None:
        pass


def _strip_fences(text: str) -> str:
    """Remove Markdown code fences some providers add around JSON output."""
    s = text.strip()
    if s.startswith("```"):
        lines = s.splitlines()
        lines = lines[1:]  # drop opening fence (``` or ```json)
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        s = "\n".join(lines).strip()
    return s


def _validate_structured(content: str, response_schema: type[BaseModel]) -> BaseModel:
    """Strip fences, parse JSON, and validate against the schema."""
    parsed = json.loads(_strip_fences(content))
    result = response_schema.model_validate(parsed)
    assert isinstance(result, BaseModel)
    return result


def _retry_after_s(response: httpx.Response, attempt: int) -> float:
    """Bounded backoff honoring Retry-After (default 2s, 4s; cap 60s)."""
    try:
        return max(0.0, min(60.0, float(response.headers.get("retry-after", ""))))
    except (TypeError, ValueError):
        return float(2 * (attempt + 1))


class MiniMaxModelClient:
    """Live MiniMax API client for M2.7 and M3 models."""

    def __init__(self, config: ModelConfig) -> None:
        self.config = config
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self):
        if self._client is None:
            import httpx
            self._client = httpx.AsyncClient(
                base_url=self.config.minimax_base_url,
                headers={
                    "Authorization": f"Bearer {self.config.minimax_api_key}",
                    "Content-Type": "application/json",
                },
                timeout=60.0,
            )
        return self._client

    async def generate(
        self,
        prompt: str,
        *,
        system_prompt: str | None = None,
        temperature: float = 0.1,
        max_tokens: int = 2048,
        response_schema: type[BaseModel] | None = None,
        model: str | None = None,
    ) -> BaseModel | str:
        """Call MiniMax API with structured output support."""
        client = await self._get_client()

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": model or self.config.minimax_m3_model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": self.config.max_tokens_override or max_tokens,
        }

        if response_schema:
            # MiniMax supports JSON mode / function calling
            payload["response_format"] = {"type": "json_object"}
            schema_json = response_schema.model_json_schema()
            prompt += f"\n\nReturn ONLY valid JSON matching this schema:\n{json.dumps(schema_json)}"

        # Minimal rate-limit resilience for live demos: retry 429/5xx a
        # bounded number of times honoring Retry-After, then raise as before.
        # Stub and default live behavior are unchanged on success paths.
        response: httpx.Response | None = None
        for _attempt in range(3):
            response = await client.post("/chat/completions", json=payload)
            if response.status_code != 429 and response.status_code < 500:
                break
            if _attempt < 2:
                await asyncio.sleep(_retry_after_s(response, _attempt))
        assert response is not None
        response.raise_for_status()
        data = response.json()

        content = data["choices"][0]["message"]["content"]

        if response_schema:
            try:
                return _validate_structured(content, response_schema)
            except Exception as e1:
                # Bounded repair attempts (max 2): show the model its validation
                # error. Live models sometimes fence JSON or paraphrase closed
                # enums on the first try; corrections usually conform. Still
                # raises afterwards — never an open-ended loop.
                last_error = e1
                current = content
                for _ in range(2):
                    repair_messages = messages + [
                        {"role": "assistant", "content": current},
                        {
                            "role": "user",
                            "content": (
                                "Your previous response was rejected by the schema "
                                f"validator. Error: {last_error}. Return ONLY "
                                "corrected valid JSON matching the required schema. "
                                "Concrete rules: identifiers use underscores only, "
                                "never hyphens (e.g. diag_001); confidence and "
                                "scores must be JSON numbers between 0 and 1, "
                                "never words; use exactly the allowed enum values "
                                "— do not invent new ones; include every required "
                                "field."
                            ),
                        },
                    ]
                    repair = await client.post(
                        "/chat/completions",
                        json={**payload, "messages": repair_messages},
                    )
                    repair.raise_for_status()
                    current = repair.json()["choices"][0]["message"]["content"]
                    try:
                        return _validate_structured(current, response_schema)
                    except Exception as e2:
                        last_error = e2
                raise ValueError(
                    f"Failed to parse model response as "
                    f"{response_schema.__name__}: {last_error}"
                ) from last_error

        return content

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None


def default_m27_model() -> str:
    """M2.7 model id for investigation workers (env-overridable, no guessing)."""
    return os.getenv("MINIMAX_M27_MODEL", "MiniMax-M2.7")


def create_model_client() -> ModelClient:
    """Factory function to create the appropriate model client based on config."""
    raw_override = os.getenv("MINIMAX_MAX_TOKENS", "")
    try:
        max_tokens_override = int(raw_override) if raw_override.strip() else None
    except ValueError:
        max_tokens_override = None
    config = ModelConfig(
        minimax_m27_model=default_m27_model(),
        minimax_m3_model=os.getenv("MINIMAX_M3_MODEL", "MiniMax-M3"),
        minimax_api_key=os.getenv("MINIMAX_API_KEY", ""),
        minimax_base_url=os.getenv("MINIMAX_BASE_URL", "https://api.minimax.chat/v1"),
        minimax_group_id=os.getenv("MINIMAX_GROUP_ID", ""),
        max_tokens_override=max_tokens_override,
    )

    if config.minimax_api_key:
        return MiniMaxModelClient(config)
    return StubModelClient(config)