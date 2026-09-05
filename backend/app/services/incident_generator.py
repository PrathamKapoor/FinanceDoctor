"""Deterministic payment-failure incident generator.

Transforms a healthy ``MerchantWorld`` by injecting ONE known anomaly (a payment-method failure
spike) into a configurable time window. The base dataset stays healthy; the injected activity
is additive and carries explicit ground truth (never exposed to future agents).
"""

from __future__ import annotations

import datetime as dt
import random

from backend.app.db.models import Order, Payment, PaymentAttempt
from backend.app.schemas.enums import (
    CustomerCohort,
    FailureReason,
    OrderStatus,
    PaymentAttemptStatus,
    PaymentStatus,
)
from backend.app.schemas.incidents import (
    IncidentConfig,
    IncidentGroundTruth,
    SyntheticMerchantConfig,
)
from backend.app.services.synthetic_data import MerchantWorld, _amount_minor, _pick_customer

EXPECTED_ACTION_TYPE = "CREATE_PAYMENT_LINK"


def _weighted_choice[T](rng: random.Random, weights: dict[T, float]) -> T:
    keys = list(weights.keys())
    values = [weights[k] for k in keys]
    return rng.choices(keys, weights=values)[0]


def _spike_reason_weights(
    config: SyntheticMerchantConfig, incident: IncidentConfig
) -> dict[FailureReason, float]:
    dist: dict[FailureReason, float] = {r: 0.0 for r in FailureReason}
    dist[incident.spike_failure_reason] = incident.spike_reason_share
    remainder = 1.0 - incident.spike_reason_share
    others = [r for r in FailureReason if r != incident.spike_failure_reason]
    total = sum(config.failure_reason_weights[r] for r in others)
    for r in others:
        dist[r] = remainder * (config.failure_reason_weights[r] / total)
    return dist


def resolve_window(
    world: MerchantWorld, incident: IncidentConfig
) -> tuple[dt.datetime, dt.datetime]:
    start = incident.start_time or (
        world.baseline_end + dt.timedelta(hours=14, minutes=37)
    )
    end = incident.end_time or (start + dt.timedelta(minutes=incident.duration_minutes))
    if end <= start:
        raise ValueError("incident end_time must be after start_time")
    return start, end


def inject_incident(
    world: MerchantWorld, incident: IncidentConfig
) -> IncidentGroundTruth:
    """Inject a single payment-method failure spike into ``world`` (mutates in place)."""
    config = world.config
    start, end = resolve_window(world, incident)
    rng = random.Random(config.seed + incident.seed_offset)

    order_counts = world.order_counts()
    methods = list(config.method_distribution.keys())
    method_weights = [config.method_distribution[m] for m in methods]

    spike_reasons = _spike_reason_weights(config, incident)

    next_order_id = (max((o.id for o in world.orders), default=0)) + 1
    next_payment_id = (max((p.id for p in world.payments), default=0)) + 1
    next_attempt_id = (max((a.id for a in world.attempts), default=0)) + 1

    window_seconds = int((end - start).total_seconds())

    for i in range(incident.num_orders):
        ts = start + dt.timedelta(seconds=rng.randrange(window_seconds + 1))
        method = rng.choices(methods, weights=method_weights)[0]

        if method == incident.affected_method:
            returning_share = min(1.0, config.returning_customer_share + incident.returning_bias)
            failure_prob = incident.spike_failure_rate
            reason_weights: dict[FailureReason, float] = spike_reasons
        else:
            returning_share = config.returning_customer_share
            failure_prob = config.baseline_failure_rate + config.method_failure_rate_bias.get(
                method, 0.0
            )
            failure_prob = max(0.005, min(0.5, failure_prob))
            reason_weights = config.failure_reason_weights

        customer = _pick_customer(rng, world.customers, order_counts, returning_share)
        cohort = (
            CustomerCohort.NEW
            if order_counts.get(customer.id, 0) == 0
            else CustomerCohort.RETURNING
        )
        order_counts[customer.id] = order_counts.get(customer.id, 0) + 1

        amount = _amount_minor(rng, config)

        failed = rng.random() < failure_prob
        reason = _weighted_choice(rng, reason_weights) if failed else None

        order_id = next_order_id + i
        payment_id = next_payment_id + i
        attempt_id = next_attempt_id + i

        attempt = PaymentAttempt(
            id=attempt_id,
            payment_id=payment_id,
            attempt_index=0,
            status=PaymentAttemptStatus.FAILED if failed else PaymentAttemptStatus.SUCCESS,
            error_code=reason.value if reason else None,
            created_at=ts,
        )
        payment = Payment(
            id=payment_id,
            order_id=order_id,
            razorpay_payment_id=f"pay_{payment_id:07d}",
            amount_minor=amount,
            currency=config.currency,
            status=PaymentStatus.FAILED if failed else PaymentStatus.CAPTURED,
            method=method,
            error_code=reason.value if reason else None,
            error_description=f"Payment failed with {reason.value}" if reason else None,
            attempt_count=1,
            created_at=ts,
        )
        order = Order(
            id=order_id,
            merchant_id=1,
            customer_id=customer.id,
            razorpay_order_id=f"order_{order_id:07d}",
            amount_minor=amount,
            currency=config.currency,
            status=OrderStatus.FAILED if failed else OrderStatus.PAID,
            customer_cohort=cohort,
            created_at=ts,
        )

        world.orders.append(order)
        world.payments.append(payment)
        world.attempts.append(attempt)

    world.incident = incident
    world.ground_truth = IncidentGroundTruth(
        incident_type=incident.incident_type.value,
        start_time=start,
        end_time=end,
        affected_dimension="payment_method",
        affected_value=incident.affected_method.value,
        expected_leading_hypothesis=(
            f"{incident.affected_method.value} payment-method degradation "
            f"(gateway/network failure spike)"
        ),
        expected_action_type=EXPECTED_ACTION_TYPE,
    )
    return world.ground_truth