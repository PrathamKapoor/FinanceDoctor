"""Razorpay adapter package."""

from backend.app.adapters.razorpay.exceptions import (
    ProviderAuthenticationError,
    ProviderConflictError,
    ProviderError,
    ProviderNotFoundError,
    ProviderRateLimitError,
    ProviderTimeoutError,
    ProviderUnavailableError,
    ProviderValidationError,
    WebhookSignatureError,
    normalize_razorpay_error,
)
from backend.app.adapters.razorpay.factory import create_razorpay_adapter
from backend.app.adapters.razorpay.interface import RazorpayAdapter
from backend.app.adapters.razorpay.live import LiveRazorpayAdapter
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
from backend.app.adapters.razorpay.stub import StubRazorpayAdapter

__all__ = [
    "RazorpayAdapter",
    "create_razorpay_adapter",
    "StubRazorpayAdapter",
    "LiveRazorpayAdapter",
    "NormalizedCustomer",
    "NormalizedOrder",
    "NormalizedPayment",
    "NormalizedPaymentLink",
    "NormalizedRefund",
    "NormalizedSettlement",
    "NormalizedWebhookEvent",
    "PaymentLinkStatus",
    "PaymentMethod",
    "PaymentStatus",
    "RefundStatus",
    "SettlementStatus",
    "ProviderError",
    "ProviderAuthenticationError",
    "ProviderNotFoundError",
    "ProviderValidationError",
    "ProviderRateLimitError",
    "ProviderConflictError",
    "ProviderUnavailableError",
    "ProviderTimeoutError",
    "WebhookSignatureError",
    "normalize_razorpay_error",
]