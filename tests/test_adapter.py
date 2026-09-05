"""Tests for Razorpay adapter (stub implementation, normalization, webhooks, idempotency)."""

from __future__ import annotations

import hashlib
import hmac

import pytest
from backend.app.adapters.razorpay import (
    NormalizedPaymentLink,
    NormalizedWebhookEvent,
    PaymentLinkStatus,
    StubRazorpayAdapter,
)
from backend.app.adapters.razorpay.webhook import _generate_event_id
from backend.app.services.synthetic_data import SyntheticMerchantConfig, generate_merchant_world


@pytest.fixture
def synthetic_world():
    """Small synthetic world for testing."""
    config = SyntheticMerchantConfig(
        seed=42,
        num_customers=50,
        num_orders=100,
        baseline_days=7,
    )
    return generate_merchant_world(config)


@pytest.fixture
def adapter(synthetic_world):
    return StubRazorpayAdapter(synthetic_world)


class TestStubAdapterReadOperations:
    """Test read operations against synthetic world."""

    @pytest.mark.asyncio
    async def test_list_payments(self, adapter):
        payments = []
        async for p in adapter.list_payments(count=10):
            payments.append(p)
        assert len(payments) == 10
        assert all(p.provider_id.startswith("pay_") for p in payments)
        assert all(p.amount_minor > 0 for p in payments)

    @pytest.mark.asyncio
    async def test_get_payment(self, adapter):
        payment = None
        async for p in adapter.list_payments(count=1):
            payment = p
            break
        assert payment is not None

        fetched = await adapter.get_payment(payment.provider_id)
        assert fetched is not None
        assert fetched.provider_id == payment.provider_id
        assert fetched.amount_minor == payment.amount_minor

    @pytest.mark.asyncio
    async def test_get_payment_not_found(self, adapter):
        result = await adapter.get_payment("pay_nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_list_orders(self, adapter):
        orders = []
        async for o in adapter.list_orders(count=5):
            orders.append(o)
        assert len(orders) == 5
        assert all(o.provider_id.startswith("order_") for o in orders)

    @pytest.mark.asyncio
    async def test_list_customers(self, adapter):
        customers = []
        async for c in adapter.list_customers(count=3):
            customers.append(c)
        assert len(customers) == 3
        assert all(c.provider_id.startswith("cust_") for c in customers)

    @pytest.mark.asyncio
    async def test_list_payment_links_empty(self, adapter):
        links = []
        async for link in adapter.list_payment_links():
            links.append(link)
        assert len(links) == 0

    @pytest.mark.asyncio
    async def test_list_refunds_empty(self, adapter):
        refunds = []
        async for r in adapter.list_refunds():
            refunds.append(r)
        assert len(refunds) == 0

    @pytest.mark.asyncio
    async def test_list_settlements_empty(self, adapter):
        settlements = []
        async for s in adapter.list_settlements():
            settlements.append(s)
        assert len(settlements) == 0


class TestStubAdapterWriteOperations:
    """Test write operations (Payment Link creation)."""

    @pytest.mark.asyncio
    async def test_create_payment_link(self, adapter):
        link = await adapter.create_payment_link(
            amount_minor=50000,  # ₹500
            currency="INR",
            reference_id="test_ref_001",
            description="Test payment link",
            customer_name="John Doe",
            customer_email="john@example.com",
            customer_phone="+919876543210",
        )
        assert isinstance(link, NormalizedPaymentLink)
        assert link.provider_id.startswith("plink_")
        assert link.amount_minor == 50000
        assert link.currency == "INR"
        assert link.reference_id == "test_ref_001"
        assert link.status == PaymentLinkStatus.CREATED
        assert link.short_url is not None
        assert link.short_url.startswith("https://rzp.io/i/")
        assert link.customer is not None
        assert link.customer.name == "John Doe"
        assert link.customer.email == "john@example.com"

    @pytest.mark.asyncio
    async def test_create_payment_link_idempotency(self, adapter):
        """Same reference_id should return existing link."""
        link1 = await adapter.create_payment_link(
            amount_minor=50000,
            reference_id="idempotent_test",
        )
        link2 = await adapter.create_payment_link(
            amount_minor=99999,  # Different amount, should be ignored
            reference_id="idempotent_test",
        )
        assert link1.provider_id == link2.provider_id
        assert link1.amount_minor == link2.amount_minor

    @pytest.mark.asyncio
    async def test_payment_link_persisted(self, adapter):
        link = await adapter.create_payment_link(
            amount_minor=10000,
            reference_id="persist_test",
        )
        fetched = await adapter.get_payment_link(link.provider_id)
        assert fetched is not None
        assert fetched.provider_id == link.provider_id
        assert fetched.reference_id == link.reference_id

    @pytest.mark.asyncio
    async def test_payment_link_webhook_event_emitted(self, adapter):
        """Creating a payment link should emit a webhook event."""
        initial_count = len(adapter._events)
        await adapter.create_payment_link(
            amount_minor=10000,
            reference_id="event_test",
        )
        assert len(adapter._events) == initial_count + 1
        event = adapter._events[-1]
        assert event.event == "payment_link.created"
        assert event.payload["payment_link_id"] is not None


class TestWebhookHandling:
    """Test webhook signature verification, parsing, and deduplication."""

    def test_verify_webhook_signature_valid(self, adapter):
        payload = b'{"event": "payment.failed", "payload": {}}'
        secret = "test_webhook_secret"
        signature = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
        assert adapter.verify_webhook_signature(payload, signature, secret) is True

    def test_verify_webhook_signature_invalid(self, adapter):
        payload = b'{"event": "payment.failed"}'
        secret = "test_webhook_secret"
        signature = "invalidsignature"
        assert adapter.verify_webhook_signature(payload, signature, secret) is False

    def test_verify_webhook_signature_wrong_secret(self, adapter):
        payload = b'{"event": "payment.failed"}'
        signature = hmac.new(b"wrong_secret", payload, hashlib.sha256).hexdigest()
        assert adapter.verify_webhook_signature(payload, signature, "test_webhook_secret") is False

    def test_parse_webhook(self, adapter):
        payload = {
            "event": "payment.failed",
            "payload": {"payment": {"entity": {"id": "pay_123", "status": "failed"}}},
        }
        event = adapter.parse_webhook(payload)
        assert isinstance(event, NormalizedWebhookEvent)
        assert event.event == "payment.failed"
        assert event.payload == payload["payload"]

    def test_webhook_deduplication(self, adapter):
        """Same event should be deduplicated."""
        event = NormalizedWebhookEvent(
            event="payment.failed",
            payload={"payment": {"id": "pay_123"}},
        )
        id1 = _generate_event_id(event)
        id2 = _generate_event_id(event)
        assert id1 == id2

    def test_webhook_different_events_different_ids(self, adapter):
        event1 = NormalizedWebhookEvent(
            event="payment.failed",
            payload={"payment": {"id": "pay_123"}},
        )
        event2 = NormalizedWebhookEvent(
            event="payment.captured",
            payload={"payment": {"id": "pay_123"}},
        )
        assert _generate_event_id(event1) != _generate_event_id(event2)


class TestNormalization:
    """Test normalized model construction."""

    @pytest.mark.asyncio
    async def test_normalized_payment_link_fields(self, adapter):
        link = await adapter.create_payment_link(
            amount_minor=25000,
            reference_id="norm_test",
        )
        # All required fields present
        assert link.provider_id
        assert link.reference_id == "norm_test"
        assert link.amount_minor == 25000
        assert link.currency == "INR"
        assert link.status.value == "created"
        assert link.short_url
        assert link.customer is not None
        assert link.expire_at is not None
        assert link.created_at is not None


class TestIdempotency:
    """Test idempotency guarantees."""

    @pytest.mark.asyncio
    async def test_create_payment_link_same_reference_returns_same(self, adapter):
        """Idempotency key is reference_id."""
        link1 = await adapter.create_payment_link(
            amount_minor=10000,
            reference_id="idem_001",
        )
        link2 = await adapter.create_payment_link(
            amount_minor=20000,  # Different amount
            reference_id="idem_001",  # Same reference_id
        )
        assert link1.provider_id == link2.provider_id
        assert link1.amount_minor == link2.amount_minor  # First one wins

    @pytest.mark.asyncio
    async def test_idempotency_key_is_reference_id(self, adapter):
        """Only reference_id matters for idempotency."""
        await adapter.create_payment_link(
            amount_minor=10000,
            reference_id="idem_002",
        )
        # Different amount, same reference_id -> same link
        link2 = await adapter.create_payment_link(
            amount_minor=50000,
            reference_id="idem_002",
        )
        link3 = await adapter.create_payment_link(
            amount_minor=50000,
            reference_id="idem_002",
        )
        assert link2.provider_id == link3.provider_id


class TestSyncAdapterContract:
    """Verify the stub implements the full interface."""

    @pytest.mark.asyncio
    async def test_all_read_methods_exist(self, adapter):
        """All read methods are implemented and callable."""
        methods = [
            "list_payments", "get_payment", "list_orders", "get_order",
            "get_order_payments", "list_customers", "get_customer",
            "list_payment_links", "get_payment_link",
            "list_refunds", "get_refund", "get_payment_refunds",
            "list_settlements", "get_settlement",
        ]
        for method_name in methods:
            assert hasattr(adapter, method_name)
            method = getattr(adapter, method_name)
            assert callable(method)

    @pytest.mark.asyncio
    async def test_write_methods_exist(self, adapter):
        """Write methods exist."""
        assert hasattr(adapter, "create_payment_link")
        assert callable(adapter.create_payment_link)

    @pytest.mark.asyncio
    async def test_webhook_methods_exist(self, adapter):
        """Webhook methods exist."""
        assert hasattr(adapter, "verify_webhook_signature")
        assert hasattr(adapter, "parse_webhook")
        assert callable(adapter.verify_webhook_signature)
        assert callable(adapter.parse_webhook)

    @pytest.mark.asyncio
    async def test_close_exists(self, adapter):
        """Close method exists."""
        assert hasattr(adapter, "close")
        await adapter.close()  # Should not raise


class TestLiveAdapterSmoke:
    """Smoke test that live adapter can be instantiated (without network calls)."""

    def test_live_adapter_instantiation(self):
        from backend.app.adapters.razorpay import LiveRazorpayAdapter
        adapter = LiveRazorpayAdapter(
            key_id="test_key",
            key_secret="test_secret",
            webhook_secret="test_webhook_secret",
        )
        assert adapter._key_id == "test_key"
        assert adapter._webhook_secret == "test_webhook_secret"