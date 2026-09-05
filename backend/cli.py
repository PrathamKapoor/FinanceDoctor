"""Developer data-inspection command.

    uv run python -m backend.cli inspect --seed
    uv run python -m backend.cli inspect --seed --inject
    uv run python -m backend.cli inspect --seed --inject --json
"""

from __future__ import annotations

import argparse
import json
import sys

from backend.app.schemas.incidents import IncidentConfig
from backend.app.services.analytics import AnalyticsEngine
from backend.app.services.incident_generator import inject_incident
from backend.app.services.synthetic_data import SyntheticMerchantConfig, generate_merchant_world


def _describe(world, inject: bool) -> str:
    config = world.config
    engine = AnalyticsEngine(world)
    overall = engine.overall()
    lines: list[str] = []

    lines.append(f"Merchant: {world.merchant.name}")
    lines.append(f"Period: {config.baseline_days} days")
    lines.append(f"Customers: {len(world.customers)}")
    lines.append(f"Orders: {len(world.orders)}")
    lines.append(f"Payment attempts: {len(world.attempts)}")
    lines.append("")
    lines.append("Baseline:")
    lines.append(f"  Success rate: {overall.baseline.success_rate:.4f}")
    lines.append(f"  Failure rate: {overall.baseline.failure_rate:.4f}")

    if inject and world.ground_truth is not None:
        gt = world.ground_truth
        lines.append("")
        lines.append("Incident:")
        lines.append(f"  Type: {gt.incident_type}")
        lines.append(f"  Start: {gt.start_time.isoformat()}")
        lines.append(f"  End: {gt.end_time.isoformat()}")
        lines.append(f"  Affected dimension: {gt.affected_dimension}")
        lines.append(f"  Affected value: {gt.affected_value}")

    lines.append("")
    lines.append("Current:")
    lines.append(f"  Success rate: {overall.current.success_rate:.4f}")
    lines.append(f"  Failure rate: {overall.current.failure_rate:.4f}")
    anomaly = engine.anomaly()
    lines.append("")
    lines.append("Anomaly:")
    lines.append(f"  score: {anomaly.anomaly_score}")
    lines.append(f"  is_anomalous: {anomaly.is_anomalous}")
    lines.append("")
    lines.append("Payment methods:")
    for m in engine.payment_methods():
        lines.append(
            f"  {m.method:<12} attempts={m.attempt_count:<6} "
            f"failure_rate={m.failure_rate:.4f} baseline={m.baseline_failure_rate:.4f}"
        )
    return "\n".join(lines)


def _as_json(world, inject: bool) -> str:
    config = world.config
    engine = AnalyticsEngine(world)
    payload = {
        "merchant": world.merchant.name,
        "period_days": config.baseline_days,
        "customers": len(world.customers),
        "orders": len(world.orders),
        "payment_attempts": len(world.attempts),
        "baseline": engine.overall().baseline.model_dump(),
        "current": engine.overall().current.model_dump(),
        "payment_methods": [m.model_dump() for m in engine.payment_methods()],
        "cohorts": [c.model_dump() for c in engine.cohorts()],
        "failure_reasons": [r.model_dump() for r in engine.failure_reasons()],
        "anomaly": engine.anomaly().model_dump(),
    }
    if inject and world.ground_truth is not None:
        payload["ground_truth"] = world.ground_truth.model_dump()
    return json.dumps(payload, indent=2, default=str)


def cmd_inspect(args: argparse.Namespace) -> int:
    config = SyntheticMerchantConfig()
    world = generate_merchant_world(config)
    inject = bool(args.inject)
    if inject:
        inject_incident(world, IncidentConfig())
    if args.json:
        print(_as_json(world, inject))
    else:
        print(_describe(world, inject))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="financial-doctor", description="Data inspection CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    inspect = sub.add_parser("inspect", help="Generate and summarize the merchant world")
    inspect.add_argument("--seed", action="store_true", help="Generate the healthy baseline world")
    inspect.add_argument(
        "--inject", action="store_true", help="Inject the payment failure incident"
    )
    inspect.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    inspect.set_defaults(func=cmd_inspect)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())