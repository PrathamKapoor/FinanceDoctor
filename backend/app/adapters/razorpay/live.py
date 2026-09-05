"""LiveRazorpayAdapter — HTTP client for real Razorpay API.

This adapter makes actual HTTP calls to the Razorpay API.
It implements the same RazorpayAdapter protocol as the stub.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import hmac
from collections.abc import AsyncIterator
from typing import Any

import httpx
from backend.app.adapters.razorpay.exceptions import (
    ProviderConflictError,
    normalize_razorpay_error,
)
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

RAZORPAY_BASE_URL = "https://api.razorpay.com/v1"
DEFAULT_TIMEOUT = 30.0
MAX_COUNT = 100


def _map_payment_status(status: str) -> PaymentStatus:
    mapping = {
        "created": PaymentStatus.CREATED,
        "authorized": PaymentStatus.AUTHORIZED,
        "captured": PaymentStatus.CAPTURED,
        "failed": PaymentStatus.FAILED,
        "refunded": PaymentStatus.REFUNDED,
    }
    return mapping.get(status.lower(), PaymentStatus.FAILED)


def _map_payment_method(method: str | None) -> PaymentMethod:
    if not method:
        return PaymentMethod.OTHER
    m = method.lower()
    if "upi" in m:
        return PaymentMethod.UPI
    if "card" in m:
        return PaymentMethod.CARD
    if "netbanking" in m or "net_banking" in m:
        return PaymentMethod.NETBANKING
    if "wallet" in m:
        return PaymentMethod.WALLET
    if "emi" in m:
        return PaymentMethod.EMI
    if "paylater" in m or "pay_later" in m:
        return PaymentMethod.PAY_LATER
    return PaymentMethod.OTHER


def _map_order_status(status: str):
    from backend.app.adapters.razorpay.models import OrderStatus
    mapping = {
        "created": OrderStatus.CREATED,
        "paid": OrderStatus.PAID,
        "attempted": OrderStatus.ATTEMPTED,
        "failed": OrderStatus.FAILED,
    }
    return mapping.get(status.lower(), OrderStatus.CREATED)


def _map_payment_link_status(status: str) -> PaymentLinkStatus:
    mapping = {
        "created": PaymentLinkStatus.CREATED,
        "paid": PaymentLinkStatus.PAID,
        "partially_paid": PaymentLinkStatus.PARTIALLY_PAID,
        "expired": PaymentLinkStatus.EXPIRED,
        "cancelled": PaymentLinkStatus.CANCELLED,
    }
    return mapping.get(status.lower(), PaymentLinkStatus.CREATED)


def _map_refund_status(status: str) -> RefundStatus:
    mapping = {
        "created": RefundStatus.CREATED,
        "processed": RefundStatus.PROCESSED,
        "failed": RefundStatus.FAILED,
    }
    return mapping.get(status.lower(), RefundStatus.CREATED)


def _map_settlement_status(status: str) -> SettlementStatus:
    mapping = {
        "created": SettlementStatus.CREATED,
        "processed": SettlementStatus.PROCESSED,
        "failed": SettlementStatus.FAILED,
    }
    return mapping.get(status.lower(), SettlementStatus.CREATED)


class LiveRazorpayAdapter:
    """Live HTTP adapter for Razorpay API."""

    def __init__(
        self,
        key_id: str,
        key_secret: str,
        webhook_secret: str,
        base_url: str = RAZORPAY_BASE_URL,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        self._key_id = key_id
        self._key_secret = key_secret
        self._webhook_secret = webhook_secret
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._client: httpx.AsyncClient | None = None

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self._base_url,
                auth=(self._key_id, self._key_secret),
                timeout=httpx.Timeout(self._timeout),
                headers={"Content-Type": "application/json", "User-Agent": "FinancialDoctor/0.1"},
            )
        return self._client

    def _handle_error(self, response: httpx.Response) -> None:
        try:
            data = response.json()
            error = data.get("error", {})
            code = error.get("code")
            description = error.get("description")
            details = error.get("metadata")
        except Exception:
            code = None
            description = response.text
            details = None

        raise normalize_razorpay_error(response.status_code, code, description, details)

    # --- Read operations ---

    async def list_payments(
        self,
        *,
        from_ts: dt.datetime | None = None,
        to_ts: dt.datetime | None = None,
        count: int = MAX_COUNT,
        skip: int = 0,
    ) -> AsyncIterator[NormalizedPayment]:
        params: dict[str, Any] = {"count": min(count, MAX_COUNT), "skip": skip}
        if from_ts:
            params["from"] = int(from_ts.timestamp())
        if to_ts:
            params["to"] = int(to_ts.timestamp())

        client = self._get_client()
        while True:
            response = await client.get("/payments", params=params)
            if response.status_code != 200:
                self._handle_error(response)
            data = response.json()
            items = data.get("items", [])
            if not items:
                break
            for item in items:
                yield self._normalize_payment(item)
            if len(items) < params["count"]:
                break
            params["skip"] += len(items)

    async def get_payment(self, payment_id: str) -> NormalizedPayment | None:
        client = self._get_client()
        response = await client.get(f"/payments/{payment_id}")
        if response.status_code == 404:
            return None
        if response.status_code != 200:
            self._handle_error(response)
        return self._normalize_payment(response.json())

    async def list_orders(
        self,
        *,
        from_ts: dt.datetime | None = None,
        to_ts: dt.datetime | None = None,
        count: int = MAX_COUNT,
        skip: int = 0,
    ) -> AsyncIterator[NormalizedOrder]:
        params: dict[str, Any] = {"count": min(count, MAX_COUNT), "skip": skip}
        if from_ts:
            params["from"] = int(from_ts.timestamp())
        if to_ts:
            params["to"] = int(to_ts.timestamp())

        client = self._get_client()
        while True:
            response = await client.get("/orders", params=params)
            if response.status_code != 200:
                self._handle_error(response)
            data = response.json()
            items = data.get("items", [])
            if not items:
                break
            for item in items:
                yield self._normalize_order(item)
            if len(items) < params["count"]:
                break
            params["skip"] += len(items)

    async def get_order(self, order_id: str) -> NormalizedOrder | None:
        client = self._get_client()
        response = await client.get(f"/orders/{order_id}")
        if response.status_code == 404:
            return None
        if response.status_code != 200:
            self._handle_error(response)
        return self._normalize_order(response.json())

    async def get_order_payments(self, order_id: str) -> AsyncIterator[NormalizedPayment]:
        client = self._get_client()
        response = await client.get(f"/orders/{order_id}/payments")
        if response.status_code != 200:
            self._handle_error(response)
        data = response.json()
        for item in data.get("items", []):
            yield self._normalize_payment(item)

    async def list_customers(
        self,
        *,
        from_ts: dt.datetime | None = None,
        to_ts: dt.datetime | None = None,
        count: int = MAX_COUNT,
        skip: int = 0,
    ) -> AsyncIterator[NormalizedCustomer]:
        params: dict[str, Any] = {"count": min(count, MAX_COUNT), "skip": skip}
        if from_ts:
            params["from"] = int(from_ts.timestamp())
        if to_ts:
            params["to"] = int(to_ts.timestamp())

        client = self._get_client()
        while True:
            response = await client.get("/customers", params=params)
            if response.status_code != 200:
                self._handle_error(response)
            data = response.json()
            items = data.get("items", [])
            if not items:
                break
            for item in items:
                yield self._normalize_customer(item)
            if len(items) < params["count"]:
                break
            params["skip"] += len(items)

    async def get_customer(self, customer_id: str) -> NormalizedCustomer | None:
        client = self._get_client()
        response = await client.get(f"/customers/{customer_id}")
        if response.status_code == 404:
            return None
        if response.status_code != 200:
            self._handle_error(response)
        return self._normalize_customer(response.json())

    async def list_payment_links(
        self,
        *,
        from_ts: dt.datetime | None = None,
        to_ts: dt.datetime | None = None,
        count: int = MAX_COUNT,
        skip: int = 0,
    ) -> AsyncIterator[NormalizedPaymentLink]:
        params: dict[str, Any] = {"count": min(count, MAX_COUNT), "skip": skip}
        if from_ts:
            params["from"] = int(from_ts.timestamp())
        if to_ts:
            params["to"] = int(to_ts.timestamp())

        client = self._get_client()
        while True:
            response = await client.get("/payment_links", params=params)
            if response.status_code != 200:
                self._handle_error(response)
            data = response.json()
            items = data.get("items", [])
            if not items:
                break
            for item in items:
                yield self._normalize_payment_link(item)
            if len(items) < params["count"]:
                break
            params["skip"] += len(items)

    async def get_payment_link(self, link_id: str) -> NormalizedPaymentLink | None:
        client = self._get_client()
        response = await client.get(f"/payment_links/{link_id}")
        if response.status_code == 404:
            return None
        if response.status_code != 200:
            self._handle_error(response)
        return self._normalize_payment_link(response.json())

    async def list_refunds(
        self,
        *,
        from_ts: dt.datetime | None = None,
        to_ts: dt.datetime | None = None,
        count: int = MAX_COUNT,
        skip: int = 0,
    ) -> AsyncIterator[NormalizedRefund]:
        params: dict[str, Any] = {"count": min(count, MAX_COUNT), "skip": skip}
        if from_ts:
            params["from"] = int(from_ts.timestamp())
        if to_ts:
            params["to"] = int(to_ts.timestamp())

        client = self._get_client()
        while True:
            response = await client.get("/refunds", params=params)
            if response.status_code != 200:
                self._handle_error(response)
            data = response.json()
            items = data.get("items", [])
            if not items:
                break
            for item in items:
                yield self._normalize_refund(item)
            if len(items) < params["count"]:
                break
            params["skip"] += len(items)

    async def get_refund(self, refund_id: str) -> NormalizedRefund | None:
        client = self._get_client()
        response = await client.get(f"/refunds/{refund_id}")
        if response.status_code == 404:
            return None
        if response.status_code != 200:
            self._handle_error(response)
        return self._normalize_refund(response.json())

    async def get_payment_refunds(self, payment_id: str) -> AsyncIterator[NormalizedRefund]:
        client = self._get_client()
        response = await client.get(f"/payments/{payment_id}/refunds")
        if response.status_code != 200:
            self._handle_error(response)
        data = response.json()
        for item in data.get("items", []):
            yield self._normalize_refund(item)

    async def list_settlements(
        self,
        *,
        from_ts: dt.datetime | None = None,
        to_ts: dt.datetime | None = None,
        count: int = MAX_COUNT,
        skip: int = 0,
    ) -> AsyncIterator[NormalizedSettlement]:
        params: dict[str, Any] = {"count": min(count, MAX_COUNT), "skip": skip}
        if from_ts:
            params["from"] = int(from_ts.timestamp())
        if to_ts:
            params["to"] = int(to_ts.timestamp())

        client = self._get_client()
        while True:
            response = await client.get("/settlements", params=params)
            if response.status_code != 200:
                self._handle_error(response)
            data = response.json()
            items = data.get("items", [])
            if not items:
                break
            for item in items:
                yield self._normalize_settlement(item)
            if len(items) < params["count"]:
                break
            params["skip"] += len(items)

    async def get_settlement(self, settlement_id: str) -> NormalizedSettlement | None:
        client = self._get_client()
        response = await client.get(f"/settlements/{settlement_id}")
        if response.status_code == 404:
            return None
        if response.status_code != 200:
            self._handle_error(response)
        return self._normalize_settlement(response.json())

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
        payload: dict[str, Any] = {
            "amount": amount_minor,
            "currency": currency,
            "reference_id": reference_id,
        }
        if description:
            payload["description"] = description
        if customer_name or customer_email or customer_phone:
            payload["customer"] = {}
            if customer_name:
                payload["customer"]["name"] = customer_name
            if customer_email:
                payload["customer"]["email"] = customer_email
            if customer_phone:
                payload["customer"]["contact"] = customer_phone
        if expire_by:
            payload["expire_by"] = expire_by
        payload["notify"] = {"sms": notify_sms, "email": notify_email}
        payload["reminder_enable"] = reminder_enable
        if notes:
            payload["notes"] = notes
        if callback_url:
            payload["callback_url"] = callback_url
            payload["callback_method"] = callback_method
        if accept_partial:
            payload["accept_partial"] = True
            if first_min_partial_amount:
                payload["first_min_partial_amount"] = first_min_partial_amount

        client = self._get_client()
        response = await client.post("/payment_links", json=payload)
        if response.status_code == 409:
            raise ProviderConflictError("Payment link with this reference_id already exists")
        if response.status_code not in (200, 201):
            self._handle_error(response)

        return self._normalize_payment_link(response.json())

    # --- Webhook handling ---

    def verify_webhook_signature(
        self, payload: bytes, signature: str, secret: str | None = None
    ) -> bool:
        expected = hmac.new(
            (secret or self._webhook_secret).encode(),
            payload,
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(expected, signature)

    def parse_webhook(self, payload: dict) -> NormalizedWebhookEvent:
        return NormalizedWebhookEvent(
            event=payload.get("event", "unknown"),
            payload=payload.get("payload", {}),
            raw=payload,
        )

    # --- Normalization helpers ---

    def _normalize_payment(self, data: dict) -> NormalizedPayment:
        return NormalizedPayment(
            provider_id=data["id"],
            order_id=data.get("order_id"),
            customer_id=data.get("customer_id"),
            amount_minor=data["amount"],
            currency=data["currency"],
            status=_map_payment_status(data["status"]),
            method=_map_payment_method(data.get("method")),
            error_code=data.get("error_code"),
            error_description=data.get("error_description"),
            fee_minor=data.get("fee"),
            tax_minor=data.get("tax"),
            created_at=dt.datetime.fromtimestamp(data["created_at"], tz=dt.UTC),
            captured_at=(
                dt.datetime.fromtimestamp(data["captured_at"], tz=dt.UTC)
                if data.get("captured_at")
                else None
            ),
            raw=data,
        )

    def _normalize_order(self, data: dict) -> NormalizedOrder:
        return NormalizedOrder(
            provider_id=data["id"],
            amount_minor=data["amount"],
            currency=data["currency"],
            status=_map_order_status(data["status"]),
            amount_paid_minor=data.get("amount_paid", 0),
            amount_due_minor=data.get("amount_due", 0),
            attempts=data.get("attempts", 0),
            created_at=dt.datetime.fromtimestamp(data["created_at"], tz=dt.UTC),
            raw=data,
        )

    def _normalize_customer(self, data: dict) -> NormalizedCustomer:
        return NormalizedCustomer(
            provider_id=data["id"],
            name=data.get("name"),
            email=data.get("email"),
            phone=data.get("contact"),
            created_at=dt.datetime.fromtimestamp(data["created_at"], tz=dt.UTC),
            raw=data,
        )

    def _normalize_payment_link(self, data: dict) -> NormalizedPaymentLink:
        customer_data = data.get("customer") or {}
        return NormalizedPaymentLink(
            provider_id=data["id"],
            reference_id=data.get("reference_id"),
            amount_minor=data["amount"],
            amount_paid_minor=data.get("amount_paid", 0),
            currency=data["currency"],
            status=_map_payment_link_status(data["status"]),
            short_url=data.get("short_url"),
            customer=NormalizedCustomer(
                provider_id=customer_data.get("id", ""),
                name=customer_data.get("name"),
                email=customer_data.get("email"),
                phone=customer_data.get("contact"),
                created_at=(
                dt.datetime.fromtimestamp(customer_data["created_at"], tz=dt.UTC)
                if customer_data.get("created_at")
                else dt.datetime.utcnow()
            ),
            ) if customer_data else None,
            description=data.get("description"),
            expire_at=(
                dt.datetime.fromtimestamp(data["expire_by"], tz=dt.UTC)
                if data.get("expire_by")
                else None
            ),
            created_at=dt.datetime.fromtimestamp(data["created_at"], tz=dt.UTC),
            raw=data,
        )

    def _normalize_refund(self, data: dict) -> NormalizedRefund:
        return NormalizedRefund(
            provider_id=data["id"],
            payment_id=data["payment_id"],
            amount_minor=data["amount"],
            currency=data["currency"],
            status=_map_refund_status(data["status"]),
            speed_processed=data.get("speed_processed"),
            created_at=dt.datetime.fromtimestamp(data["created_at"], tz=dt.UTC),
            processed_at=(
                dt.datetime.fromtimestamp(data["processed_at"], tz=dt.UTC)
                if data.get("processed_at")
                else None
            ),
            raw=data,
        )

    def _normalize_settlement(self, data: dict) -> NormalizedSettlement:
        return NormalizedSettlement(
            provider_id=data["id"],
            amount_minor=data["amount"],
            currency=data["currency"],
            status=_map_settlement_status(data["status"]),
            fee_minor=data.get("fee", 0),
            tax_minor=data.get("tax", 0),
            created_at=dt.datetime.fromtimestamp(data["created_at"], tz=dt.UTC),
            processed_at=(
                dt.datetime.fromtimestamp(data["processed_at"], tz=dt.UTC)
                if data.get("processed_at")
                else None
            ),
            raw=data,
        )

    # --- Lifecycle ---

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None