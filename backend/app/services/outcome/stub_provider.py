"""Stub provider simulator for outcome-layer tests.

The Financial Doctor's MVP does not require live Razorpay credentials
to exercise the closed loop. ``StubProviderSimulator`` wraps the
Stage 2 ``StubRazorpayAdapter`` and lets tests simulate exactly the events
that would arrive from a real provider — without bypassing the webhook
boundary.

The simulator:
  - advances internal payment link state (CREATED -> PAID / EXPIRED)
  - builds a verified webhook payload (matching the shape Razorpay
    sends) including the canonical ``payment_link.paid`` payload
  - hands that payload to the :class:`OutcomeWebhookHandler` so the
    *same* production code path executes
"""

from __future__ import annotations

import datetime as dt
import hashlib
import hmac
from typing import Any

from backend.app.adapters.razorpay.models import (
    NormalizedPaymentLink,
    PaymentLinkStatus,
)
from backend.app.adapters.razorpay.stub import StubRazorpayAdapter
from backend.app.schemas.outcome.target_outcome import TargetOutcomeStatus


class StubProviderSimulator:
    """Deterministic simulator for outcome-layer tests."""

    def __init__(self, adapter: StubRazorpayAdapter, webhook_secret: str) -> None:
        self._adapter = adapter
        self._webhook_secret = webhook_secret

    def seed_payment_link(
        self,
        provider_id: str,
        amount_minor: int,
        *,
        reference_id: str | None = None,
    ) -> NormalizedPaymentLink:
        """Insert a pre-existing payment link into the adapter's store.

        Useful for tests that wire outcomes to a known link id without
        going through the async ``create_payment_link`` path.
        """
        link = NormalizedPaymentLink(
            provider_id=provider_id,
            reference_id=reference_id or provider_id,
            amount_minor=amount_minor,
            amount_paid_minor=0,
            currency="INR",
            status=PaymentLinkStatus.CREATED,
            created_at=dt.datetime.utcnow(),
        )
        self._adapter._payment_links[provider_id] = link
        return link

    def mark_payment_link_paid(
        self,
        payment_link_id: str,
        *,
        amount_paid_minor: int | None = None,
    ) -> NormalizedPaymentLink:
        link = self._adapter.lookup_payment_link(payment_link_id)
        if link is None:
            raise KeyError(f"Payment link {payment_link_id} not found")
        link.status = PaymentLinkStatus.PAID
        if amount_paid_minor is not None:
            link.amount_paid_minor = int(amount_paid_minor)
        else:
            link.amount_paid_minor = link.amount_minor
        return link

    def mark_payment_link_expired(self, payment_link_id: str) -> NormalizedPaymentLink:
        link = self._adapter.lookup_payment_link(payment_link_id)
        if link is None:
            raise KeyError(f"Payment link {payment_link_id} not found")
        link.status = PaymentLinkStatus.CANCELLED
        return link

    # ---- Webhook payload generation ----

    def build_payment_link_paid_payload(
        self,
        payment_link_id: str,
        *,
        created_at: dt.datetime | None = None,
    ) -> tuple[dict[str, Any], bytes]:
        """Build a verified ``payment_link.paid`` payload + signed body.

        Returns ``(payload_dict, raw_body)``. The body is what the
        FastAPI webhook endpoint receives; the payload is the parsed
        shape used by ``NormalizedWebhookEvent``. They are equal here
        for the stub, but production providers may differ.
        """
        link = self._adapter.lookup_payment_link(payment_link_id)
        if link is None:
            raise KeyError(f"Payment link {payment_link_id} not found")
        ts = int((created_at or dt.datetime.utcnow()).timestamp())
        payload: dict[str, Any] = {
            "entity": "event",
            "account_id": "acc_test",
            "event": "payment_link.paid",
            "contains": ["payment_link"],
            "payload": {
                "payment_link": {
                    "entity": {
                        "id": link.provider_id,
                        "amount_paid": link.amount_paid_minor or link.amount_minor,
                        "amount": link.amount_minor,
                        "currency": link.currency,
                        "reference_id": link.reference_id,
                        "status": "paid",
                        "created_at": ts,
                    }
                }
            },
            "created_at": ts,
        }
        body = _canonical_payload_bytes(payload)
        return payload, body

    def build_payment_failed_payload(
        self,
        payment_id: str,
        *,
        created_at: dt.datetime | None = None,
    ) -> tuple[dict[str, Any], bytes]:
        ts = int((created_at or dt.datetime.utcnow()).timestamp())
        payload: dict[str, Any] = {
            "entity": "event",
            "event": "payment.failed",
            "contains": ["payment"],
            "payload": {
                "payment": {
                    "entity": {
                        "id": payment_id,
                        "amount": 0,
                        "currency": "INR",
                        "status": "failed",
                        "created_at": ts,
                    }
                }
            },
            "created_at": ts,
        }
        body = _canonical_payload_bytes(payload)
        return payload, body

    def sign_body(self, body: bytes) -> str:
        return hmac.new(
            self._webhook_secret.encode(), body, hashlib.sha256
        ).hexdigest()


def _canonical_payload_bytes(payload: dict[str, Any]) -> bytes:
    """Stable JSON byte representation for HMAC verification.

    Razorpay signs the exact bytes of the body. We use a compact JSON
    serializer so the same payload always produces the same bytes.
    """
    import json

    return json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")


def status_for_target_status(status: TargetOutcomeStatus) -> PaymentLinkStatus:
    """Map a target outcome status to the underlying provider link status."""
    if status == TargetOutcomeStatus.PAID:
        return PaymentLinkStatus.PAID
    if status == TargetOutcomeStatus.EXPIRED:
        return PaymentLinkStatus.CANCELLED
    if status == TargetOutcomeStatus.FAILED:
        return PaymentLinkStatus.CANCELLED
    return PaymentLinkStatus.CREATED


__all__ = ["StubProviderSimulator"]