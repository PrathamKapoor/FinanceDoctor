"""Case orchestration facade for Stage 6.

``CaseController`` is a thin public facade over the demo-session runner. It
drives the closed Financial Doctor loop through the existing Stage 1–5
services and exposes the deterministic read model the case-experience UI
renders. It never rebuilds state with an LLM and never executes an action
outside the policy → approval → executor boundary.
"""

from __future__ import annotations

from typing import Any

from backend.app.services.demo.read_model import build_read_model
from backend.app.services.demo.session import (
    DemoCaseSession,
    DemoSessionStore,
    run_demo_case,
)


class CaseController:
    """Deterministic driver for a single Financial Doctor case.

    Start a case to run Stage 1–5 up to the human-approval gate; mutations
    flow through the demo-case HTTP API (approve / reject / execute /
    simulate).
    """

    def __init__(self, store: DemoSessionStore) -> None:
        self._store = store

    async def start(
        self,
        *,
        seed: int | None = None,
        num_orders: int | None = None,
        num_customers: int | None = None,
    ) -> DemoCaseSession:
        session = await run_demo_case(
            seed=seed, num_orders=num_orders, num_customers=num_customers
        )
        return self._store.put(session)

    def read_model(self, session: DemoCaseSession) -> dict[str, Any]:
        return build_read_model(session)


__all__ = ["CaseController"]