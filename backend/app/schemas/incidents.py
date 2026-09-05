"""Pydantic schemas for synthetic merchant configuration, incident injection, and ground truth."""

from __future__ import annotations

import datetime as dt

from pydantic import BaseModel, Field, model_validator

from backend.app.schemas.enums import (
    FailureReason,
    IncidentType,
    PaymentMethod,
)


class SyntheticMerchantConfig(BaseModel):
    """Deterministic parameters for the synthetic healthy merchant world."""

    seed: int = 42
    currency: str = "INR"
    merchant_name: str = "Demo Merchant"
    razorpay_merchant_id: str = "merchant_demo"

    baseline_start: dt.datetime = Field(
        default_factory=lambda: dt.datetime(2026, 7, 1, 0, 0, 0)
    )
    baseline_days: int = 30
    num_customers: int = 4000
    num_orders: int = 6000

    # Target first-attempt failure rate; per-method rates are biases around this.
    baseline_failure_rate: float = 0.04
    method_failure_rate_bias: dict[PaymentMethod, float] = Field(
        default_factory=lambda: {
            PaymentMethod.UPI: -0.01,
            PaymentMethod.CARD: 0.02,
            PaymentMethod.NETBANKING: 0.01,
            PaymentMethod.WALLET: 0.0,
        }
    )

    # Must total ~1.0.
    method_distribution: dict[PaymentMethod, float] = Field(
        default_factory=lambda: {
            PaymentMethod.UPI: 0.5,
            PaymentMethod.CARD: 0.3,
            PaymentMethod.NETBANKING: 0.15,
            PaymentMethod.WALLET: 0.05,
        }
    )

    returning_customer_share: float = 0.6
    retry_rate: float = 0.25
    retry_success_rate: float = 0.6

    # Baseline failure-reason prior.
    failure_reason_weights: dict[FailureReason, float] = Field(
        default_factory=lambda: {
            FailureReason.INSUFFICIENT_FUNDS: 0.30,
            FailureReason.BANK_DECLINED: 0.25,
            FailureReason.CARD_EXPIRED: 0.10,
            FailureReason.NETWORK_ERROR: 0.10,
            FailureReason.GATEWAY_TIMEOUT: 0.10,
            FailureReason.UNKNOWN: 0.15,
        }
    )

    amount_mean_minor: int = 50_000  # ₹500
    amount_sigma: float = 0.9
    amount_min_minor: int = 5_000  # ₹50
    amount_max_minor: int = 2_000_000  # ₹20,000

    @model_validator(mode="after")
    def _check_distributions(self) -> SyntheticMerchantConfig:
        if abs(sum(self.method_distribution.values()) - 1.0) > 1e-6:
            raise ValueError("method_distribution must sum to 1.0")
        if not self.method_distribution:
            raise ValueError("method_distribution must not be empty")
        return self


class IncidentConfig(BaseModel):
    """Configuration for a single injected payment-method failure spike."""

    incident_type: IncidentType = IncidentType.PAYMENT_METHOD_FAILURE_SPIKE
    affected_method: PaymentMethod = PaymentMethod.UPI

    start_time: dt.datetime | None = None  # defaults to baseline_end + 14h37m
    duration_minutes: int = 180
    end_time: dt.datetime | None = None

    num_orders: int = 400
    spike_failure_rate: float = 0.40
    spike_failure_reason: FailureReason = FailureReason.NETWORK_ERROR
    spike_reason_share: float = 0.90

    returning_bias: float = 0.15  # extra returning-customer share for affected orders
    seed_offset: int = 7


class IncidentGroundTruth(BaseModel):
    """Ground truth for a single incident.

    NEVER surfaced to M2.7/M3. Used only for tests, evaluation, and demo validation.
    """

    incident_type: str
    start_time: dt.datetime
    end_time: dt.datetime
    affected_dimension: str
    affected_value: str
    expected_leading_hypothesis: str
    expected_action_type: str