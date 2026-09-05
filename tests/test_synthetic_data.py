"""Synthetic merchant world tests: determinism, health, record counts."""

from __future__ import annotations

from backend.app.schemas.enums import PaymentAttemptStatus
from backend.app.services.synthetic_data import generate_merchant_world


def _signature(world):
    return [
        (o.id, o.customer_id, o.amount_minor, o.status.value, o.created_at.isoformat())
        for o in world.orders
    ]


def test_deterministic_same_seed(small_config):
    a = generate_merchant_world(small_config)
    b = generate_merchant_world(small_config)
    assert _signature(a) == _signature(b)
    assert [c.id for c in a.customers] == [c.id for c in b.customers]


def test_record_counts(small_config):
    world = generate_merchant_world(small_config)
    assert len(world.customers) == small_config.num_customers
    assert len(world.orders) == small_config.num_orders
    assert len(world.payments) == small_config.num_orders
    assert len(world.attempts) >= small_config.num_orders


def test_healthy_baseline_failure_rate(small_config):
    from backend.app.services.analytics import attempt_metrics

    world = generate_merchant_world(small_config)
    metrics = attempt_metrics(world.attempts)
    assert 0.02 <= metrics.failure_rate <= 0.08
    assert abs(metrics.success_rate + metrics.failure_rate - 1.0) < 1e-9


def test_amounts_are_integer_minor_units(small_config):
    world = generate_merchant_world(small_config)
    for order in world.orders:
        assert isinstance(order.amount_minor, int)
        assert order.amount_minor % 100 == 0
        assert order.amount_minor >= small_config.amount_min_minor
        assert order.amount_minor <= small_config.amount_max_minor


def test_method_distribution_within_tolerance(small_config):
    world = generate_merchant_world(small_config)
    from collections import Counter

    counts = Counter(p.method for p in world.payments)
    total = len(world.payments)
    for method, expected in small_config.method_distribution.items():
        actual = counts.get(method, 0) / total
        assert abs(actual - expected) < 0.05


def test_attempts_have_valid_statuses(small_config):
    world = generate_merchant_world(small_config)
    for attempt in world.attempts:
        assert attempt.status in (PaymentAttemptStatus.SUCCESS, PaymentAttemptStatus.FAILED)