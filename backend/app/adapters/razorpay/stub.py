"""StubRazorpayAdapter — deterministic adapter backed by Stage 1 synthetic world.

This adapter operates entirely in-memory against the deterministic synthetic
merchant world from Stage 1. It implements the full RazorpayAdapter interface
without any network calls, enabling fast, reproducible tests and demo mode.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import uuid
from collections.abc import AsyncIterator

from backend.app.adapters.razorpay.models import (
    NormalizedCustomer,
    NormalizedOrder,
    NormalizedPayment,
    NormalizedPaymentLink,
    NormalizedRefund,
    NormalizedSettlement,
    NormalizedWebhookEvent,
    PaymentLinkStatus,
    PaymentMethod,
    PaymentStatus,
    RefundStatus,
    SettlementStatus,
)
from backend.app.services.synthetic_data import MerchantWorld


class StubRazorpayAdapter:
    """Deterministic in-memory Razorpay adapter for testing and demo mode."""

    def __init__(self, world: MerchantWorld, webhook_secret: str = "test_webhook_secret") -> None:
        self._world = world
        self._webhook_secret = webhook_secret
        self._payment_links: dict[str, NormalizedPaymentLink] = {}
        self._events: list[NormalizedWebhookEvent] = []
        self._idempotency_keys: dict[str, NormalizedPaymentLink] = {}

    # --- Internal helpers ---

    def _normalize_payment(self, p, order, customer) -> NormalizedPayment:
        method_map = {
            "UPI": PaymentMethod.UPI,
            "CARD": PaymentMethod.CARD,
            "NETBANKING": PaymentMethod.NETBANKING,
            "WALLET": PaymentMethod.WALLET,
        }
        status_map = {
            "CREATED": PaymentStatus.CREATED,
            "AUTHORIZED": PaymentStatus.AUTHORIZED,
            "CAPTURED": PaymentStatus.CAPTURED,
            "FAILED": PaymentStatus.FAILED,
            "REFUNDED": PaymentStatus.REFUNDED,
        }
        return NormalizedPayment(
            provider_id=p.razorpay_payment_id,
            order_id=order.razorpay_order_id if order else None,
            customer_id=customer.razorpay_customer_id if customer else None,
            amount_minor=p.amount_minor,
            currency=p.currency,
            status=status_map.get(p.status.value, PaymentStatus.FAILED),
            method=method_map.get(p.method.value, PaymentMethod.OTHER),
            error_code=p.error_code,
            error_description=p.error_description,
            fee_minor=None,
            tax_minor=None,
            created_at=p.created_at,
            captured_at=p.created_at if p.status.value == "CAPTURED" else None,
            raw={},
        )

    def _normalize_order(self, o, customer) -> NormalizedOrder:
        from backend.app.adapters.razorpay.models import OrderStatus
        status_map = {
            "CREATED": OrderStatus.CREATED,
            "PAID": OrderStatus.PAID,
            "FAILED": OrderStatus.FAILED,
        }
        return NormalizedOrder(
            provider_id=o.razorpay_order_id,
            amount_minor=o.amount_minor,
            currency=o.currency,
            status=status_map.get(o.status.value, OrderStatus.CREATED),
            amount_paid_minor=o.amount_minor if o.status.value == "PAID" else 0,
            amount_due_minor=o.amount_minor if o.status.value != "PAID" else 0,
            attempts=1,
            created_at=o.created_at,
            raw={},
        )

    def _normalize_customer(self, c) -> NormalizedCustomer:
        return NormalizedCustomer(
            provider_id=c.razorpay_customer_id,
            name=c.email.split("@")[0] if c.email else None,
            email=c.email,
            phone=c.phone,
            created_at=c.created_at,
            raw={},
        )

    def _normalize_payment_link(self, pl: NormalizedPaymentLink) -> NormalizedPaymentLink:
        return pl

    def _normalize_refund(self, r) -> NormalizedRefund:
        status_map = {
            "CREATED": RefundStatus.CREATED,
            "PROCESSED": RefundStatus.PROCESSED,
            "FAILED": RefundStatus.FAILED,
        }
        return NormalizedRefund(
            provider_id=(
                r.razorpay_refund_id
                if hasattr(r, "razorpay_refund_id")
                else f"rfd_{uuid.uuid4().hex[:12]}"
            ),
            payment_id=r.payment_id if hasattr(r, "payment_id") else "",
            amount_minor=r.amount_minor if hasattr(r, "amount_minor") else 0,
            currency=r.currency if hasattr(r, "currency") else "INR",
            status=status_map.get(
                r.status.value if hasattr(r, "status") else "PROCESSED", RefundStatus.PROCESSED
            ),
            created_at=r.created_at if hasattr(r, "created_at") else dt.datetime.utcnow(),
            raw={},
        )

    def _normalize_settlement(self, s) -> NormalizedSettlement:
        status_map = {
            "CREATED": SettlementStatus.CREATED,
            "PROCESSED": SettlementStatus.PROCESSED,
            "FAILED": SettlementStatus.FAILED,
        }
        return NormalizedSettlement(
            provider_id=(
                s.razorpay_settlement_id
                if hasattr(s, "razorpay_settlement_id")
                else f"setl_{uuid.uuid4().hex[:12]}"
            ),
            amount_minor=s.amount_minor if hasattr(s, "amount_minor") else 0,
            currency=s.currency if hasattr(s, "currency") else "INR",
            status=status_map.get(
                s.status.value if hasattr(s, "status") else "PROCESSED", SettlementStatus.PROCESSED
            ),
            created_at=s.created_at if hasattr(s, "created_at") else dt.datetime.utcnow(),
            fee_minor=0,
            tax_minor=0,
            raw={},
        )

    # --- Read operations ---

    async def list_payments(
        self,
        *,
        from_ts: dt.datetime | None = None,
        to_ts: dt.datetime | None = None,
        count: int = 100,
        skip: int = 0,
    ) -> AsyncIterator[NormalizedPayment]:
        orders_by_id = {o.id: o for o in self._world.orders}
        customers_by_id = {c.id: c for c in self._world.customers}

        for p in self._world.payments[skip : skip + count]:
            if from_ts and p.created_at < from_ts:
                continue
            if to_ts and p.created_at >= to_ts:
                continue
            order = orders_by_id.get(p.order_id)
            customer = (
                customers_by_id.get(order.customer_id) if order else None
            )
            yield self._normalize_payment(p, order, customer)

    async def get_payment(self, payment_id: str) -> NormalizedPayment | None:
        for p in self._world.payments:
            if p.razorpay_payment_id == payment_id:
                order = next((o for o in self._world.orders if o.id == p.order_id), None)
                customer = (
                    next((c for c in self._world.customers if c.id == order.customer_id), None)
                    if order
                    else None
                )
                return self._normalize_payment(p, order, customer)
        return None

    async def list_orders(
        self,
        *,
        from_ts: dt.datetime | None = None,
        to_ts: dt.datetime | None = None,
        count: int = 100,
        skip: int = 0,
    ) -> AsyncIterator[NormalizedOrder]:
        customers_by_id = {c.id: c for c in self._world.customers}
        for o in self._world.orders[skip : skip + count]:
            if from_ts and o.created_at < from_ts:
                continue
            if to_ts and o.created_at >= to_ts:
                continue
            customer = customers_by_id.get(o.customer_id)
            yield self._normalize_order(o, customer)

    async def get_order(self, order_id: str) -> NormalizedOrder | None:
        for o in self._world.orders:
            if o.razorpay_order_id == order_id:
                customer = next((c for c in self._world.customers if c.id == o.customer_id), None)
                return self._normalize_order(o, customer)
        return None

    async def get_order_payments(self, order_id: str) -> AsyncIterator[NormalizedPayment]:
        order = next((o for o in self._world.orders if o.razorpay_order_id == order_id), None)
        if not order:
            return
        customers_by_id = {c.id: c for c in self._world.customers}
        for p in self._world.payments:
            if p.order_id == order.id:
                customer = customers_by_id.get(order.customer_id)
                yield self._normalize_payment(p, order, customer)

    async def list_customers(
        self,
        *,
        from_ts: dt.datetime | None = None,
        to_ts: dt.datetime | None = None,
        count: int = 100,
        skip: int = 0,
    ) -> AsyncIterator[NormalizedCustomer]:
        for c in self._world.customers[skip : skip + count]:
            if from_ts and c.created_at < from_ts:
                continue
            if to_ts and c.created_at >= to_ts:
                continue
            yield self._normalize_customer(c)

    async def get_customer(self, customer_id: str) -> NormalizedCustomer | None:
        for c in self._world.customers:
            if c.razorpay_customer_id == customer_id:
                return self._normalize_customer(c)
        return None

    async def list_payment_links(
        self,
        *,
        from_ts: dt.datetime | None = None,
        to_ts: dt.datetime | None = None,
        count: int = 100,
        skip: int = 0,
    ) -> AsyncIterator[NormalizedPaymentLink]:
        links = list(self._payment_links.values())[skip : skip + count]
        for pl in links:
            if from_ts and pl.created_at < from_ts:
                continue
            if to_ts and pl.created_at >= to_ts:
                continue
            yield pl

    async def get_payment_link(self, link_id: str) -> NormalizedPaymentLink | None:
        return self._payment_links.get(link_id)

    async def list_refunds(
        self,
        *,
        from_ts: dt.datetime | None = None,
        to_ts: dt.datetime | None = None,
        count: int = 100,
        skip: int = 0,
    ) -> AsyncIterator[NormalizedRefund]:
        # No refunds in synthetic world by default
        return
        yield

    async def get_refund(self, refund_id: str) -> NormalizedRefund | None:
        return None

    async def get_payment_refunds(self, payment_id: str) -> AsyncIterator[NormalizedRefund]:
        return
        yield

    async def list_settlements(
        self,
        *,
        from_ts: dt.datetime | None = None,
        to_ts: dt.datetime | None = None,
        count: int = 100,
        skip: int = 0,
    ) -> AsyncIterator[NormalizedSettlement]:
        # No settlements in synthetic world by default
        return
        yield

    async def get_settlement(self, settlement_id: str) -> NormalizedSettlement | None:
        return None

    # --- Write operations ---

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
        expire_by: int | None = None,
        notify_sms: bool = True,
        notify_email: bool = True,
        reminder_enable: bool = True,
        notes: dict[str, str] | None = None,
        callback_url: str | None = None,
        callback_method: str = "get",
        accept_partial: bool = False,
        first_min_partial_amount: int | None = None,
    ) -> NormalizedPaymentLink:
        # Idempotency: check reference_id
        if reference_id in self._idempotency_keys:
            return self._idempotency_keys[reference_id]

        now = dt.datetime.utcnow()
        expire_ts = expire_by or int((now + dt.timedelta(days=180)).timestamp())

        # Generate deterministic IDs
        link_id = f"plink_{uuid.uuid4().hex[:14]}"
        short_url = f"https://rzp.io/i/{uuid.uuid4().hex[:8]}"

        customer = NormalizedCustomer(
            provider_id=f"cust_{uuid.uuid4().hex[:14]}",
            name=customer_name,
            email=customer_email,
            phone=customer_phone,
            created_at=now,
        )

        link = NormalizedPaymentLink(
            provider_id=link_id,
            reference_id=reference_id,
            amount_minor=amount_minor,
            amount_paid_minor=0,
            currency=currency,
            status=PaymentLinkStatus.CREATED,
            short_url=short_url,
            customer=customer,
            description=description,
            expire_at=dt.datetime.fromtimestamp(expire_ts, tz=dt.UTC),
            created_at=now,
            raw={},
        )

        self._payment_links[link_id] = link
        self._idempotency_keys[reference_id] = link

        # Emit synthetic webhook event for payment_link.created
        event = NormalizedWebhookEvent(
            event="payment_link.created",
            payload={
                "entity": "payment_link",
                "payment_link_id": link_id,
                "reference_id": reference_id,
                "amount": amount_minor,
                "currency": currency,
                "status": "created",
            },
            raw={},
        )
        self._events.append(event)

        return link

    # --- Webhook handling ---

    def verify_webhook_signature(self, payload: bytes, signature: str, secret: str) -> bool:
        expected = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, signature)

    def parse_webhook(self, payload: dict) -> NormalizedWebhookEvent:
        return NormalizedWebhookEvent(
            event=payload.get("event", "unknown"),
            payload=payload.get("payload", {}),
            raw=payload,
        )

    # --- Lifecycle ---

    async def close(self) -> None:
        pass

    def lookup_payment_link(self, link_id: str) -> NormalizedPaymentLink | None:
        """Public accessor for the in-memory payment-link store.

        Exists so the outcome-layer stub simulator can mutate
        payment-link state during closed-loop tests without bypassing
        adapter encapsulation.
        """
        return self._payment_links.get(link_id)