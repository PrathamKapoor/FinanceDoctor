"""Outcome-layer webhook processing.

Stage 2 already implemented the verified Razorpay webhook boundary
(HMAC verification, normalization, deduplication). Stage 5 *reuses*
that boundary: the existing ``/webhooks/razorpay`` endpoint persists
the raw event as a ``FinancialEvent``, and ``OutcomeWebhookHandler``
consumes those events to advance target outcome state.

The handler is responsible for:
  1. verifying HMAC signature (delegated to the Stage 2 boundary)
  2. deduplicating events
  3. identifying the relevant provider resource
  4. locating the associated target outcome
  5. applying a deterministic state transition
  6. re-aggregating the aggregate outcome
  7. recording an audit event

It does NOT execute another ``RazorpayAdapter`` call. It does NOT call
any LLM. It does NOT create another ``ActionExecution``.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import logging
import time
from typing import Any

from backend.app.adapters.razorpay.models import NormalizedWebhookEvent
from backend.app.schemas.outcome.audit import AuditEvent
from backend.app.schemas.outcome.enums import (
    AuditActor,
    AuditEventType,
    TargetOutcomeStatus,
)
from backend.app.schemas.outcome.target_outcome import RecoveryTargetOutcome
from backend.app.services.outcome.outcome_evaluator import OutcomeEvaluator
from backend.app.services.outcome.outcome_store import AuditStore, OutcomeStore

logger = logging.getLogger(__name__)


class WebhookProcessingError(Exception):
    """Raised when an inbound event cannot be processed."""


SUPPORTED_OUTCOME_EVENTS: frozenset[str] = frozenset(
    {
        "payment_link.paid",
        "payment_link.cancelled",
        "payment.captured",
        "payment.failed",
    }
)


class OutcomeWebhookHandler:
    """Consumes verified Razorpay webhook events to update outcomes."""

    def __init__(
        self,
        outcome_store: OutcomeStore,
        audit_store: AuditStore,
        evaluator: OutcomeEvaluator,
        webhook_secret: str,
        *,
        observed_events: list[dict[str, Any]] | None = None,
    ) -> None:
        self._outcomes = outcome_store
        self._audit = audit_store
        self._evaluator = evaluator
        self._webhook_secret = webhook_secret
        self._events_processed: int = 0
        self._events_duplicated: int = 0
        self._events_unrelated: int = 0
        self._events_ignored: int = 0
        self._latency_ms_total: int = 0
        self._latency_samples: int = 0
        self._targets_evaluated: int = 0
        self._observed_events = (
            observed_events if observed_events is not None else []
        )
        self._seen_event_ids: set[str] = set()

    @property
    def metrics(self) -> dict[str, Any]:
        avg = (
            self._latency_ms_total / self._latency_samples
            if self._latency_samples
            else 0.0
        )
        return {
            "events_processed": self._events_processed,
            "events_duplicated": self._events_duplicated,
            "events_unrelated": self._events_unrelated,
            "events_ignored": self._events_ignored,
            "targets_evaluated": self._targets_evaluated,
            "aggregation_latency_ms_avg": avg,
        }

    def verify_signature(self, payload: bytes, signature: str) -> bool:
        expected = hmac.new(
            self._webhook_secret.encode(), payload, hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(expected, signature or "")

    def process_event(self, event: NormalizedWebhookEvent) -> dict[str, Any]:
        """Apply a verified webhook event to the outcome layer."""
        start = time.perf_counter()
        try:
            return self._process_event_inner(event)
        finally:
            elapsed_ms = int((time.perf_counter() - start) * 1000)
            self._latency_ms_total += elapsed_ms
            self._latency_samples += 1

    def process_raw_payload(
        self, raw_payload: dict[str, Any], body: bytes, signature: str | None
    ) -> dict[str, Any]:
        """Convenience: verify HMAC + normalize + process."""
        if signature is not None and not self.verify_signature(body, signature):
            raise WebhookProcessingError("invalid signature")
        event = NormalizedWebhookEvent(
            event=raw_payload.get("event", "unknown"),
            payload=raw_payload.get("payload", {}),
            raw=raw_payload,
        )
        return self.process_event(event)

    # ---- Internals ----

    def _process_event_inner(self, event: NormalizedWebhookEvent) -> dict[str, Any]:
        self._observed_events.append(event.raw)

        event_id = self._event_id(event)
        if event_id in self._seen_event_ids:
            self._events_duplicated += 1
            self._audit.record(
                AuditEvent(
                    event_type=AuditEventType.OUTCOME_WEBHOOK_DUPLICATE,
                    actor=AuditActor.PROVIDER,
                    entity_type="outcome",
                    entity_id="-",
                    previous_state=None,
                    new_state=None,
                    reason=f"duplicate:{event.event}",
                    reference_id=event_id,
                    metadata={"event_id": event_id, "event_type": event.event},
                )
            )
            return {"status": "duplicate", "event_id": event_id}

        if event.event not in SUPPORTED_OUTCOME_EVENTS:
            self._events_ignored += 1
            return {"status": "ignored", "reason": "unsupported_event", "event": event.event}

        link_id, payment_id = self._extract_identifiers(event)
        if not link_id and not payment_id:
            self._events_unrelated += 1
            self._audit.record(
                AuditEvent(
                    event_type=AuditEventType.OUTCOME_WEBHOOK_UNRELATED,
                    actor=AuditActor.PROVIDER,
                    entity_type="outcome",
                    entity_id="-",
                    previous_state=None,
                    new_state=None,
                    reason=f"no resource id in {event.event}",
                    reference_id=event_id,
                    metadata={"event_type": event.event},
                )
            )
            return {"status": "unrelated", "event_id": event_id}

        target = self._locate_target(payment_link_id=link_id, payment_id=payment_id)
        if target is None:
            self._events_unrelated += 1
            self._audit.record(
                AuditEvent(
                    event_type=AuditEventType.OUTCOME_WEBHOOK_UNRELATED,
                    actor=AuditActor.PROVIDER,
                    entity_type="outcome",
                    entity_id="-",
                    previous_state=None,
                    new_state=None,
                    reason=f"no target outcome for {event.event}",
                    reference_id=event_id,
                    metadata={
                        "event_type": event.event,
                        "payment_link_id": link_id,
                        "payment_id": payment_id,
                    },
                )
            )
            return {"status": "unrelated", "event_id": event_id}

        # Record the event id for dedup AFTER we've decided the event
        # is processable. Idempotency: same event id never double-counts.
        self._seen_event_ids.add(event_id)

        previous = target.status
        recovered_amount = self._extract_recovered_amount(event)
        event_at = self._extract_event_at(event)

        # Apply the deterministic transition. If the transition is
        # illegal (target is already terminal, out-of-order event, etc.)
        # we record the attempt as ignored and DO NOT mutate state.
        try:
            if event.event == "payment_link.paid":
                target.transition(
                    TargetOutcomeStatus.PAID,
                    event_id=event_id,
                    event_at=event_at,
                    recovered_amount_minor=recovered_amount,
                )
            elif event.event == "payment.captured":
                target.transition(
                    TargetOutcomeStatus.PAID,
                    event_id=event_id,
                    event_at=event_at,
                    recovered_amount_minor=recovered_amount,
                )
            elif event.event == "payment_link.cancelled":
                target.transition(
                    TargetOutcomeStatus.EXPIRED,
                    event_id=event_id,
                    event_at=event_at,
                )
            elif event.event == "payment.failed":
                target.transition(
                    TargetOutcomeStatus.FAILED,
                    event_id=event_id,
                    event_at=event_at,
                )
            else:
                self._events_ignored += 1
                return {"status": "ignored", "event": event.event}
        except ValueError:
            # Terminal-status overwrite attempt (PAID already, or
            # out-of-order older event). The state must not change.
            self._events_ignored += 1
            return {"status": "ignored", "event": event.event}

        self._events_processed += 1
        self._targets_evaluated += 1

        self._outcomes.save_target(target)
        self._audit.record(
            AuditEvent(
                event_type=(
                    AuditEventType.TARGET_PAYMENT_CONFIRMED
                    if target.status == TargetOutcomeStatus.PAID
                    else AuditEventType.TARGET_MARKED_FAILED
                    if target.status == TargetOutcomeStatus.FAILED
                    else AuditEventType.TARGET_EXPIRED
                ),
                actor=AuditActor.PROVIDER,
                entity_type="target_outcome",
                entity_id=target.target_outcome_id,
                previous_state=previous.value,
                new_state=target.status.value,
                reason=event.event,
                reference_id=event_id,
                metadata={
                    "event_type": event.event,
                    "payment_link_id": target.payment_link_id,
                    "payment_id": target.payment_id,
                    "recovered_amount_minor": target.recovered_amount_minor,
                },
            )
        )

        # Re-aggregate the parent outcome (records its own recalc audit).
        outcome = self._evaluator.recalculate(target.outcome_id)

        return {
            "status": "processed",
            "event_id": event_id,
            "outcome_id": target.outcome_id,
            "target_outcome_id": target.target_outcome_id,
            "target_status": target.status.value,
            "outcome_status": outcome.status.value,
            "amount_recovered_minor": outcome.amount_recovered_minor,
        }

    # ---- Helpers ----

    @staticmethod
    def _event_id(event: NormalizedWebhookEvent) -> str:
        """Deterministic provider-event id for dedup."""
        payload = event.payload or {}
        payment_entity = payload.get("payment", {}) or {}
        payment_link_entity = payload.get("payment_link", {}) or {}
        resource_id = (
            (payment_link_entity.get("entity") or {}).get("id")
            or (payment_entity.get("entity") or {}).get("id")
            or payment_link_entity.get("id")
            or payment_entity.get("id")
            or payload.get("id", "")
        )
        created_at = (
            (payment_entity.get("entity") or {}).get("created_at")
            or (payment_link_entity.get("entity") or {}).get("created_at")
            or payment_entity.get("created_at")
            or payment_link_entity.get("created_at")
            or event.created_at.isoformat()
        )
        key = f"{event.event}:{resource_id}:{created_at}"
        return hashlib.sha256(key.encode()).hexdigest()[:32]

    @staticmethod
    def _extract_identifiers(event: NormalizedWebhookEvent) -> tuple[str | None, str | None]:
        payload = event.payload or {}
        payment_link_entity = payload.get("payment_link", {}) or {}
        payment_entity = payload.get("payment", {}) or {}
        link_id = (
            payment_link_entity.get("id")
            or (payment_link_entity.get("entity") or {}).get("id")
            or payload.get("payment_link_id")
        )
        payment_id = (
            payment_entity.get("id")
            or (payment_entity.get("entity") or {}).get("id")
            or payload.get("payment_id")
        )
        return link_id, payment_id

    @staticmethod
    def _extract_recovered_amount(event: NormalizedWebhookEvent) -> int | None:
        """Extract amount-paid in minor units."""
        payload = event.payload or {}
        pl_entity = payload.get("payment_link", {}) or {}
        if "amount_paid" in pl_entity:
            return int(pl_entity["amount_paid"])
        nested_pl_entity = pl_entity.get("entity") or {}
        if "amount_paid" in nested_pl_entity:
            return int(nested_pl_entity["amount_paid"])
        if "amount_paid" in payload:
            return int(payload["amount_paid"])
        payment_entity = payload.get("payment", {}) or {}
        if event.event == "payment.captured":
            if "amount" in payment_entity:
                return int(payment_entity["amount"])
            nested_payment_entity = payment_entity.get("entity") or {}
            if "amount" in nested_payment_entity:
                return int(nested_payment_entity["amount"])
        return None

    @staticmethod
    def _extract_event_at(event: NormalizedWebhookEvent) -> dt.datetime | None:
        """Best-effort provider event timestamp."""
        payload = event.payload or {}
        for key in ("payment_link", "payment"):
            sub = payload.get(key, {}) or {}
            nested = sub.get("entity") or {}
            ts = nested.get("created_at") or sub.get("created_at")
            if ts is not None:
                if isinstance(ts, (int, float)):
                    return dt.datetime.utcfromtimestamp(int(ts))
                if isinstance(ts, str):
                    try:
                        return dt.datetime.fromisoformat(ts.replace("Z", "+00:00"))
                    except ValueError:
                        continue
        return event.created_at

    def _locate_target(
        self,
        *,
        payment_link_id: str | None,
        payment_id: str | None,
    ) -> RecoveryTargetOutcome | None:
        if payment_link_id:
            target = self._outcomes.get_target_by_payment_link(payment_link_id)
            if target is not None:
                return target
        if payment_id:
            targets = self._outcomes.list_targets_for_payment(payment_id)
            if targets:
                return sorted(targets, key=lambda t: t.created_at, reverse=True)[0]
        return None


__all__ = ["OutcomeWebhookHandler", "SUPPORTED_OUTCOME_EVENTS", "WebhookProcessingError"]
