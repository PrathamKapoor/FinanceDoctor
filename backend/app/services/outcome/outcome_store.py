"""In-memory stores for outcomes, target outcomes, and audit events.

The Stage 4 pipeline uses dict-based in-memory stores for actions,
snapshots, and approvals. Stage 5 follows the same pattern for the
closed-loop observation layer. These stores are intentionally
process-local — production should swap them for a persistent backend;
the public API is the contract.
"""

from __future__ import annotations

import threading

from backend.app.schemas.outcome.audit import AuditEvent
from backend.app.schemas.outcome.intervention_outcome import InterventionOutcome
from backend.app.schemas.outcome.target_outcome import RecoveryTargetOutcome


class OutcomeStore:
    """Thread-safe in-memory store for intervention outcomes + target outcomes."""

    def __init__(self) -> None:
        self._outcomes: dict[str, InterventionOutcome] = {}
        self._targets: dict[str, RecoveryTargetOutcome] = {}
        self._targets_by_payment_link: dict[str, str] = {}  # plink_id -> target_outcome_id
        self._targets_by_payment_id: dict[str, list[str]] = {}  # pay_id -> [target_outcome_id]
        self._outcomes_by_action: dict[str, str] = {}  # action_id -> outcome_id
        self._lock = threading.RLock()

    # ---- Outcomes ----

    def save_outcome(self, outcome: InterventionOutcome) -> InterventionOutcome:
        with self._lock:
            self._outcomes[outcome.outcome_id] = outcome
            self._outcomes_by_action[outcome.action_id] = outcome.outcome_id
            return outcome

    def get_outcome(self, outcome_id: str) -> InterventionOutcome | None:
        with self._lock:
            return self._outcomes.get(outcome_id)

    def get_outcome_by_action(self, action_id: str) -> InterventionOutcome | None:
        with self._lock:
            oid = self._outcomes_by_action.get(action_id)
            return self._outcomes.get(oid) if oid else None

    def list_outcomes(self) -> list[InterventionOutcome]:
        with self._lock:
            return list(self._outcomes.values())

    # ---- Targets ----

    def save_target(self, target: RecoveryTargetOutcome) -> RecoveryTargetOutcome:
        with self._lock:
            self._targets[target.target_outcome_id] = target
            if target.payment_link_id:
                self._targets_by_payment_link[target.payment_link_id] = target.target_outcome_id
            self._targets_by_payment_id.setdefault(target.payment_id, []).append(
                target.target_outcome_id
            )
            return target

    def get_target(self, target_outcome_id: str) -> RecoveryTargetOutcome | None:
        with self._lock:
            return self._targets.get(target_outcome_id)

    def get_target_by_payment_link(self, payment_link_id: str) -> RecoveryTargetOutcome | None:
        with self._lock:
            tid = self._targets_by_payment_link.get(payment_link_id)
            return self._targets.get(tid) if tid else None

    def list_targets_for_outcome(self, outcome_id: str) -> list[RecoveryTargetOutcome]:
        with self._lock:
            return [t for t in self._targets.values() if t.outcome_id == outcome_id]

    def list_targets_for_payment(self, payment_id: str) -> list[RecoveryTargetOutcome]:
        with self._lock:
            return [
                self._targets[tid]
                for tid in self._targets_by_payment_id.get(payment_id, [])
                if tid in self._targets
            ]

    def list_all_targets(self) -> list[RecoveryTargetOutcome]:
        with self._lock:
            return list(self._targets.values())

    # ---- Bookkeeping ----

    def clear(self) -> None:
        with self._lock:
            self._outcomes.clear()
            self._targets.clear()
            self._targets_by_payment_link.clear()
            self._targets_by_payment_id.clear()
            self._outcomes_by_action.clear()


class AuditStore:
    """Thread-safe in-memory audit event store."""

    def __init__(self) -> None:
        self._events: list[AuditEvent] = []
        self._lock = threading.RLock()
        # Indexed by event_type + entity_id for fast lookup, and by
        # provider event id for idempotency.
        self._index_by_entity: dict[tuple[str, str], list[str]] = {}
        self._index_by_reference: dict[str, list[str]] = {}
        self._index_by_audit: dict[str, str] = {}

    def record(self, event: AuditEvent) -> AuditEvent:
        with self._lock:
            self._events.append(event)
            self._index_by_entity.setdefault(
                (event.entity_type, event.entity_id), []
            ).append(event.audit_id)
            if event.reference_id:
                self._index_by_reference.setdefault(event.reference_id, []).append(
                    event.audit_id
                )
            self._index_by_audit[event.audit_id] = event.audit_id
            return event

    def list_all(self) -> list[AuditEvent]:
        with self._lock:
            return list(self._events)

    def list_for_entity(self, entity_type: str, entity_id: str) -> list[AuditEvent]:
        with self._lock:
            ids = self._index_by_entity.get((entity_type, entity_id), [])
            return [e for e in self._events if e.audit_id in ids]

    def list_for_reference(self, reference_id: str) -> list[AuditEvent]:
        with self._lock:
            ids = self._index_by_reference.get(reference_id, [])
            return [e for e in self._events if e.audit_id in ids]

    def clear(self) -> None:
        with self._lock:
            self._events.clear()
            self._index_by_entity.clear()
            self._index_by_reference.clear()
            self._index_by_audit.clear()


# Process-local default instances — tests construct their own.
_default_outcome_store: OutcomeStore | None = None
_default_audit_store: AuditStore | None = None


def get_default_outcome_store() -> OutcomeStore:
    global _default_outcome_store
    if _default_outcome_store is None:
        _default_outcome_store = OutcomeStore()
    return _default_outcome_store


def get_default_audit_store() -> AuditStore:
    global _default_audit_store
    if _default_audit_store is None:
        _default_audit_store = AuditStore()
    return _default_audit_store


def reset_default_stores() -> None:
    """Test helper — clears default singletons."""
    global _default_outcome_store, _default_audit_store
    _default_outcome_store = None
    _default_audit_store = None


__all__ = [
    "OutcomeStore",
    "AuditStore",
    "get_default_outcome_store",
    "get_default_audit_store",
    "reset_default_stores",
]