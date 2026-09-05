"""Shared fixtures and small explicit world builder for Stage 1 tests."""

from __future__ import annotations

import datetime as dt
import os

os.environ["DATABASE_URL"] = "sqlite:///./data/test_financial_doctor.db"

import pytest
from backend.app.db.models import Customer, Merchant, Order, Payment, PaymentAttempt
from backend.app.schemas.enums import (
    CustomerCohort,
    FailureReason,
    OrderStatus,
    PaymentAttemptStatus,
    PaymentMethod,
    PaymentStatus,
)
from backend.app.schemas.incidents import IncidentConfig, SyntheticMerchantConfig
from backend.app.services.synthetic_data import MerchantWorld, generate_merchant_world

BASELINE_START = dt.datetime(2026, 7, 1, 0, 0, 0)


@pytest.fixture(autouse=True, scope="session")
def _clean_test_db() -> None:
    yield
    from backend.app.db.database import get_engine

    get_engine().dispose()
    path = "data/test_financial_doctor.db"
    if os.path.exists(path):
        os.remove(path)


@pytest.fixture(autouse=True)
def _reset_policy_config() -> None:
    """Restore policy config singletons between tests to avoid cross-test pollution."""
    yield
    from backend.app.schemas.action.policy import DefaultPolicyConfig, PolicyConfig

    DefaultPolicyConfig.set(PolicyConfig())
    # The service module keeps a second, private singleton with no ``set``
    # hook; reset its instance directly so it also returns defaults.
    from backend.app.services.action import policy as _policy_module

    _policy_module.DefaultPolicyConfig._instance = None


@pytest.fixture
def small_config() -> SyntheticMerchantConfig:
    return SyntheticMerchantConfig(
        seed=1,
        num_customers=200,
        num_orders=500,
        baseline_days=14,
        baseline_start=BASELINE_START,
    )


@pytest.fixture
def world(small_config: SyntheticMerchantConfig) -> MerchantWorld:
    return generate_merchant_world(small_config)


@pytest.fixture
def injected_world(small_config: SyntheticMerchantConfig) -> MerchantWorld:
    w = generate_merchant_world(small_config)
    inject(w)
    return w


def inject(world: MerchantWorld) -> None:
    from backend.app.services.incident_generator import inject_incident

    inject_incident(world, IncidentConfig())


@pytest.fixture
def make_world_fixture():
    """Expose ``make_world`` as an injectable fixture to avoid cross-module imports."""
    return make_world


def make_world(
    specs: list[
        tuple[
            PaymentMethod,
            CustomerCohort,
            bool,
            FailureReason | None,
            int,
            dt.datetime,
        ]
    ],
    baseline_start: dt.datetime = BASELINE_START,
) -> MerchantWorld:
    """Build a minimal world from explicit (method, cohort, failed, reason, amount, ts) specs.

    Each spec maps to exactly one order, one payment, and a single attempt.
    """
    config = SyntheticMerchantConfig(seed=1, baseline_start=baseline_start, baseline_days=30)
    merchant = Merchant(id=1, razorpay_merchant_id="m1", name="Test Merchant")
    customer = Customer(
        id=1,
        merchant_id=1,
        razorpay_customer_id="c1",
        email="c1@example.com",
        phone="+91",
        created_at=baseline_start - dt.timedelta(days=10),
    )
    orders: list[Order] = []
    payments: list[Payment] = []
    attempts: list[PaymentAttempt] = []

    for i, (method, cohort, failed, reason, amount, ts) in enumerate(specs, start=1):
        order = Order(
            id=i,
            merchant_id=1,
            customer_id=1,
            razorpay_order_id=f"o{i}",
            amount_minor=amount,
            currency="INR",
            status=OrderStatus.FAILED if failed else OrderStatus.PAID,
            customer_cohort=cohort,
            created_at=ts,
        )
        payment = Payment(
            id=i,
            order_id=i,
            razorpay_payment_id=f"p{i}",
            amount_minor=amount,
            currency="INR",
            status=PaymentStatus.FAILED if failed else PaymentStatus.CAPTURED,
            method=method,
            error_code=reason.value if reason else None,
            error_description=None,
            attempt_count=1,
            created_at=ts,
        )
        attempt = PaymentAttempt(
            id=i,
            payment_id=i,
            attempt_index=0,
            status=PaymentAttemptStatus.FAILED if failed else PaymentAttemptStatus.SUCCESS,
            error_code=reason.value if reason else None,
            created_at=ts,
        )
        orders.append(order)
        payments.append(payment)
        attempts.append(attempt)

    return MerchantWorld(
        config=config,
        merchant=merchant,
        customers=[customer],
        orders=orders,
        payments=payments,
        attempts=attempts,
    )