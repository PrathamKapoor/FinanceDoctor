"""Outcome-layer services.

This package owns the deterministic observation and measurement layer
for the closed-loop Financial Doctor pipeline. No LLM code lives here;
all amounts are integer minor units; all transitions are validated by
the tables in :mod:`backend.app.schemas.outcome.enums`.
"""