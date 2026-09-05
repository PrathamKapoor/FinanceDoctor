"""Normalized Razorpay domain models.

These models are the internal representation used throughout Financial Doctor.
They are provider-agnostic and contain only fields required by the application.
All monetary amounts are integer minor units.
"""

from __future__ import annotations

import datetime as dt
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class PaymentStatus(StrEnum):
    """Normalized payment status (subset of Razorpay states)."""

    CREATED = "created"
    AUTHORIZED = "authorized"
    CAPTURED = "captured"
    FAILED = "failed"
    REFUNDED = "refunded"


class OrderStatus(StrEnum):
    """Normalized order status."""

    CREATED = "created"
    PAID = "paid"
    ATTEMPTED = "attempted"
    FAILED = "failed"


class PaymentLinkStatus(StrEnum):
    """Normalized payment link status."""

    CREATED = "created"
    PAID = "paid"
    EXPIRED = "expired"
    CANCELLED = "cancelled"
    PARTIALLY_PAID = "partially_paid"


class RefundStatus(StrEnum):
    """Normalized refund status."""

    CREATED = "created"
    PROCESSED = "processed"
    FAILED = "failed"


class SettlementStatus(StrEnum):
    """Normalized settlement status."""

    CREATED = "created"
    PROCESSED = "processed"
    FAILED = "failed"


class PaymentMethod(StrEnum):
    """Payment method (aligned with Stage 1 enums)."""

    UPI = "upi"
    CARD = "card"
    NETBANKING = "netbanking"
    WALLET = "wallet"
    EMI = "emi"
    PAY_LATER = "pay_later"
    OTHER = "other"


class NormalizedPayment(BaseModel):
    """Normalized payment from Razorpay."""

    provider_id: str = Field(..., description="Razorpay payment ID (e.g., pay_...)")
    order_id: str | None = Field(None, description="Razorpay order ID (e.g., order_...)")
    customer_id: str | None = Field(None, description="Razorpay customer ID (e.g., cust_...)")
    amount_minor: int = Field(..., ge=0, description="Amount in minor units (paise for INR)")
    currency: str = Field(..., min_length=3, max_length=3)
    status: PaymentStatus
    method: PaymentMethod = PaymentMethod.OTHER
    error_code: str | None = None
    error_description: str | None = None
    fee_minor: int | None = Field(None, ge=0, description="Razorpay fee in minor units")
    tax_minor: int | None = Field(None, ge=0, description="Tax in minor units")
    created_at: dt.datetime
    captured_at: dt.datetime | None = None
    raw: dict[str, Any] = Field(default_factory=dict, description="Original provider payload")


class NormalizedOrder(BaseModel):
    """Normalized order from Razorpay."""

    provider_id: str = Field(..., description="Razorpay order ID (e.g., order_...)")
    amount_minor: int = Field(..., ge=0)
    currency: str = Field(..., min_length=3, max_length=3)
    status: OrderStatus
    amount_paid_minor: int = Field(0, ge=0)
    amount_due_minor: int = Field(0, ge=0)
    attempts: int = Field(0, ge=0)
    created_at: dt.datetime
    raw: dict[str, Any] = Field(default_factory=dict)


class NormalizedCustomer(BaseModel):
    """Normalized customer from Razorpay."""

    provider_id: str = Field(..., description="Razorpay customer ID (e.g., cust_...)")
    name: str | None = None
    email: str | None = None
    phone: str | None = None
    created_at: dt.datetime
    raw: dict[str, Any] = Field(default_factory=dict)


class NormalizedPaymentLink(BaseModel):
    """Normalized payment link from Razorpay."""

    provider_id: str = Field(..., description="Razorpay payment link ID (e.g., plink_...)")
    reference_id: str | None = None
    amount_minor: int = Field(..., ge=0)
    amount_paid_minor: int = Field(0, ge=0)
    currency: str = Field(..., min_length=3, max_length=3)
    status: PaymentLinkStatus
    short_url: str | None = None
    customer: NormalizedCustomer | None = None
    description: str | None = None
    expire_at: dt.datetime | None = None
    created_at: dt.datetime
    raw: dict[str, Any] = Field(default_factory=dict)


class NormalizedRefund(BaseModel):
    """Normalized refund from Razorpay."""

    provider_id: str = Field(..., description="Razorpay refund ID (e.g., rfd_...)")
    payment_id: str = Field(..., description="Associated Razorpay payment ID")
    amount_minor: int = Field(..., ge=0)
    currency: str = Field(..., min_length=3, max_length=3)
    status: RefundStatus
    speed_processed: str | None = None  # normal, instant
    created_at: dt.datetime
    processed_at: dt.datetime | None = None
    raw: dict[str, Any] = Field(default_factory=dict)


class NormalizedSettlement(BaseModel):
    """Normalized settlement from Razorpay."""

    provider_id: str = Field(..., description="Razorpay settlement ID (e.g., setl_...)")
    amount_minor: int = Field(..., ge=0)
    currency: str = Field(..., min_length=3, max_length=3)
    status: SettlementStatus
    fee_minor: int = Field(0, ge=0)
    tax_minor: int = Field(0, ge=0)
    created_at: dt.datetime
    processed_at: dt.datetime | None = None
    raw: dict[str, Any] = Field(default_factory=dict)


class NormalizedWebhookEvent(BaseModel):
    """Normalized webhook event from Razorpay."""

    event: str = Field(..., description="Event type (e.g., payment.failed)")
    payload: dict[str, Any] = Field(..., description="Event payload (entity-specific)")
    created_at: dt.datetime = Field(default_factory=dt.datetime.utcnow)
    raw: dict[str, Any] = Field(default_factory=dict)