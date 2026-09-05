"""Demo case orchestration — a deterministic, read-oriented wrapper that wires
Stages 1–5 into a single case journey the Stage 6 UI renders.

This package does **not** redesign the Stage 1–5 architecture. It re-uses the
same service objects the golden closed-loop test exercises (analytics, workers,
M3, planner, policy engine, approval service, executor, outcome layer) and
exposes them through a safe, single `DemoCaseSession` the frontend consumes.
"""