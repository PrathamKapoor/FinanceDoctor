"""Consultation service (Stage 7A).

READ-ONLY by construction. This module imports no action, approval, adapter,
policy, or outcome-mutation code — there is deliberately nothing here a
prompt-injected model could invoke. The data flow is strictly:

```text
CaseView dict → ConsultationContextBuilder → context
    → StubModelClient template (demo) | MiniMax M3 structured output (live)
    → validated ConsultationResponse (+ history record)
```

Stub mode answers deterministically from context values (no hallucinated
numbers possible). Live mode validates schema, answer type, sections, and
₹-amount grounding, falling back to the deterministic template on ANY
failure — the case UI keeps working when the model does not.
"""

from __future__ import annotations

import re
import time
from typing import Any

from pydantic import BaseModel, Field

from backend.app.services.consultation.context_builder import (
    ConsultationContextBuilder,
)
from backend.app.services.consultation.models import (
    AnswerType,
    ConsultationContext,
    ConsultationRecord,
    ConsultationResponse,
    ConsultationSection,
    ConsultationTimings,
)
from backend.app.services.consultation.prompt_builder import (
    CONSULT_SYSTEM_PROMPT,
    build_user_prompt,
)


class ConsultationError(Exception):
    """Base consultation failure (model/speech/provider problems)."""


class ConsultValidationError(ConsultationError):
    """The question itself is unusable (empty / too long)."""


class ConsultRateLimited(ConsultationError):
    """Per-case cooldown tripped."""


class ConsultConfig(BaseModel):
    """Consultation boundaries (cost control + abuse control)."""

    cooldown_seconds: float = 2.0
    max_question_chars: int = 1000
    max_answer_chars: int = 4000
    history_cap: int = 50
    model_timeout_seconds: float = 60.0


class _LiveConsultationOutput(BaseModel):
    """Structured output contract for the live consultation model."""

    answer: str = Field(..., min_length=1, max_length=4000)
    answer_type: str = "general"
    referenced_sections: list[str] = Field(default_factory=list)


# ---- intent routing (stub + live fallback share the refusal detector) ----

_REFUSAL_VERBS = (
    "approve", "reject", "execute", "send", "create", "skip", "bypass",
    "ignore", "recover", "retry", "refund", "run", "trigger", "perform",
    "authoriz", "authoris", "cancel", "do it",
)
_REFUSAL_FRAMES = (
    "please ", "can you ", "could you ", "would you ", "will you ",
    "i want you to", "you should", "just do", "go ahead",
)


def _is_action_request(question: str) -> bool:
    q = f" {question.strip().lower()} "
    starts_imperative = q.lstrip().startswith(_REFUSAL_VERBS)
    framed = any(f in q and any(v in q for v in _REFUSAL_VERBS) for f in _REFUSAL_FRAMES)
    return starts_imperative or framed


def _classify(question: str) -> AnswerType:
    q = question.lower()
    if _is_action_request(question):
        return AnswerType.REFUSED
    if any(k in q for k in ("polic", "approv", "human", "why can't", "why cant",
                            "just send", "safet", "permission", "allow you")):
        return AnswerType.SAFETY
    if any(k in q for k in ("did it work", "did the treatment", "did it help",
                            "outcome", "result", "recovered", "paid", "work?")):
        return AnswerType.OUTCOME
    if any(k in q for k in ("recommend", "treatment", "prescrib", "action",
                            "link", "target")):
        return AnswerType.TREATMENT
    if any(k in q for k in ("evidence", "why do you think", "method", "upi",
                            "compar", "proof", "support")):
        return AnswerType.EVIDENCE
    if any(k in q for k in ("why", "cause", "reason", "diagnos", "root")):
        return AnswerType.DIAGNOSIS
    if any(k in q for k in ("what happened", "what went wrong", "what's wrong",
                            "symptom", "spike", "failure rate", "anomal",
                            "detect", "overview", "summar", "tell me")):
        return AnswerType.INCIDENT
    return AnswerType.GENERAL


_SECTIONS: dict[AnswerType, list[ConsultationSection]] = {
    AnswerType.INCIDENT: [ConsultationSection.INCIDENT, ConsultationSection.METRICS],
    AnswerType.DIAGNOSIS: [ConsultationSection.DIAGNOSIS, ConsultationSection.EVIDENCE,
                           ConsultationSection.INVESTIGATION],
    AnswerType.EVIDENCE: [ConsultationSection.EVIDENCE, ConsultationSection.DIAGNOSIS],
    AnswerType.TREATMENT: [ConsultationSection.TREATMENT, ConsultationSection.APPROVAL,
                           ConsultationSection.EXECUTION],
    AnswerType.SAFETY: [ConsultationSection.POLICY, ConsultationSection.APPROVAL,
                        ConsultationSection.TREATMENT],
    AnswerType.OUTCOME: [ConsultationSection.OUTCOME, ConsultationSection.EXECUTION],
    AnswerType.GENERAL: [ConsultationSection.INCIDENT, ConsultationSection.DIAGNOSIS,
                         ConsultationSection.OUTCOME],
    AnswerType.REFUSED: [],
}

_REFUSAL_TEXT = (
    "I can explain the current treatment and its status, but I cannot approve, "
    "execute, or modify financial actions through the consultation interface. "
    "Approvals and execution happen only through the controlled interface "
    "after human review."
)


def _na(value: Any) -> str:
    return str(value) if value not in (None, "") else "not available"


def _evidence_lookup(evidence: list[dict[str, Any]], evidence_id: str) -> dict[str, Any]:
    for e in evidence:
        if e.get("id") == evidence_id:
            return e
    return {}


def _fmt_rate(value: Any) -> str:
    try:
        return f"{float(value) * 100:.2f}%"
    except (TypeError, ValueError):
        return "not available"


def _render_answer(answer_type: AnswerType, ctx: ConsultationContext) -> str:
    """Deterministic stub answer composed ONLY from context values."""
    inc, diag = ctx.incident, ctx.diagnosis
    act, pol, appr, exe, out = (ctx.recommended_action, ctx.policy_status,
                                ctx.approval_status, ctx.execution_status, ctx.outcome)

    if answer_type == AnswerType.REFUSED:
        return _REFUSAL_TEXT

    if answer_type == AnswerType.INCIDENT:
        return (
            f"On {_na(inc.get('start_time'))}, your payment failure rate rose from a "
            f"{_na(inc.get('baseline_failure_rate'))} baseline to "
            f"{_na(inc.get('current_failure_rate'))} — about a "
            f"{_na(inc.get('relative_increase'))} increase across "
            f"{_na(inc.get('sample_size'))} attempts. The anomaly score was "
            f"{_na(inc.get('anomaly_score'))} against a threshold of "
            f"{_na(inc.get('anomaly_threshold'))}, so the system flagged a "
            f"{_na(inc.get('incident_type'))} concentrated in "
            f"{_na(inc.get('affected_value'))}."
        )

    if answer_type == AnswerType.DIAGNOSIS:
        alts = diag.get("alternative_hypotheses", []) or []
        alt_txt = "; ".join(
            f"{a.get('hypothesis')} (score {a.get('score')})" for a in alts
        ) or "none recorded"
        unc = "; ".join(diag.get("uncertainties", []) or []) or "none recorded"
        ev = ", ".join(diag.get("supporting_evidence_ids", []) or []) or "none recorded"
        return (
            f"The leading diagnosis is {_na(diag.get('leading_hypothesis'))}, at "
            f"{_na(diag.get('confidence'))} model-assessed confidence. Supporting "
            f"evidence: {ev}. Alternatives considered: {alt_txt}. Open "
            f"uncertainties: {unc}."
        )

    if answer_type == AnswerType.EVIDENCE:
        upi = _evidence_lookup(ctx.evidence, "payment_method.UPI.failure_rate")
        card = _evidence_lookup(ctx.evidence, "payment_method.CARD.failure_rate")
        net = _evidence_lookup(ctx.evidence, "payment_method.NETBANKING.failure_rate")
        wallet = _evidence_lookup(ctx.evidence, "payment_method.WALLET.failure_rate")
        reason = _evidence_lookup(ctx.evidence, "failure_reason.distribution")
        reason_txt = ""
        if isinstance(reason.get("value"), dict) and reason["value"]:
            top = max(reason["value"].items(), key=lambda kv: kv[1])
            reason_txt = f" {top[0]} caused most of those failures."
        return (
            f"UPI failed at {_fmt_rate(upi.get('value'))} versus a "
            f"{_fmt_rate(upi.get('baseline'))} baseline, while CARD "
            f"({_fmt_rate(card.get('value'))}), NETBANKING "
            f"({_fmt_rate(net.get('value'))}) and WALLET "
            f"({_fmt_rate(wallet.get('value'))}) stayed near baseline.{reason_txt} "
            f"See evidence payment_method.UPI.failure_rate."
        )

    if answer_type == AnswerType.TREATMENT:
        return (
            f"The recommendation is {_na(act.get('action_type'))} for "
            f"{_na(act.get('targets_count'))} eligible targets totaling "
            f"{_na(act.get('total_amount'))}: {_na(act.get('rationale'))} Approval "
            f"is currently {_na(appr.get('status'))} and execution is "
            f"{_na(exe.get('status'))}."
        )

    if answer_type == AnswerType.SAFETY:
        checks = pol.get("checks", []) or []
        return (
            f"The AI only recommends. Every financial action must pass "
            f"{len(checks)} deterministic policy checks — currently "
            f"{_na(pol.get('decision'))} — and then be explicitly approved by a "
            f"human; right now approval is {_na(appr.get('status'))}. I cannot "
            f"approve, send, or execute anything from this consultation."
        )

    if answer_type == AnswerType.OUTCOME:
        if not out.get("present"):
            return (
                "There is no treatment outcome yet because "
                f"execution is {_na(exe.get('status'))} and approval is "
                f"{_na(appr.get('status'))}."
            )
        return (
            f"The treatment status is {_na(out.get('status'))}: "
            f"{_na(out.get('targets_succeeded'))} of {_na(out.get('targets_total'))} "
            f"targets recovered {_na(out.get('amount_recovered'))} of "
            f"{_na(out.get('amount_targeted'))} "
            f"({_na(out.get('conversion_rate'))}). "
            f"{_na(out.get('targets_pending'))} targets are still pending."
        )

    # GENERAL — compact whole-case summary.
    return (
        f"This case is a {_na(inc.get('incident_type'))}: failure rate rose from "
        f"{_na(inc.get('baseline_failure_rate'))} to "
        f"{_na(inc.get('current_failure_rate'))}. Leading diagnosis: "
        f"{_na(diag.get('leading_hypothesis'))}. Treatment "
        f"{_na(act.get('action_type'))} is {_na(appr.get('status'))} for approval, "
        f"and the outcome is {_na(out.get('status'))}."
    )


_RUPEE_TOKEN = re.compile(r"₹\s?([0-9][0-9,]*)")


def _allowed_amounts(ctx: ConsultationContext) -> set[str]:
    allowed = set()
    for v in ctx.key_figures.values():
        s = v.replace("₹", "").replace(",", "").replace(" ", "")
        if s and all(ch.isdigit() or ch == "." for ch in s):
            allowed.add(s)
    return allowed


def _check_rupee_grounding(answer: str, ctx: ConsultationContext) -> None:
    """Every ₹ amount in a live answer must exactly match a context figure."""
    allowed = _allowed_amounts(ctx)
    for raw in _RUPEE_TOKEN.findall(answer):
        if raw.replace(",", "") not in allowed:
            raise ConsultationError(
                f"Unverified monetary value in model answer: ₹{raw}"
            )


class ConsultService:
    """Case-scoped, read-only consultation over an existing ``CaseView``."""

    def __init__(
        self,
        model_client: Any | None = None,
        config: ConsultConfig | None = None,
        model_name: str | None = None,
    ) -> None:
        if model_client is None:
            from backend.app.agents.models import create_model_client

            model_client = create_model_client()
        from backend.app.agents.models import StubModelClient

        self._client = model_client
        self._is_stub = isinstance(model_client, StubModelClient)
        self._config = config or ConsultConfig()
        if model_name is None:
            # Attribute live answers to the configured model; stubs stay "stub".
            model_name = getattr(
                getattr(model_client, "config", None), "minimax_m3_model", "live"
            )
        self._model_name = "stub" if self._is_stub else model_name
        self._builder = ConsultationContextBuilder()

    async def consult(
        self,
        case_view: dict[str, Any],
        question: str,
        *,
        history: list[dict[str, Any]],
        last_at: float | None,
    ) -> tuple[ConsultationResponse, float]:
        """Answer one question. Returns (response, new_last_at).

        ``history`` is mutated in place (append + cap) — it is consultation
        metadata scoped to the case, never financial state.
        """

        started = time.perf_counter()
        q = (question or "").strip()
        if not q:
            raise ConsultValidationError("Question must not be empty")
        if len(q) > self._config.max_question_chars:
            raise ConsultValidationError(
                f"Question exceeds {self._config.max_question_chars} characters"
            )
        now = time.monotonic()
        if last_at is not None and now - last_at < self._config.cooldown_seconds:
            raise ConsultRateLimited("Consultation cooldown active; please wait")

        t0 = time.perf_counter()
        ctx = self._builder.build(case_view)
        context_ms = int((time.perf_counter() - t0) * 1000)

        if self._is_stub:
            answer_type = _classify(q)
            answer = _render_answer(answer_type, ctx)
            model_ms = 0
            model = "stub"
        else:
            answer, answer_type, model_ms, model = await self._live_answer(ctx, q)
        total_ms = int((time.perf_counter() - started) * 1000)

        response = ConsultationResponse(
            case_id=ctx.case_id,
            question=q,
            answer=answer[: self._config.max_answer_chars],
            answer_type=answer_type,
            referenced_sections=list(_SECTIONS[answer_type]),
            model=model,
            timings=ConsultationTimings(
                context_build_ms=context_ms,
                model_latency_ms=model_ms,
                total_latency_ms=total_ms,
            ),
        )
        record = ConsultationRecord(
            consultation_id=response.consultation_id,
            case_id=response.case_id,
            question=response.question,
            answer=response.answer,
            answer_type=response.answer_type,
            referenced_sections=response.referenced_sections,
            model=response.model,
        )
        history.append(record.model_dump(mode="json"))
        del history[: max(0, len(history) - self._config.history_cap)]
        return response, now

    async def _live_answer(
        self, ctx: ConsultationContext, question: str
    ) -> tuple[str, AnswerType, int, str]:
        """M3 structured consultation with validation + ₹ grounding + fallback."""
        t0 = time.perf_counter()
        try:
            raw = await self._client.generate(
                prompt=build_user_prompt(ctx, question),
                system_prompt=CONSULT_SYSTEM_PROMPT,
                temperature=0.2,
                max_tokens=800,
                response_schema=_LiveConsultationOutput,
            )
            if not isinstance(raw, _LiveConsultationOutput):
                raise ConsultationError("unstructured model output")
            answer = raw.answer.strip()[: self._config.max_answer_chars]
            try:
                answer_type = AnswerType(raw.answer_type.lower())
            except ValueError:
                answer_type = _classify(question)
            _check_rupee_grounding(answer, ctx)
            model_ms = int((time.perf_counter() - t0) * 1000)
            return answer, answer_type, model_ms, self._model_name
        except Exception:
            # ANY live failure degrades to the deterministic template.
            # The case UI keeps working; the answer stays grounded.
            answer_type = _classify(question)
            answer = _render_answer(answer_type, ctx)
            model_ms = int((time.perf_counter() - t0) * 1000)
            return answer, answer_type, model_ms, "stub"


__all__ = [
    "ConsultConfig",
    "ConsultService",
    "ConsultValidationError",
    "ConsultRateLimited",
    "ConsultationError",
]
