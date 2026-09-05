"""Evidence object / bundle / store tests."""

from __future__ import annotations

import json

from backend.app.db.database import create_schema, drop_schema, get_session_factory
from backend.app.schemas.evidence import EvidenceBundle
from backend.app.services.evidence import (
    EvidenceStore,
    build_bundle,
    flatten,
    serialize_bundle,
)

REQUIRED_EVIDENCE_IDS = {
    "overall.total_attempts",
    "overall.failure_rate",
    "anomaly.payment_failure_rate",
    "payment_method.UPI.failure_rate",
    "cohort.NEW.failure_rate",
    "monetary.failed_amount_minor",
}


def test_bundle_has_required_metrics(injected_world):
    bundle = build_bundle(injected_world)
    assert bundle.overall.baseline.total_attempts > 0
    assert bundle.payment_methods
    assert bundle.cohorts
    assert bundle.failure_reasons
    assert bundle.anomaly.is_anomalous is True


def test_flatten_contains_required_evidence(injected_world):
    items = flatten(build_bundle(injected_world))
    ids = {e.id for e in items}
    assert REQUIRED_EVIDENCE_IDS <= ids


def test_bundle_serializes_and_round_trips(injected_world):
    bundle = build_bundle(injected_world)
    text = serialize_bundle(bundle)
    data = json.loads(text)
    assert set(data.keys()) >= {"incident", "overall", "anomaly", "payment_methods", "cohorts"}
    parsed = EvidenceBundle.model_validate(data)
    assert parsed.overall.current.total_attempts == bundle.overall.current.total_attempts


def test_evidence_is_machine_readable_not_prose(injected_world):
    items = flatten(build_bundle(injected_world))
    for e in items:
        assert e.source == "deterministic"
        if e.kind in {"count", "money"}:
            assert isinstance(e.value, int)


def test_evidence_store_round_trip(injected_world):
    bundle = build_bundle(injected_world)
    items = flatten(bundle)
    drop_schema()
    create_schema()
    with get_session_factory()() as session:
        store = EvidenceStore(session)
        store.write("inc:test", items)
        retrieved = store.retrieve("inc:test")
        assert len(retrieved) == len(items)
        assert {e.id for e in retrieved} == {e.id for e in items}
        store.clear("inc:test")
        assert store.retrieve("inc:test") == []