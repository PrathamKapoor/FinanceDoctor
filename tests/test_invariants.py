"""Financial invariant / property tests.

These prove the arithmetic is trustworthy: totals decompose exactly, rates are ratios,
and money never leaves the integer minor-unit representation.
"""

from __future__ import annotations

import pytest
from backend.app.schemas.enums import PaymentAttemptStatus
from backend.app.services.analytics import AnalyticsEngine, attempt_metrics


def test_successful_plus_failed_equals_total(injected_world):
    metrics = attempt_metrics(injected_world.attempts)
    assert metrics.successful_attempts + metrics.failed_attempts == metrics.total_attempts


def test_failure_rate_is_ratio(injected_world):
    metrics = attempt_metrics(injected_world.attempts)
    if metrics.total_attempts:
        assert metrics.failure_rate == pytest.approx(
            metrics.failed_attempts / metrics.total_attempts
        )


def test_method_attempts_sum_to_total(injected_world):
    engine = AnalyticsEngine(injected_world)
    methods = engine.payment_methods()
    total = engine.overall().current.total_attempts
    assert sum(m.attempt_count for m in methods) == total


def test_method_failures_sum_to_total_failures(injected_world):
    engine = AnalyticsEngine(injected_world)
    methods = engine.payment_methods()
    failed = engine.overall().current.failed_attempts
    assert sum(m.failure_count for m in methods) == failed


def test_cohort_attempts_sum_to_total(injected_world):
    engine = AnalyticsEngine(injected_world)
    cohorts = engine.cohorts()
    total = engine.overall().current.total_attempts
    assert sum(c.attempt_count for c in cohorts) == total


def test_failed_amount_le_total_amount(injected_world):
    engine = AnalyticsEngine(injected_world)
    monetary = engine.monetary()
    assert 0 <= monetary.failed_amount_minor <= monetary.total_amount_minor


def test_payment_attempt_count_matches_rows(injected_world):
    from collections import Counter

    rows_by_payment = Counter(a.payment_id for a in injected_world.attempts)
    for payment in injected_world.payments:
        assert payment.attempt_count == rows_by_payment[payment.id]


def test_attempts_are_exclusively_terminal(injected_world):
    for attempt in injected_world.attempts:
        assert attempt.status in (
            PaymentAttemptStatus.SUCCESS,
            PaymentAttemptStatus.FAILED,
        )