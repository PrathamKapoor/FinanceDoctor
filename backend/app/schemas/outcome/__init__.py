"""Outcome domain schemas - closed-loop observation and measurement layer.

The schemas in this package model the *measured result* of a previously
executed recovery action. The Financial Doctor declares success — or
failure — based on the patient's outcome, not the prescription.

The schemas are intentionally side-effect free. Deterministic arithmetic
lives in ``backend.app.services.outcome``; this module defines structure.
"""