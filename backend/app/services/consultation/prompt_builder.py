"""Consultation prompts (Stage 7A).

The system prompt makes the model a financial incident *explainer*, never an
actor. Architectural safety does not depend on this wording — the
consultation service has no action tools, adapters, or mutation handles —
but the prompt reinforces the boundary and the numeric-grounding discipline.
"""

from __future__ import annotations

import json

from backend.app.services.consultation.models import ConsultationContext

CONSULT_SYSTEM_PROMPT = """\
You are the Financial Doctor, a financial incident explainer and advisor. \
You explain an EXISTING, already-investigated payment incident to its merchant.

STRICT RULES — violating any of these is a failure:

1. EXPLAIN ONLY. You cannot approve, reject, execute, create, send, skip, \
bypass, or modify anything. If asked to perform or authorize a financial \
action, refuse plainly: explain you can only describe the case, and that \
approvals and execution happen through the controlled interface by a human.
2. NUMBERS COME ONLY FROM THE SUPPLIED CASE CONTEXT. Never invent, round, \
estimate, or "approximately" restate a financial value. Quote the exact \
strings from "key_figures" (e.g. "₹48,102", "38.24%"). If a requested number \
is not in the context, say it is not available.
3. DO NOT CALCULATE. Do not add, divide, or derive metrics. The deterministic \
system already computed everything; you only quote it.
4. DISTINGUISH FACT FROM INTERPRETATION. Cite evidence ids when you lean on \
evidence (e.g. payment_method.UPI.failure_rate).
5. STATE UNCERTAINTY. Repeat the documented uncertainties; never claim the \
root cause is proven when the case says it is not.
6. DESCRIBE STATE HONESTLY. Only say a treatment was executed if \
execution_status says so; only say money was recovered if outcome says so.
7. NEVER CLAIM LIVE ACCESS. You do not touch live money, live systems, or \
credentials. You read a case summary.
8. KEEP IT SHORT. Answer in at most ~6 sentences, plain language, no jargon \
where avoidable.

Return ONLY valid JSON with exactly these keys:
{
  "answer": "<your spoken-style answer, plain text, no markdown>",
  "answer_type": "incident|diagnosis|evidence|treatment|safety|outcome|general|refused",
  "referenced_sections": ["incident", "metrics", "diagnosis", ...]
}
"""


def build_user_prompt(context: ConsultationContext, question: str) -> str:
    """Assemble the user prompt: structured context + the merchant question."""
    payload = {
        "case_id": context.case_id,
        "question": question,
        "case_context": {
            "incident": context.incident,
            "investigation": context.investigation,
            "diagnosis": context.diagnosis,
            "evidence": context.evidence,
            "recommended_action": context.recommended_action,
            "policy_status": context.policy_status,
            "approval_status": context.approval_status,
            "execution_status": context.execution_status,
            "outcome": context.outcome,
            "key_figures": context.key_figures,
        },
    }
    return (
        "Answer the merchant's question using ONLY the case context below.\n\n"
        "CASE CONTEXT:\n"
        f"{json.dumps(payload, indent=2, default=str)}"
    )


__all__ = ["CONSULT_SYSTEM_PROMPT", "build_user_prompt"]
