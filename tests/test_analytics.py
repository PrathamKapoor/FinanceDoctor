"""Analytics engine tests with explicit expected values on a small controlled fixture."""

from __future__ import annotations

import datetime as dt

import pytest
from backend.app.schemas.enums import CustomerCohort, FailureReason, PaymentMethod
from backend.app.services.analytics import AnalyticsEngine, attempt_metrics

BASE_START = dt.datetime(2026, 7, 1, 0, 0, 0)
BASELINE_WINDOW = (BASE_START, BASE_START + dt.timedelta(days=1))
CURRENT_WINDOW = (dt.datetime(2026, 7, 31, 14, 0, 0), dt.datetime(2026, 7, 31, 18, 0, 0))


def _fixture_world(make_world_fixture):
    upi, card = PaymentMethod.UPI, PaymentMethod.CARD
    new, returning = CustomerCohort.NEW, CustomerCohort.RETURNING
    decline = FailureReason.BANK_DECLINED
    network = FailureReason.NETWORK_ERROR

    def ts(day, hour, minute=0):
        return dt.datetime(2026, 7, day, hour, minute, 0)

    return make_world_fixture(
        [
            # baseline window
            (upi, new, False, None, 1000, ts(1, 10)),
            (upi, returning, False, None, 2000, ts(1, 11)),
            (card, new, True, decline, 3000, ts(1, 12)),
            (upi, new, False, None, 4000, ts(1, 13)),
            # current window
            (upi, new, True, network, 5000, ts(31, 15)),
            (upi, returning, True, network, 6000, ts(31, 15, 30)),
            (card, new, False, None, 7000, ts(31, 16)),
        ]
    )


@pytest.fixture
def engine(make_world_fixture):
    world = _fixture_world(make_world_fixture)
    return AnalyticsEngine(world, baseline_window=BASELINE_WINDOW, current_window=CURRENT_WINDOW)


def test_attempt_metrics_counts(engine):
    baseline = engine.overall().baseline
    assert baseline.total_attempts == 4
    assert baseline.failed_attempts == 1
    assert baseline.successful_attempts == 3
    assert baseline.failure_rate == pytest.approx(0.25)


def test_overall_comparison(engine):
    overall = engine.overall()
    assert overall.current.total_attempts == 3
    assert overall.current.failure_rate == pytest.approx(2 / 3)
    assert overall.absolute_delta == pytest.approx(2 / 3 - 0.25)
    assert overall.relative_delta == pytest.approx((2 / 3 - 0.25) / 0.25)


def test_payment_method_statistics(engine):
    methods = {m.method: m for m in engine.payment_methods()}
    upi = methods["UPI"]
    assert upi.attempt_count == 2
    assert upi.failure_count == 2
    assert upi.failure_rate == pytest.approx(1.0)
    assert upi.baseline_failure_rate == pytest.approx(0.0)
    assert upi.delta == pytest.approx(1.0)

    card = methods["CARD"]
    assert card.attempt_count == 1
    assert card.failure_count == 0
    assert card.failure_rate == pytest.approx(0.0)
    assert card.baseline_failure_rate == pytest.approx(1.0)

    netbanking = methods["NETBANKING"]
    assert netbanking.attempt_count == 0
    assert netbanking.failure_rate == pytest.approx(0.0)


def test_cohort_statistics(engine):
    cohorts = {c.cohort: c for c in engine.cohorts()}
    new = cohorts["NEW"]
    assert new.attempt_count == 2
    assert new.failure_count == 1
    assert new.failure_rate == pytest.approx(0.5)
    assert new.baseline_failure_rate == pytest.approx(1 / 3)

    returning = cohorts["RETURNING"]
    assert returning.attempt_count == 1
    assert returning.failure_rate == pytest.approx(1.0)
    assert returning.baseline_failure_rate == pytest.approx(0.0)


def test_failure_reason_statistics(engine):
    reasons = {r.reason: r for r in engine.failure_reasons()}
    assert reasons["NETWORK_ERROR"].failure_count == 2
    assert reasons["NETWORK_ERROR"].failure_rate == pytest.approx(2 / 3)


def test_monetary_aggregation(engine):
    monetary = engine.monetary()
    assert monetary.total_amount_minor == 18_000
    assert monetary.failed_amount_minor == 11_000
    assert monetary.currency == "INR"


def test_attempt_metrics_on_empty_returns_zero():
    metrics = attempt_metrics([])
    assert metrics.total_attempts == 0
    assert metrics.failure_rate == 0.0
    assert metrics.success_rate == 0.0