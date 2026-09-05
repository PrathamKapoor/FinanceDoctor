"""Deterministic synthetic merchant world generator.

Produces a **healthy** merchant baseline (no incident). The same seed always produces the same
dataset. All randomness comes from ``random.Random(seed)`` (standard library); no numpy, no
LLM, no network.
"""

from __future__ import annotations

import datetime as dt
import itertools
import math
import random
from dataclasses import dataclass, field

from backend.app.db.models import Customer, Merchant, Order, Payment, PaymentAttempt
from backend.app.schemas.enums import (
    CustomerCohort,
    FailureReason,
    OrderStatus,
    PaymentAttemptStatus,
    PaymentMethod,
    PaymentStatus,
)
from backend.app.schemas.incidents import (
    IncidentConfig,
    IncidentGroundTruth,
    SyntheticMerchantConfig,
)


def _day_weight(weekday: int) -> float:
    """Weekday activity weight: retail SMB peaks toward the weekend."""
    return {0: 1.0, 1: 1.0, 2: 1.0, 3: 1.0, 4: 1.15, 5: 1.35, 6: 1.30}[weekday]


def _hour_weight(hour: int) -> float:
    """Hour-of-day activity weight: business hours and a mild evening bump."""
    if 9 <= hour <= 21:
        return 2.0
    if hour in (8, 22, 23):
        return 1.2
    return 0.5


def _clamp_method_rate(base: float, bias: float) -> float:
    return max(0.005, min(0.5, base + bias))


@dataclass
class MerchantWorld:
    """In-memory (and later persisted) representation of a merchant's financial state."""

    config: SyntheticMerchantConfig
    merchant: Merchant
    customers: list[Customer] = field(default_factory=list)
    orders: list[Order] = field(default_factory=list)
    payments: list[Payment] = field(default_factory=list)
    attempts: list[PaymentAttempt] = field(default_factory=list)
    incident: IncidentConfig | None = None
    ground_truth: IncidentGroundTruth | None = None

    @property
    def baseline_start(self) -> dt.datetime:
        return self.config.baseline_start

    @property
    def baseline_end(self) -> dt.datetime:
        return self.config.baseline_start + dt.timedelta(days=self.config.baseline_days)

    def order_counts(self) -> dict[int, int]:
        counts: dict[int, int] = {}
        for order in self.orders:
            counts[order.customer_id] = counts.get(order.customer_id, 0) + 1
        return counts


def _ids(start: int = 1) -> itertools.count[int]:
    return itertools.count(start)


def _amount_minor(rng: random.Random, config: SyntheticMerchantConfig) -> int:
    mean_major = config.amount_mean_minor / 100
    rupees = int(rng.lognormvariate(math.log(mean_major), config.amount_sigma))
    lo = config.amount_min_minor // 100
    hi = config.amount_max_minor // 100
    rupees = max(lo, min(hi, rupees))
    return rupees * 100


def _pick_customer(
    rng: random.Random,
    customers: list[Customer],
    order_counts: dict[int, int],
    returning_share: float,
) -> Customer:
    returning_pool = [c for c in customers if order_counts.get(c.id, 0) > 0]
    new_pool = [c for c in customers if order_counts.get(c.id, 0) == 0]
    if returning_pool and new_pool:
        pool = returning_pool if rng.random() < returning_share else new_pool
    elif returning_pool:
        pool = returning_pool
    else:
        pool = new_pool
    return rng.choice(pool)


def _failure_reason(rng: random.Random, config: SyntheticMerchantConfig) -> FailureReason:
    reasons = list(config.failure_reason_weights.keys())
    weights = [config.failure_reason_weights[r] for r in reasons]
    return rng.choices(reasons, weights=weights)[0]


def build_customers(
    config: SyntheticMerchantConfig, rng: random.Random
) -> list[Customer]:
    customers: list[Customer] = []
    id_gen = _ids(1)
    for _ in range(config.num_customers):
        acquisition_days = rng.uniform(0.0, 180.0)
        created_at = config.baseline_start - dt.timedelta(days=acquisition_days)
        customer_id = next(id_gen)
        customers.append(
            Customer(
                id=customer_id,
                merchant_id=1,
                razorpay_customer_id=f"cust_{customer_id:06d}",
                email=f"customer{customer_id:06d}@example.com",
                phone=f"+91{customer_id:08d}",
                created_at=created_at,
            )
        )
    return customers


def generate_orders(
    config: SyntheticMerchantConfig,
    rng: random.Random,
    customers: list[Customer],
) -> tuple[list[Order], list[Payment], list[PaymentAttempt]]:
    order_ids = _ids(1)
    payment_ids = _ids(1)
    attempt_ids = _ids(1)
    methods = list(config.method_distribution.keys())
    method_weights = [config.method_distribution[m] for m in methods]

    skeleton: list[tuple[dt.datetime, PaymentMethod]] = []
    for _ in range(config.num_orders):
        day_index = _pick_day(config, rng)
        hour = rng.choices(range(24), weights=[_hour_weight(h) for h in range(24)])[0]
        minute = rng.randint(0, 59)
        second = rng.randint(0, 59)
        ts = config.baseline_start + dt.timedelta(
            days=day_index, hours=hour, minutes=minute, seconds=second
        )
        method = rng.choices(methods, weights=method_weights)[0]
        skeleton.append((ts, method))
    skeleton.sort(key=lambda item: item[0])

    order_counts: dict[int, int] = {}
    orders: list[Order] = []
    payments: list[Payment] = []
    attempts: list[PaymentAttempt] = []

    for ts, method in skeleton:
        customer = _pick_customer(rng, customers, order_counts, config.returning_customer_share)
        cohort = (
            CustomerCohort.NEW
            if order_counts.get(customer.id, 0) == 0
            else CustomerCohort.RETURNING
        )
        order_counts[customer.id] = order_counts.get(customer.id, 0) + 1

        amount = _amount_minor(rng, config)
        order_id = next(order_ids)
        payment_id = next(payment_ids)

        order = Order(
            id=order_id,
            merchant_id=1,
            customer_id=customer.id,
            razorpay_order_id=f"order_{order_id:07d}",
            amount_minor=amount,
            currency=config.currency,
            status=OrderStatus.CREATED,
            customer_cohort=cohort,
            created_at=ts,
        )
        orders.append(order)

        payment, payment_attempts = _make_payment(
            config, rng, order, method, payment_id, attempt_ids, ts
        )
        payments.append(payment)
        attempts.extend(payment_attempts)

        if payment.status == PaymentStatus.CAPTURED:
            order.status = OrderStatus.PAID
        else:
            order.status = OrderStatus.FAILED

    return orders, payments, attempts


def _pick_day(config: SyntheticMerchantConfig, rng: random.Random) -> int:
    days = list(range(config.baseline_days))
    weights = [_day_weight((config.baseline_start + dt.timedelta(days=d)).weekday()) for d in days]
    return rng.choices(days, weights=weights)[0]


def _make_payment(
    config: SyntheticMerchantConfig,
    rng: random.Random,
    order: Order,
    method: PaymentMethod,
    payment_id: int,
    attempt_ids: itertools.count[int],
    created_at: dt.datetime,
) -> tuple[Payment, list[PaymentAttempt]]:
    base = config.baseline_failure_rate
    bias = config.method_failure_rate_bias.get(method, 0.0)
    failure_prob = _clamp_method_rate(base, bias)

    attempts: list[PaymentAttempt] = []

    def add_attempt(status: PaymentAttemptStatus, reason: FailureReason | None) -> None:
        attempts.append(
            PaymentAttempt(
                id=next(attempt_ids),
                payment_id=payment_id,
                attempt_index=len(attempts),
                status=status,
                error_code=reason.value if reason else None,
                created_at=created_at,
            )
        )

    first_failure = rng.random() < failure_prob
    if not first_failure:
        add_attempt(PaymentAttemptStatus.SUCCESS, None)
        payment = Payment(
            id=payment_id,
            order_id=order.id,
            razorpay_payment_id=f"pay_{payment_id:07d}",
            amount_minor=order.amount_minor,
            currency=config.currency,
            status=PaymentStatus.CAPTURED,
            method=method,
            error_code=None,
            error_description=None,
            attempt_count=1,
            created_at=created_at,
        )
        return payment, attempts

    reason = _failure_reason(rng, config)
    add_attempt(PaymentAttemptStatus.FAILED, reason)

    if rng.random() < config.retry_rate:
        retry_success = rng.random() < config.retry_success_rate
        if retry_success:
            add_attempt(PaymentAttemptStatus.SUCCESS, None)
        else:
            add_attempt(PaymentAttemptStatus.FAILED, reason)

    failed = all(a.status == PaymentAttemptStatus.FAILED for a in attempts)
    payment = Payment(
        id=payment_id,
        order_id=order.id,
        razorpay_payment_id=f"pay_{payment_id:07d}",
        amount_minor=order.amount_minor,
        currency=config.currency,
        status=PaymentStatus.FAILED if failed else PaymentStatus.CAPTURED,
        method=method,
        error_code=reason.value if failed else None,
        error_description=f"Payment failed with {reason.value}" if failed else None,
        attempt_count=len(attempts),
        created_at=created_at,
    )
    return payment, attempts


def generate_merchant_world(config: SyntheticMerchantConfig) -> MerchantWorld:
    """Generate the full healthy merchant world deterministically."""
    rng = random.Random(config.seed)
    merchant = Merchant(
        id=1, razorpay_merchant_id=config.razorpay_merchant_id, name=config.merchant_name
    )
    customers = build_customers(config, rng)
    orders, payments, attempts = generate_orders(config, rng, customers)
    return MerchantWorld(
        config=config,
        merchant=merchant,
        customers=customers,
        orders=orders,
        payments=payments,
        attempts=attempts,
    )