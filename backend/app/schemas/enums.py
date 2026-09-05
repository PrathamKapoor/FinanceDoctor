"""Explicit status and category enums for the Payment Failure Incident domain."""

from __future__ import annotations

from enum import StrEnum


class PaymentStatus(StrEnum):
    """Lifecycle of a Payment. Kept to the MVP states only."""

    CREATED = "CREATED"
    AUTHORIZED = "AUTHORIZED"
    CAPTURED = "CAPTURED"
    FAILED = "FAILED"
    REFUNDED = "REFUNDED"


class PaymentAttemptStatus(StrEnum):
    """Outcome of a single payment attempt."""

    STARTED = "STARTED"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"


class OrderStatus(StrEnum):
    """Order states required by the MVP."""

    CREATED = "CREATED"
    PAID = "PAID"
    FAILED = "FAILED"


class PaymentMethod(StrEnum):
    """Payment methods present in the synthetic Razorpay environment."""

    UPI = "UPI"
    CARD = "CARD"
    NETBANKING = "NETBANKING"
    WALLET = "WALLET"


class FailureReason(StrEnum):
    """Structured payment failure reasons."""

    INSUFFICIENT_FUNDS = "INSUFFICIENT_FUNDS"
    BANK_DECLINED = "BANK_DECLINED"
    CARD_EXPIRED = "CARD_EXPIRED"
    NETWORK_ERROR = "NETWORK_ERROR"
    GATEWAY_TIMEOUT = "GATEWAY_TIMEOUT"
    UNKNOWN = "UNKNOWN"


class CustomerCohort(StrEnum):
    """Customer cohort at the time of an order."""

    NEW = "NEW"
    RETURNING = "RETURNING"


class IncidentType(StrEnum):
    """Known incident types (currently one)."""

    PAYMENT_METHOD_FAILURE_SPIKE = "PAYMENT_METHOD_FAILURE_SPIKE"


class PolicyVerdict(StrEnum):
    """Reserved for the policy engine (Stage later than 1)."""

    APPROVE = "APPROVE"
    REJECT = "REJECT"
    HUMAN_APPROVAL_REQUIRED = "HUMAN_APPROVAL_REQUIRED"