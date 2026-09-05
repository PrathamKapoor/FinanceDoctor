"""Stage 5 — OutcomeWebhookHandler tests.

HMAC verification reuse, dedup, payment_link.paid handling, out-of-order
safety, unrelated event rejection. Uses the stub provider simulator so
the same production code path is exercised.
"""

from __future__ import annotations

import pytest
from backend.app.adapters.razorpay.models import NormalizedWebhookEvent
from backend.app.adapters.razorpay.stub import StubRazorpayAdapter
from backend.app.schemas.action.execution import ActionExecution, ExecutionStatus
from backend.app.schemas.outcome.enums import OutcomeStatus, TargetOutcomeStatus
from backend.app.services.outcome.outcome_evaluator import OutcomeEvaluator
from backend.app.services.outcome.outcome_initializer import OutcomeInitializer
from backend.app.services.outcome.outcome_store import AuditStore, OutcomeStore
from backend.app.services.outcome.outcome_webhook_handler import (
    OutcomeWebhookHandler,
    WebhookProcessingError,
)
from backend.app.services.outcome.stub_provider import StubProviderSimulator
from backend.app.services.synthetic_data import SyntheticMerchantConfig, generate_merchant_world

SECRET = "test_webhook_secret"


class _FakeAction:
    action_id = "act_1"
    investigation_id = "inv_1"
    diagnosis_id = "diag_1"
    currency = "INR"


@pytest.fixture
def stack():
    world = generate_merchant_world(SyntheticMerchantConfig())
    adapter = StubRazorpayAdapter(world, webhook_secret=SECRET)
    simulator = StubProviderSimulator(adapter, SECRET)

    outcomes_store = OutcomeStore()
    audit_store = AuditStore()
    evaluator = OutcomeEvaluator(outcomes_store, audit_store)
    handler = OutcomeWebhookHandler(
        outcomes_store, audit_store, evaluator, webhook_secret=SECRET
    )
    initializer = OutcomeInitializer(outcomes_store, audit_store, evaluator)
    return {
        "adapter": adapter,
        "simulator": simulator,
        "outcomes": outcomes_store,
        "audit": audit_store,
        "evaluator": evaluator,
        "handler": handler,
        "initializer": initializer,
    }


@pytest.fixture
def initialized(stack):
    initializer = stack["initializer"]
    outcomes = stack["outcomes"]
    simulator = stack["simulator"]

    # Seed a real payment link in the stub adapter so the simulator
    # can mutate it and the webhook handler can locate it by id.
    simulator.seed_payment_link("plink_pay_1", amount_minor=5000, reference_id="ref_1")

    execution = ActionExecution(
        action_id="act_1",
        approval_id="apr_1",
        status=ExecutionStatus.SUCCEEDED,
        idempotency_key="key_1",
    )

    outcome = initializer.initialize_outcome_for_execution(
        action=_FakeAction(),
        approval=None,
        execution=execution,
        targets_with_links=[
            {
                "payment_id": "pay_1",
                "amount_minor": 5000,
                "currency": "INR",
                "payment_link_id": "plink_pay_1",
                "provider_reference": "ref_1",
            }
        ],
    )
    target = outcomes.list_targets_for_outcome(outcome.outcome_id)[0]
    return stack, outcome, target


def _paid_event(simulator, link_id: str) -> NormalizedWebhookEvent:
    payload, _body = simulator.build_payment_link_paid_payload(link_id)
    return NormalizedWebhookEvent(
        event="payment_link.paid",
        payload=payload["payload"],
        raw=payload,
    )


class TestSignatureVerification:
    def test_invalid_signature_rejected(self, stack):
        handler = stack["handler"]
        payload = {"event": "payment_link.paid", "payload": {"payment_link": {}}}
        body = b'{"event":"payment_link.paid"}'
        with pytest.raises(WebhookProcessingError, match="invalid signature"):
            handler.process_raw_payload(payload, body, "bad_signature")

    def test_valid_signature_no_target_returns_unrelated(self, stack):
        import datetime as dt
        import hashlib
        import hmac
        import json

        handler = stack["handler"]
        ts = int(dt.datetime.utcnow().timestamp())
        payload = {
            "event": "payment_link.paid",
            "payload": {"payment_link": {"id": "plink_unknown"}},
            "created_at": ts,
        }
        body = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
        sig = hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()
        result = handler.process_raw_payload(payload, body, sig)
        assert result["status"] in ("unrelated", "ignored")


class TestDedup:
    def test_duplicate_event_counted_once(self, initialized):
        stack, outcome, target = initialized
        handler = stack["handler"]
        simulator = stack["simulator"]
        simulator.mark_payment_link_paid(target.payment_link_id)
        event = _paid_event(simulator, target.payment_link_id)

        r1 = handler.process_event(event)
        assert r1["status"] == "processed"

        r2 = handler.process_event(event)
        assert r2["status"] == "duplicate"

        refreshed = stack["outcomes"].get_outcome(outcome.outcome_id)
        assert refreshed.amount_recovered_minor == 5000
        assert refreshed.targets_succeeded == 1

    def test_duplicate_does_not_recount_target(self, initialized):
        stack, outcome, target = initialized
        handler = stack["handler"]
        simulator = stack["simulator"]
        simulator.mark_payment_link_paid(target.payment_link_id)
        event = _paid_event(simulator, target.payment_link_id)
        handler.process_event(event)
        handler.process_event(event)  # duplicate
        refreshed_target = stack["outcomes"].get_target(target.target_outcome_id)
        assert refreshed_target.transition_count == 1
        assert refreshed_target.status == TargetOutcomeStatus.PAID


class TestPaymentLinkPaid:
    def test_paid_updates_target_and_outcome(self, initialized):
        stack, outcome, target = initialized
        handler = stack["handler"]
        simulator = stack["simulator"]
        simulator.mark_payment_link_paid(target.payment_link_id)
        event = _paid_event(simulator, target.payment_link_id)

        result = handler.process_event(event)
        assert result["status"] == "processed"
        assert result["target_status"] == "PAID"
        assert result["outcome_status"] == "RECOVERED"

        refreshed_target = stack["outcomes"].get_target(target.target_outcome_id)
        assert refreshed_target.status == TargetOutcomeStatus.PAID
        assert refreshed_target.recovered_amount_minor == 5000
        assert refreshed_target.paid_at is not None

        refreshed = stack["outcomes"].get_outcome(outcome.outcome_id)
        assert refreshed.status == OutcomeStatus.RECOVERED
        assert refreshed.amount_recovered_minor == 5000


class TestOutOfOrder:
    def test_paid_then_failed_does_not_corrupt(self, initialized):
        stack, outcome, target = initialized
        handler = stack["handler"]
        simulator = stack["simulator"]
        simulator.mark_payment_link_paid(target.payment_link_id)
        paid = _paid_event(simulator, target.payment_link_id)
        handler.process_event(paid)

        refreshed_target = stack["outcomes"].get_target(target.target_outcome_id)
        assert refreshed_target.status == TargetOutcomeStatus.PAID

        failed = NormalizedWebhookEvent(
            event="payment.failed",
            payload={"payment": {"id": "pay_1"}},
            raw={"event": "payment.failed"},
        )
        handler.process_event(failed)

        refreshed_target = stack["outcomes"].get_target(target.target_outcome_id)
        assert refreshed_target.status == TargetOutcomeStatus.PAID
        refreshed = stack["outcomes"].get_outcome(outcome.outcome_id)
        assert refreshed.status == OutcomeStatus.RECOVERED
        assert refreshed.amount_recovered_minor == 5000


class TestUnrelatedEvent:
    def test_unrelated_webhook_ignored(self, stack):
        handler = stack["handler"]
        event = NormalizedWebhookEvent(
            event="payment_link.paid",
            payload={"payment_link": {"id": "plink_unknown"}},
            raw={"event": "payment_link.paid"},
        )
        result = handler.process_event(event)
        assert result["status"] == "unrelated"

    def test_unsupported_event_ignored(self, stack):
        handler = stack["handler"]
        event = NormalizedWebhookEvent(
            event="refund.processed",
            payload={"refund": {"id": "rfd_1"}},
            raw={"event": "refund.processed"},
        )
        result = handler.process_event(event)
        assert result["status"] == "ignored"


class TestAuditTrail:
    def test_provider_actor_recorded(self, initialized):
        stack, outcome, target = initialized
        handler = stack["handler"]
        simulator = stack["simulator"]
        simulator.mark_payment_link_paid(target.payment_link_id)
        event = _paid_event(simulator, target.payment_link_id)
        handler.process_event(event)

        events = stack["audit"].list_for_entity("target_outcome", target.target_outcome_id)
        payment_events = [
            e for e in events if e.event_type.value == "TARGET_PAYMENT_CONFIRMED"
        ]
        assert len(payment_events) == 1
        assert payment_events[0].actor.value == "PROVIDER"
        assert payment_events[0].new_state == "PAID"
