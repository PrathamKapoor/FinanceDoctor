"""Stage 6 — demo case journey API tests.

These verify the single integration surface the frontend consumes. They do
**not** duplicate backend financial calculations; they assert that the read
model exposes the deterministic Stage 1–5 values, and that the safety
boundaries (policy → approval → execute) are preserved over HTTP.
"""

from __future__ import annotations

import pytest
from backend.app.main import create_app
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    app = create_app()
    with TestClient(app) as c:
        yield c


def start_case(client: TestClient) -> dict:
    resp = client.post("/demo/case/start", json={})
    assert resp.status_code == 200
    return resp.json()


def test_start_exposes_incident_metrics(client):
    case = start_case(client)
    symptom = case["symptom"]
    assert symptom["incident_type"] == "PAYMENT_METHOD_FAILURE_SPIKE"
    # Deterministic Stage 1 numbers — not hardcoded in the frontend.
    anomaly = symptom["anomaly"]
    assert anomaly["is_anomalous"] is True
    assert anomaly["anomaly_score"] == pytest.approx(10.854, abs=0.01)
    assert anomaly["baseline"] == pytest.approx(0.0454, abs=0.001)
    assert anomaly["current"] == pytest.approx(0.2175, abs=0.001)
    assert anomaly["relative_delta"] == pytest.approx(3.79, abs=0.1)


def test_start_exposes_diagnosis_and_evidence(client):
    case = start_case(client)
    diagnosis = case["diagnosis"]
    assert diagnosis["leading_hypothesis"] == "PAYMENT_METHOD_DEGRADATION"
    assert diagnosis["recommended_action_type"] == "CREATE_PAYMENT_LINK"
    assert len(diagnosis["alternative_hypotheses"]) >= 1
    assert diagnosis["evidence"], "evidence explorer should have items"


def test_start_exposes_policy_checks(client):
    case = start_case(client)
    policy = case["policy"]
    assert policy["decision"] == "HUMAN_APPROVAL_REQUIRED"
    assert policy["passed"] is True
    checks = {c["check"]: c["status"] for c in policy["checks"]}
    assert checks["authorization"] == "PASS"
    assert checks["eligibility"] == "PASS"
    assert checks["action_integrity"] == "PASS"
    assert case["approval"]["status"] == "PENDING"


def test_execute_before_approval_is_blocked(client):
    case = start_case(client)
    case_id = case["case_id"]
    resp = client.post(f"/demo/case/{case_id}/execute")
    assert resp.status_code == 409


def test_reject_blocks_execution(client):
    case = start_case(client)
    case_id = case["case_id"]
    resp = client.post(f"/demo/case/{case_id}/reject", json={"decided_by": "reviewer"})
    assert resp.status_code == 200
    assert resp.json()["approval"]["status"] == "REJECTED"
    resp = client.post(f"/demo/case/{case_id}/execute")
    assert resp.status_code == 409


def test_full_demo_journey(client):
    case = start_case(client)
    case_id = case["case_id"]

    approve = client.post(f"/demo/case/{case_id}/approve", json={"decided_by": "demo"})
    assert approve.status_code == 200
    assert approve.json()["approval"]["status"] == "APPROVED"

    execute = client.post(f"/demo/case/{case_id}/execute")
    assert execute.status_code == 200
    treatment = execute.json()["treatment"]
    assert treatment["status"] == "SUCCEEDED"
    assert treatment["links_count"] > 0

    simulate = client.post(f"/demo/case/{case_id}/simulate", json={})
    assert simulate.status_code == 200
    outcome = simulate.json()["outcome"]
    assert outcome["status"] == "PARTIALLY_RECOVERED"
    assert outcome["targets_succeeded"] > 0
    assert outcome["amount_recovered_minor"] > 0

    # The read model is stable across requests.
    again = client.get(f"/demo/case/{case_id}").json()
    assert again["outcome"]["status"] == "PARTIALLY_RECOVERED"
    assert again["outcome"]["amount_recovered_minor"] == outcome["amount_recovered_minor"]