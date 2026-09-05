"""Case orchestration services for Stage 6.

``CaseController`` drives the closed Financial Doctor loop through the
existing Stage 1-5 services and exposes a deterministic read model for
the case-experience UI.

It is deliberately the *only* first-party way to advance a case over
HTTP. Every mutation step reuses the real Stage 4/5 services (policy,
approval, executor, outcome evaluator, webhook handler). The read model
is assembled from stored deterministic state — never rebuilt by an LLM,
never executing an action.
"""

from backend.app.services.case.case_controller import CaseController

__all__ = ["CaseController"]