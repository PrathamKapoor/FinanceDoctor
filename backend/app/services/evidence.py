"""Evidence object construction, evidence bundle assembly, and the evidence store.

The evidence bundle is the machine-readable contract that M2.7 / M3 will consume in later
stages. It contains ONLY deterministic evidence (no LLM output) at this stage.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.db.models import Evidence as EvidenceRow
from backend.app.schemas.evidence import Evidence, EvidenceBundle
from backend.app.schemas.financial import IncidentSummary
from backend.app.services.analytics import AnalyticsEngine
from backend.app.services.synthetic_data import MerchantWorld

DETERMINISTIC = "deterministic"


def incident_summary(world: MerchantWorld, engine: AnalyticsEngine) -> IncidentSummary:
    if world.ground_truth is not None:
        gt = world.ground_truth
        return IncidentSummary(
            type=gt.incident_type,
            start_time=gt.start_time,
            end_time=gt.end_time,
            affected_dimension=gt.affected_dimension,
            affected_value=gt.affected_value,
            is_injected=True,
        )
    start, end = engine.current_window
    return IncidentSummary(
        type="BASELINE",
        start_time=start,
        end_time=end,
        is_injected=False,
    )


def build_bundle(world: MerchantWorld, engine: AnalyticsEngine | None = None) -> EvidenceBundle:
    engine = engine or AnalyticsEngine(world)
    return EvidenceBundle(
        incident=incident_summary(world, engine),
        overall=engine.overall(),
        temporal=engine.temporal_hourly(),
        baseline_daily=engine.baseline_daily(),
        payment_methods=engine.payment_methods(),
        cohorts=engine.cohorts(),
        failure_reasons=engine.failure_reasons(),
        monetary=engine.monetary(),
        anomaly=engine.anomaly(),
    )


def flatten(bundle: EvidenceBundle) -> list[Evidence]:
    """Flatten a bundle into a list of typed, individually addressable evidence objects."""
    evidence: list[Evidence] = []
    c = bundle.overall.current
    b = bundle.overall.baseline

    evidence.append(
        Evidence(
            id="overall.total_attempts", kind="count", metric="total_attempts",
            value=c.total_attempts, unit="attempt", window="current",
        )
    )
    evidence.append(
        Evidence(
            id="overall.failed_attempts", kind="count", metric="failed_attempts",
            value=c.failed_attempts, unit="attempt", window="current",
        )
    )
    evidence.append(
        Evidence(
            id="overall.failure_rate", kind="rate", metric="failure_rate",
            value=c.failure_rate, unit="ratio", baseline=b.failure_rate,
            current=c.failure_rate, delta=bundle.overall.absolute_delta, window="current",
        )
    )
    evidence.append(
        Evidence(
            id="overall.failure_rate_spike", kind="delta", metric="failure_rate_absolute_delta",
            value=bundle.overall.absolute_delta, unit="ratio",
            baseline=b.failure_rate, current=c.failure_rate, window="current",
        )
    )

    anomaly = bundle.anomaly
    evidence.append(
        Evidence(
            id="anomaly.payment_failure_rate", kind="anomaly", metric="payment_failure_rate",
            value=anomaly.model_dump(), unit=None, baseline=anomaly.baseline,
            current=anomaly.current, delta=anomaly.absolute_delta, window="current",
        )
    )

    for m in bundle.payment_methods:
        evidence.append(
            Evidence(
                id=f"payment_method.{m.method}.failure_rate", kind="rate",
                metric="failure_rate", value=m.failure_rate, unit="ratio",
                baseline=m.baseline_failure_rate, current=m.failure_rate, delta=m.delta,
                dimension="payment_method", window="current",
            )
        )

    for co in bundle.cohorts:
        evidence.append(
            Evidence(
                id=f"cohort.{co.cohort}.failure_rate", kind="rate", metric="failure_rate",
                value=co.failure_rate, unit="ratio", baseline=co.baseline_failure_rate,
                current=co.failure_rate, delta=co.delta, dimension="customer_cohort",
                window="current",
            )
        )

    evidence.append(
        Evidence(
            id="failure_reason.distribution", kind="distribution",
            metric="failure_reason_distribution",
            value={r.reason: r.failure_count for r in bundle.failure_reasons},
            unit="count", dimension="failure_reason", window="current",
        )
    )

    evidence.append(
        Evidence(
            id="monetary.failed_amount_minor", kind="money", metric="failed_amount_minor",
            value=bundle.monetary.failed_amount_minor, unit=f"{bundle.monetary.currency}_minor",
            window="current",
        )
    )
    evidence.append(
        Evidence(
            id="incident.start_time", kind="timestamp", metric="incident_start_time",
            value=bundle.incident.start_time.isoformat(), unit="iso8601", window="current",
        )
    )
    return evidence


class EvidenceStore:
    """Persist and retrieve deterministic evidence rows (SQLite-backed)."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def write(self, scope: str, evidence: list[Evidence]) -> None:
        for row in evidence:
            self.session.add(
                EvidenceRow(
                    scope=scope,
                    kind=row.kind,
                    metric=row.metric,
                    dimension=row.dimension,
                    unit=row.unit,
                    payload=row.model_dump(),
                    created_at=dt.datetime.utcnow(),
                )
            )
        self.session.commit()

    def retrieve(self, scope: str) -> list[Evidence]:
        rows = self.session.scalars(
            select(EvidenceRow).where(EvidenceRow.scope == scope).order_by(EvidenceRow.id)
        ).all()
        return [Evidence(**row.payload) for row in rows]

    def clear(self, scope: str | None = None) -> None:
        stmt = select(EvidenceRow)
        if scope is not None:
            stmt = stmt.where(EvidenceRow.scope == scope)
        for row in self.session.scalars(stmt).all():
            self.session.delete(row)
        self.session.commit()


def serialize_bundle(bundle: EvidenceBundle) -> str:
    return bundle.model_dump_json(indent=2)