"""SQLAlchemy ORM models for the Payment Failure Incident MVP.

All monetary amounts are stored as **integer minor units** (``amount_minor``, for INR: paise).
Every table below is required by the Stage 1 persistence flow. The ``Investigation`` entity is
deferred to the investigation stage (it is not needed to persist deterministic evidence).
"""

from __future__ import annotations

import datetime as dt
import enum
from typing import Any

from sqlalchemy import JSON, BigInteger, DateTime, ForeignKey, Integer, String
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db.database import Base
from backend.app.schemas.enums import (
    CustomerCohort,
    OrderStatus,
    PaymentAttemptStatus,
    PaymentMethod,
    PaymentStatus,
)


def _enum(e: type[enum.Enum], length: int = 40) -> SAEnum:
    """Build a portable string-backed SQLAlchemy Enum (native enums unsupported on SQLite)."""
    return SAEnum(
        e,
        native_enum=False,
        values_callable=lambda members: [m.value for m in members],
        length=length,
    )


class Merchant(Base):
    __tablename__ = "merchant"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    razorpay_merchant_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)


class Customer(Base):
    __tablename__ = "customer"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    merchant_id: Mapped[int] = mapped_column(
        ForeignKey("merchant.id"), nullable=False, index=True
    )
    razorpay_customer_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, nullable=False)


class Order(Base):
    __tablename__ = "order"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    merchant_id: Mapped[int] = mapped_column(
        ForeignKey("merchant.id"), nullable=False, index=True
    )
    customer_id: Mapped[int] = mapped_column(ForeignKey("customer.id"), nullable=False, index=True)
    razorpay_order_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    amount_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    status: Mapped[OrderStatus] = mapped_column(_enum(OrderStatus), nullable=False)
    customer_cohort: Mapped[CustomerCohort] = mapped_column(_enum(CustomerCohort), nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, nullable=False, index=True)

    customer: Mapped[Customer] = relationship()


class Payment(Base):
    __tablename__ = "payment"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("order.id"), nullable=False, index=True)
    razorpay_payment_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    amount_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    status: Mapped[PaymentStatus] = mapped_column(_enum(PaymentStatus), nullable=False)
    method: Mapped[PaymentMethod] = mapped_column(_enum(PaymentMethod), nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, nullable=False, index=True)

    order: Mapped[Order] = relationship()


class PaymentAttempt(Base):
    __tablename__ = "payment_attempt"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    payment_id: Mapped[int] = mapped_column(ForeignKey("payment.id"), nullable=False, index=True)
    attempt_index: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[PaymentAttemptStatus] = mapped_column(
        _enum(PaymentAttemptStatus), nullable=False
    )
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, nullable=False, index=True)

    payment: Mapped[Payment] = relationship()


class Evidence(Base):
    """Persisted deterministic evidence row (schema-validated payload as JSON)."""

    __tablename__ = "evidence"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scope: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(64), nullable=False)
    metric: Mapped[str] = mapped_column(String(64), nullable=False)
    dimension: Mapped[str | None] = mapped_column(String(64), nullable=True)
    unit: Mapped[str | None] = mapped_column(String(32), nullable=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime, nullable=False, default=dt.datetime.utcnow
    )


class FinancialEvent(Base):
    """Persisted Razorpay webhook event (normalized + raw)."""

    __tablename__ = "financial_event"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    deduplication_key: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False, index=True
    )
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime, nullable=False, default=dt.datetime.utcnow
    )