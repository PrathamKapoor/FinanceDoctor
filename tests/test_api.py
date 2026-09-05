"""API endpoint tests (demo/dev endpoints only)."""

from __future__ import annotations

import pytest
from backend.app.main import create_app
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    app = create_app()
    with TestClient(app) as c:
        yield c


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_seed_endpoint(client):
    resp = client.post("/demo/seed", json={"seed": 1, "num_orders": 300, "num_customers": 50})
    assert resp.status_code == 200
    data = resp.json()
    assert data["orders"] == 300
    assert data["customers"] == 50
    assert "baseline" in data


def test_inject_reports_ground_truth(client):
    client.post("/demo/seed", json={"seed": 1, "num_orders": 300, "num_customers": 50})
    resp = client.post("/demo/inject-incident")
    assert resp.status_code == 200
    gt = resp.json()
    assert gt["incident_type"] == "PAYMENT_METHOD_FAILURE_SPIKE"
    assert gt["affected_dimension"] == "payment_method"


def test_metrics_endpoint(client):
    client.post("/demo/seed", json={"seed": 1, "num_orders": 300, "num_customers": 50})
    resp = client.get("/demo/metrics")
    assert resp.status_code == 200
    data = resp.json()
    assert set(data) >= {"overall", "payment_methods", "cohorts", "failure_reasons", "anomaly"}


def test_evidence_endpoint_after_incident(client):
    client.post("/demo/seed", json={"seed": 1, "num_orders": 300, "num_customers": 50})
    client.post("/demo/inject-incident")
    resp = client.get("/demo/evidence")
    assert resp.status_code == 200
    data = resp.json()
    assert data["bundle"]["anomaly"]["is_anomalous"] is True
    assert data["evidence"]


def test_metrics_without_seed_returns_409(client):
    resp = client.get("/demo/metrics")
    assert resp.status_code == 409