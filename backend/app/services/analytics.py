"""Deterministic financial analytics engine.

All metrics are computed here in pure Python from ORM objects. No LLM, no float money. The
engine is the single source of truth for every financial quantity later stages consume.

Formulas (attempt level):

    failure_rate = failed_attempts / total_attempts
    success_rate = successful_attempts / total_attempts
    absolute_delta(current, baseline) = current_failure_rate - baseline_failure_rate
    relative_delta(current, baseline) = absolute_delta / baseline_failure_rate
"""

from __future__ import annotations

import datetime as dt
import statistics
from collections import defaultdict
from collections.abc import Callable

from backend.app.db.models import Order, Payment, PaymentAttempt
from backend.app.schemas.enums import CustomerCohort, PaymentAttemptStatus, PaymentMethod
from backend.app.schemas.financial import (
    AnomalyResult,
    AttemptMetrics,
    CohortStat,
    MethodStat,
    MonetaryStat,
    ReasonStat,
    TimeBucketStat,
    WindowComparison,
)
from backend.app.services.incident_generator import resolve_window
from backend.app.services.synthetic_data import MerchantWorld

Window = tuple[dt.datetime, dt.datetime]


def attempt_metrics(attempts: list[PaymentAttempt]) -> AttemptMetrics:
    total = len(attempts)
    failed = sum(1 for a in attempts if a.status == PaymentAttemptStatus.FAILED)
    success = total - failed
    return AttemptMetrics(
        total_attempts=total,
        successful_attempts=success,
        failed_attempts=failed,
        success_rate=(success / total) if total else 0.0,
        failure_rate=(failed / total) if total else 0.0,
    )


def compare(current: AttemptMetrics, baseline: AttemptMetrics) -> WindowComparison:
    absolute_delta = current.failure_rate - baseline.failure_rate
    relative_delta = absolute_delta / baseline.failure_rate if baseline.failure_rate else 0.0
    return WindowComparison(
        baseline=baseline,
        current=current,
        absolute_delta=absolute_delta,
        relative_delta=relative_delta,
    )


def _is_failed(attempt: PaymentAttempt) -> bool:
    return attempt.status == PaymentAttemptStatus.FAILED


class AnalyticsEngine:
    """Compute deterministic financial evidence over a merchant world."""

    ANOMALY_THRESHOLD = 3.0

    def __init__(
        self,
        world: MerchantWorld,
        baseline_window: Window | None = None,
        current_window: Window | None = None,
    ) -> None:
        self.world = world
        self.orders: dict[int, Order] = {o.id: o for o in world.orders}
        self.payments: dict[int, Payment] = {p.id: p for p in world.payments}
        self.baseline_window = baseline_window or (world.baseline_start, world.baseline_end)
        self.current_window = current_window or self._default_current_window()

    def _default_current_window(self) -> Window:
        if self.world.incident is not None:
            return resolve_window(self.world, self.world.incident)
        end = self.world.baseline_end
        return (end - dt.timedelta(days=1), end)

    # -- accessors ---------------------------------------------------------
    def payment_for(self, attempt: PaymentAttempt) -> Payment:
        return self.payments[attempt.payment_id]

    def order_for(self, attempt: PaymentAttempt) -> Order:
        return self.orders[self.payment_for(attempt).order_id]

    def method_for(self, attempt: PaymentAttempt) -> PaymentMethod:
        return self.payment_for(attempt).method

    def cohort_for(self, attempt: PaymentAttempt) -> CustomerCohort:
        return self.order_for(attempt).customer_cohort

    def amount_for(self, attempt: PaymentAttempt) -> int:
        return self.payment_for(attempt).amount_minor

    def attempts_in(self, window: Window) -> list[PaymentAttempt]:
        start, end = window
        return [a for a in self.world.attempts if start <= a.created_at < end]

    def baseline_attempts(self) -> list[PaymentAttempt]:
        return self.attempts_in(self.baseline_window)

    def current_attempts(self) -> list[PaymentAttempt]:
        return self.attempts_in(self.current_window)

    # -- aggregate metrics -------------------------------------------------
    def overall(self) -> WindowComparison:
        baseline = attempt_metrics(self.baseline_attempts())
        current = attempt_metrics(self.current_attempts())
        return compare(current, baseline)

    def payment_methods(self) -> list[MethodStat]:
        baseline = self._group_failure_rate(self.baseline_attempts(), self.method_for)
        current = self._group_failure_rate(self.current_attempts(), self.method_for)
        stats: list[MethodStat] = []
        for method in PaymentMethod:
            cur_count, cur_fail, cur_rate = current.get(method, (0, 0, 0.0))
            base_count, base_fail, base_rate = baseline.get(method, (0, 0, 0.0))
            stats.append(
                MethodStat(
                    method=method.value,
                    attempt_count=cur_count,
                    failure_count=cur_fail,
                    failure_rate=cur_rate,
                    baseline_failure_rate=base_rate,
                    delta=cur_rate - base_rate,
                )
            )
        return stats

    def cohorts(self) -> list[CohortStat]:
        baseline = self._group_failure_rate(self.baseline_attempts(), self.cohort_for)
        current = self._group_failure_rate(self.current_attempts(), self.cohort_for)
        stats: list[CohortStat] = []
        for cohort in CustomerCohort:
            cur_count, cur_fail, cur_rate = current.get(cohort, (0, 0, 0.0))
            base_count, base_fail, base_rate = baseline.get(cohort, (0, 0, 0.0))
            stats.append(
                CohortStat(
                    cohort=cohort.value,
                    attempt_count=cur_count,
                    failure_count=cur_fail,
                    failure_rate=cur_rate,
                    baseline_failure_rate=base_rate,
                    delta=cur_rate - base_rate,
                )
            )
        return stats

    def failure_reasons(self) -> list[ReasonStat]:
        attempts = self.current_attempts()
        total = len(attempts)
        by_reason: dict[str, int] = defaultdict(int)
        for a in attempts:
            if _is_failed(a):
                key = a.error_code or "UNKNOWN"
                by_reason[key] += 1
        if not by_reason:
            return []
        stats = [
            ReasonStat(reason=r, failure_count=c, failure_rate=(c / total) if total else 0.0)
            for r, c in sorted(by_reason.items())
        ]
        return stats

    def temporal_hourly(self) -> list[TimeBucketStat]:
        return self._bucket_by(
            self.current_attempts(),
            lambda a: a.created_at.replace(minute=0, second=0, microsecond=0).isoformat(),
        )

    def baseline_daily(self) -> list[TimeBucketStat]:
        start_date = self.baseline_window[0].date()
        end_date = self.baseline_window[1].date()
        by_date: dict[dt.date, list[PaymentAttempt]] = defaultdict(list)
        for a in self.baseline_attempts():
            by_date[a.created_at.date()].append(a)
        day = start_date
        stats: list[TimeBucketStat] = []
        while day < end_date:
            lst = by_date.get(day, [])
            metrics = attempt_metrics(lst)
            stats.append(
                TimeBucketStat(
                    bucket=day.isoformat(),
                    attempt_count=metrics.total_attempts,
                    failure_count=metrics.failed_attempts,
                    failure_rate=metrics.failure_rate,
                )
            )
            day += dt.timedelta(days=1)
        return stats

    def monetary(self) -> MonetaryStat:
        current_payments = [
            p
            for p in self.world.payments
            if self.current_window[0] <= p.created_at < self.current_window[1]
        ]
        total = sum(p.amount_minor for p in current_payments)
        failed = sum(
            p.amount_minor for p in current_payments if p.status.value == "FAILED"
        )
        return MonetaryStat(
            currency=self.world.config.currency,
            total_amount_minor=total,
            failed_amount_minor=failed,
        )

    def anomaly(self, threshold: float = ANOMALY_THRESHOLD) -> AnomalyResult:
        baseline = attempt_metrics(self.baseline_attempts())
        current = attempt_metrics(self.current_attempts())
        daily_rates = [
            b.failure_rate for b in self.baseline_daily() if b.attempt_count > 0
        ]
        mean = statistics.fmean(daily_rates) if daily_rates else 0.0
        std = statistics.stdev(daily_rates) if len(daily_rates) > 1 else 0.0
        if std > 0:
            z = (current.failure_rate - mean) / std
        else:
            z = float(current.failure_rate - mean)  # zero variance: use raw delta
        return AnomalyResult(
            metric="payment_failure_rate",
            method="z-score vs daily baseline distribution",
            baseline=baseline.failure_rate,
            baseline_mean=mean,
            baseline_std=std,
            current=current.failure_rate,
            absolute_delta=current.failure_rate - baseline.failure_rate,
            relative_delta=(current.failure_rate - baseline.failure_rate) / baseline.failure_rate
            if baseline.failure_rate
            else 0.0,
            sample_size=current.total_attempts,
            anomaly_score=round(z, 4),
            threshold=threshold,
            is_anomalous=z >= threshold,
        )

    # -- helpers -----------------------------------------------------------
    def _group_failure_rate(
        self,
        attempts: list[PaymentAttempt],
        key_fn: Callable[[PaymentAttempt], object],
    ) -> dict[object, tuple[int, int, float]]:
        counts: dict[object, list[int]] = defaultdict(lambda: [0, 0])
        for a in attempts:
            key = key_fn(a)
            counts[key][1] += 1
            if _is_failed(a):
                counts[key][0] += 1
        return {
            k: (v[1], v[0], (v[0] / v[1]) if v[1] else 0.0) for k, v in counts.items()
        }

    @staticmethod
    def _bucket_by(
        attempts: list[PaymentAttempt], key_fn: Callable[[PaymentAttempt], str]
    ) -> list[TimeBucketStat]:
        buckets: dict[str, list[int]] = defaultdict(lambda: [0, 0])
        for a in attempts:
            key = key_fn(a)
            buckets[key][1] += 1
            if _is_failed(a):
                buckets[key][0] += 1
        return [
            TimeBucketStat(
                bucket=k,
                attempt_count=v[1],
                failure_count=v[0],
                failure_rate=(v[0] / v[1]) if v[1] else 0.0,
            )
            for k, v in sorted(buckets.items())
        ]