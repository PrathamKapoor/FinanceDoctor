"""Anomaly detector tests: healthy baseline vs injected incident, determinism."""

from __future__ import annotations

import datetime as dt

from backend.app.services.analytics import AnalyticsEngine
from backend.app.services.synthetic_data import generate_merchant_world


def test_healthy_baseline_not_anomalous(small_config):
    world = generate_merchant_world(small_config)
    start = world.baseline_start
    engine = AnalyticsEngine(
        world,
        baseline_window=(start, start + dt.timedelta(days=7)),
        current_window=(start + dt.timedelta(days=7), start + dt.timedelta(days=14)),
    )
    result = engine.anomaly()
    assert result.is_anomalous is False


def test_injected_incident_is_anomalous(injected_world):
    engine = AnalyticsEngine(injected_world)
    result = engine.anomaly()
    assert result.is_anomalous is True
    assert result.anomaly_score >= engine.ANOMALY_THRESHOLD
    assert result.current > result.baseline


def test_anomaly_score_deterministic(injected_world):
    a = AnalyticsEngine(injected_world).anomaly()
    b = AnalyticsEngine(injected_world).anomaly()
    assert a.model_dump() == b.model_dump()


def test_anomaly_fields_are_computed(injected_world):
    result = AnalyticsEngine(injected_world).anomaly()
    assert result.metric == "payment_failure_rate"
    assert result.sample_size > 0
    assert result.absolute_delta > 0
    assert result.relative_delta > 0