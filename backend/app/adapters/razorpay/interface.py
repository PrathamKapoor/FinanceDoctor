"""RazorpayAdapter interface (Protocol).

This is the abstraction that the rest of Financial Doctor depends on.
Both StubRazorpayAdapter and LiveRazorpayAdapter implement this protocol.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import AsyncIterator
from typing import Protocol

from backend.app.adapters.razorpay.models import (
    NormalizedCustomer,
    NormalizedOrder,
    NormalizedPayment,
    NormalizedPaymentLink,
    NormalizedRefund,
    NormalizedSettlement,
    NormalizedWebhookEvent,
)


class RazorpayAdapter(Protocol):
    """Abstract interface for Razorpay operations.

    All methods return normalized domain models. Raw provider payloads
    are never exposed beyond the adapter layer.
    """

    # --- Read operations ---

    async def list_payments(
        self,
        *,
        from_ts: dt.datetime | None = None,
        to_ts: dt.datetime | None = None,
        count: int = 100,
        skip: int = 0,
    ) -> AsyncIterator[NormalizedPayment]:
        """Iterate over payments with optional time filtering and pagination."""
        ...

    async def get_payment(self, payment_id: str) -> NormalizedPayment | None:
        """Fetch a single payment by Razorpay ID."""
        ...

    async def list_orders(
        self,
        *,
        from_ts: dt.datetime | None = None,
        to_ts: dt.datetime | None = None,
        count: int = 100,
        skip: int = 0,
    ) -> AsyncIterator[NormalizedOrder]:
        """Iterate over orders with optional time filtering and pagination."""
        ...

    async def get_order(self, order_id: str) -> NormalizedOrder | None:
        """Fetch a single order by Razorpay ID."""
        ...

    async def get_order_payments(self, order_id: str) -> AsyncIterator[NormalizedPayment]:
        """Fetch all payments for a specific order."""
        ...

    async def list_customers(
        self,
        *,
        from_ts: dt.datetime | None = None,
        to_ts: dt.datetime | None = None,
        count: int = 100,
        skip: int = 0,
    ) -> AsyncIterator[NormalizedCustomer]:
        """Iterate over customers with optional time filtering and pagination."""
        ...

    async def get_customer(self, customer_id: str) -> NormalizedCustomer | None:
        """Fetch a single customer by Razorpay ID."""
        ...

    async def list_payment_links(
        self,
        *,
        from_ts: dt.datetime | None = None,
        to_ts: dt.datetime | None = None,
        count: int = 100,
        skip: int = 0,
    ) -> AsyncIterator[NormalizedPaymentLink]:
        """Iterate over payment links with optional time filtering and pagination."""
        ...

    async def get_payment_link(self, link_id: str) -> NormalizedPaymentLink | None:
        """Fetch a single payment link by Razorpay ID."""
        ...

    async def list_refunds(
        self,
        *,
        from_ts: dt.datetime | None = None,
        to_ts: dt.datetime | None = None,
        count: int = 100,
        skip: int = 0,
    ) -> AsyncIterator[NormalizedRefund]:
        """Iterate over refunds with optional time filtering and pagination."""
        ...

    async def get_refund(self, refund_id: str) -> NormalizedRefund | None:
        """Fetch a single refund by Razorpay ID."""
        ...

    async def get_payment_refunds(self, payment_id: str) -> AsyncIterator[NormalizedRefund]:
        """Fetch all refunds for a specific payment."""
        ...

    async def list_settlements(
        self,
        *,
        from_ts: dt.datetime | None = None,
        to_ts: dt.datetime | None = None,
        count: int = 100,
        skip: int = 0,
    ) -> AsyncIterator[NormalizedSettlement]:
        """Iterate over settlements with optional time filtering and pagination."""
        ...

    async def get_settlement(self, settlement_id: str) -> NormalizedSettlement | None:
        """Fetch a single settlement by Razorpay ID."""
        ...

    # --- Write operations (MVP: only create_payment_link is verified) ---

    async def create_payment_link(
        self,
        *,
        amount_minor: int,
        currency: str = "INR",
        reference_id: str,
        description: str | None = None,
        customer_name: str | None = None,
        customer_email: str | None = None,
        customer_phone: str | None = None,
        expire_by: int | None = None,  # Unix timestamp
        notify_sms: bool = True,
        notify_email: bool = True,
        reminder_enable: bool = True,
        notes: dict[str, str] | None = None,
        callback_url: str | None = None,
        callback_method: str = "get",
        accept_partial: bool = False,
        first_min_partial_amount: int | None = None,
    ) -> NormalizedPaymentLink:
        """Create a standard Payment Link for re-collection.

        This is the ONLY verified write operation for the MVP.
        Idempotency is achieved via `reference_id` (must be unique per link).
        """
        ...

    # --- Webhook handling ---

    def verify_webhook_signature(
        self, payload: bytes, signature: str, secret: str | None = None
    ) -> bool:
        """Verify HMAC SHA256 webhook signature.

        Returns True if valid, False otherwise. Does not raise.
        """
        ...

    def parse_webhook(self, payload: dict) -> NormalizedWebhookEvent:
        """Parse raw webhook payload into normalized event.

        Does NOT verify signature — caller must call verify_webhook_signature first.
        """
        ...

    # --- Lifecycle ---

    async def close(self) -> None:
        """Close any underlying connections (e.g., HTTP client)."""
        ...