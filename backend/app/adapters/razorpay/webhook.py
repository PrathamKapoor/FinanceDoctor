"""Razorpay webhook endpoint handler (Stage 2 + Stage 5 wiring).

Stage 2 introduced this endpoint with HMAC verification, normalization,
and deduplication. Stage 5 *extends* the handler:

  - After persisting the ``FinancialEvent`` (Stage 2 contract), the
    handler dispatches the event to the outcome layer's
    :class:`OutcomeWebhookHandler`.
  - The outcome handler re-verifies the signature (defence in depth),
    dedups again, identifies the relevant target outcome, applies a
    deterministic state transition, and re-aggregates the parent
    outcome.

The endpoint NEVER executes an ``ActionExecution``. It is observation
only.
"""

from __future__ import annotations

import hashlib
import hmac
import logging

from backend.app.adapters.razorpay.factory import create_razorpay_adapter
from backend.app.adapters.razorpay.models import NormalizedWebhookEvent
from backend.app.config import get_settings
from backend.app.db.database import get_session
from backend.app.db.models import FinancialEvent
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks/razorpay", tags=["webhooks"])

# In-memory deduplication for webhook events (Stage 2 baseline).
_processed_event_ids: set[str] = set()


def _generate_event_id(event: NormalizedWebhookEvent) -> str:
    """Stage 2 dedup key — used by the FastAPI boundary."""
    payload_str = (
        f"{event.event}:{event.payload.get('payment', {}).get('id', '')}:"
        f"{event.created_at.isoformat()}"
    )
    return hashlib.sha256(payload_str.encode()).hexdigest()[:32]


@router.post("")
async def receive_webhook(
    request: Request,
    x_razorpay_signature: str | None = Header(None, alias="X-Razorpay-Signature"),
    session: Session = Depends(get_session),
) -> dict[str, str]:
    """Receive and process Razorpay webhook events.

    Stage 2 contract:
      - Verifies signature (live mode).
      - Parses + normalizes.
      - Deduplicates.
      - Persists as ``FinancialEvent``.

    Stage 5 extension:
      - Dispatches the same event to the outcome webhook handler.
      - The handler advances target outcome state and re-aggregates
        the parent outcome.
    """
    settings = get_settings()
    mode = getattr(settings, "razorpay_mode", "stub")

    # Read raw body for signature verification
    body = await request.body()
    payload = await request.json()

    webhook_secret = getattr(settings, "razorpay_webhook_secret", "test_webhook_secret")

    # Verify signature in live mode (also available in stub for testing)
    if mode == "live" and x_razorpay_signature:
        expected = hmac.new(
            webhook_secret.encode(),
            body,
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(expected, x_razorpay_signature):
            logger.warning("Invalid webhook signature")
            raise HTTPException(status_code=400, detail="Invalid signature")

    # Parse and normalize via the adapter
    adapter = await create_razorpay_adapter()
    event = adapter.parse_webhook(payload)

    # Stage 2 dedup at the FastAPI boundary
    event_id = _generate_event_id(event)
    if event_id in _processed_event_ids:
        logger.info(f"Duplicate webhook event ignored: {event.event}")
        return {"status": "duplicate"}

    _processed_event_ids.add(event_id)

    # Persist as FinancialEvent (Stage 2 contract)
    financial_event = FinancialEvent(
        source="razorpay",
        event_type=event.event,
        payload=event.raw,
    )
    session.add(financial_event)
    session.commit()

    # Stage 5 dispatch — outcome webhook handler.
    # The handler independently dedups, verifies (when signature
    # supplied), and applies deterministic state transitions.
    outcome_handler = getattr(request.app.state, "webhook_handler", None)
    if outcome_handler is not None:
        outcome_result = outcome_handler.process_event(event)
        logger.info(
            f"Outcome dispatch: event={event.event} -> {outcome_result.get('status')}"
        )

    logger.info(f"Processed webhook: {event.event} (id={event_id})")
    return {"status": "ok"}


@router.get("/health")
def webhook_health() -> dict[str, str]:
    return {"status": "ok", "service": "razorpay-webhook"}