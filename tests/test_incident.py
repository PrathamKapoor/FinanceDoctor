"""Incident injection tests: reproducibility, ground truth, targeted effect."""

from __future__ import annotations

from backend.app.schemas.enums import PaymentMethod
from backend.app.schemas.incidents import IncidentConfig
from backend.app.services.analytics import AnalyticsEngine, attempt_metrics
from backend.app.services.incident_generator import EXPECTED_ACTION_TYPE, inject_incident
from backend.app.services.synthetic_data import generate_merchant_world


def _fresh(small_config):
    return generate_merchant_world(small_config)


def test_incident_reproducible(small_config):
    gt_a = inject_incident(_fresh(small_config), IncidentConfig())
    gt_b = inject_incident(_fresh(small_config), IncidentConfig())
    assert gt_a.model_dump() == gt_b.model_dump()


def test_ground_truth_correct(small_config):
    world = _fresh(small_config)
    gt = inject_incident(world, IncidentConfig())
    assert gt.incident_type == "PAYMENT_METHOD_FAILURE_SPIKE"
    assert gt.affected_dimension == "payment_method"
    assert gt.affected_value == "UPI"
    assert gt.expected_action_type == EXPECTED_ACTION_TYPE
    assert gt.start_time < gt.end_time


def test_affected_method_spikes_others_do_not(small_config):
    world = _fresh(small_config)
    incident = IncidentConfig(affected_method=PaymentMethod.UPI)
    inject_incident(world, incident)

    from backend.app.services.analytics import AnalyticsEngine

    engine = AnalyticsEngine(world)
    methods = {m.method: m for m in engine.payment_methods()}
    upi = methods["UPI"]
    assert upi.failure_rate > upi.baseline_failure_rate + 0.15

    for method_name, stat in methods.items():
        if method_name != "UPI":
            assert abs(stat.failure_rate - stat.baseline_failure_rate) < 0.12


def test_unrelated_dimensions_not_destroyed(small_config):
    world = _fresh(small_config)
    customers_before = list(world.customers)
    baseline_orders = len(world.orders)
    inject_incident(world, IncidentConfig())
    assert world.customers == customers_before
    assert len(world.orders) == baseline_orders + IncidentConfig().num_orders
    assert all(o.amount_minor >= 0 for o in world.orders)


def test_incident_increases_overall_failure_rate(small_config):
    world = _fresh(small_config)
    baseline_rate = attempt_metrics(world.attempts).failure_rate
    inject_incident(world, IncidentConfig())
    current_rate = AnalyticsEngine(world).overall().current.failure_rate
    assert current_rate > baseline_rate + 0.10


def test_incident_uses_seed_offset(small_config):
    a = _fresh(small_config)
    b = _fresh(small_config)
    inject_incident(a, IncidentConfig(seed_offset=7))
    inject_incident(b, IncidentConfig(seed_offset=8))
    assert a.ground_truth.start_time < a.ground_truth.end_time
    assert a.incident is not None and b.incident is not None