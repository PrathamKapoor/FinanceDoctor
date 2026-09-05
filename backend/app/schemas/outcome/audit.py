"""Outcome-layer audit events.

Stage 5 extends the existing audit discipline with structured events
that capture every state transition on an outcome or target outcome.
Provider events use ``actor=PROVIDER``; deterministic transitions use
``actor=SYSTEM``; human-driven finalization uses ``actor=HUMAN``.
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from pydantic import BaseModel, Field

from backend.app.schemas.outcome.enums import AuditActor, AuditEventType


class AuditEvent(BaseModel):
    """A single structured audit event."""

    audit_id: str = Field(default_factory=lambda: f"aud_{uuid.uuid4().hex[:12]}")
    event_type: AuditEventType
    actor: AuditActor
    entity_type: str = Field(..., description="entity class (outcome, target_outcome)")
    entity_id: str = Field(..., description="entity ID")
    previous_state: str | None = Field(default=None, description="Prior status")
    new_state: str | None = Field(default=None, description="New status")
    reason: str | None = Field(default=None, description="Provider reference / reason")
    reference_id: str | None = Field(default=None, description="Provider event / exec id")
    metadata: dict[str, Any] = Field(default_factory=dict)
    timestamp: dt.datetime = Field(default_factory=dt.datetime.utcnow)