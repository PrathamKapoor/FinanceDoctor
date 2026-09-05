"""Financial state persistence (SQLite) for the synthetic merchant world."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.db.database import create_schema, drop_schema, get_engine
from backend.app.db.models import Customer, Merchant, Order, Payment, PaymentAttempt
from backend.app.services.synthetic_data import MerchantWorld

TABLE_CLASSES = [Merchant, Customer, Order, Payment, PaymentAttempt]


def reset_db() -> None:
    """Drop and recreate the schema (idempotent, destructive)."""
    engine = get_engine()
    drop_schema(engine)
    create_schema(engine)


def persist_world(session: Session, world: MerchantWorld) -> None:
    """Persist the full synthetic world (customers, orders, payments, attempts)."""
    session.add(world.merchant)
    session.add_all(world.customers)
    session.add_all(world.orders)
    session.add_all(world.payments)
    session.add_all(world.attempts)
    session.commit()


def count_rows(session: Session) -> dict[str, int]:
    """Return entity row counts (useful for tests and the seed report)."""
    return {
        cls.__tablename__: session.scalar(select(func.count()).select_from(cls)) or 0
        for cls in TABLE_CLASSES
    }