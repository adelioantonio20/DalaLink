from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.config import now_luanda
from app.db.session import Base


class Wallet(Base):
    __tablename__ = "wallets"
    __table_args__ = (
        CheckConstraint("balance_aoa >= 0", name="ck_wallet_non_negative_balance"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    passenger_id: Mapped[int] = mapped_column(
        ForeignKey("passengers.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    balance_aoa: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"), nullable=False)
    currency: Mapped[str] = mapped_column(String(8), default="AOA", nullable=False)
    is_locked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=now_luanda, onupdate=now_luanda, nullable=False
    )

    passenger: Mapped["Passenger"] = relationship(back_populates="wallet")
    cards: Mapped[list["TransportCard"]] = relationship(back_populates="wallet")


class TransportCard(Base):
    __tablename__ = "transport_cards"
    __table_args__ = (Index("ix_transport_cards_status", "status"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    wallet_id: Mapped[int] = mapped_column(ForeignKey("wallets.id", ondelete="CASCADE"), nullable=False)
    card_code: Mapped[str] = mapped_column(String(32), unique=True, index=True, nullable=False)  # MOB-000001
    qr_token: Mapped[str] = mapped_column(String(128), unique=True, index=True, nullable=False)
    card_technology: Mapped[str] = mapped_column(String(16), default="QR", nullable=False)  # QR, NFC (future)
    nfc_uid: Mapped[Optional[str]] = mapped_column(String(64), unique=True, nullable=True)
    status: Mapped[str] = mapped_column(
        String(24), default="ACTIVE", nullable=False
    )  # ACTIVE, BLOCKED, LOST, REVOKED
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_luanda, nullable=False)
    blocked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    block_reason: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)

    wallet: Mapped["Wallet"] = relationship(back_populates="cards")
    transactions: Mapped[list["CardTransaction"]] = relationship(back_populates="card")


class CardTransaction(Base):
    __tablename__ = "card_transactions"
    __table_args__ = (
        CheckConstraint("amount_aoa > 0", name="ck_card_tx_positive_amount"),
        Index("ix_card_tx_card_created", "card_id", "created_at"),
        Index("ix_card_tx_trip_id", "trip_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    card_id: Mapped[int] = mapped_column(ForeignKey("transport_cards.id", ondelete="RESTRICT"), nullable=False)
    wallet_id: Mapped[int] = mapped_column(ForeignKey("wallets.id", ondelete="RESTRICT"), nullable=False)
    trip_id: Mapped[Optional[int]] = mapped_column(ForeignKey("trips.id", ondelete="SET NULL"), nullable=True)
    tx_type: Mapped[str] = mapped_column(
        String(24), nullable=False
    )  # TOPUP_ADMIN, TRIP_DEBIT, REFUND, ADJUSTMENT
    amount_aoa: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    balance_before_aoa: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    balance_after_aoa: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="COMPLETED", nullable=False)  # COMPLETED, DECLINED
    description: Mapped[str] = mapped_column(Text, nullable=False)
    performed_by_user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_luanda, nullable=False)

    card: Mapped["TransportCard"] = relationship(back_populates="transactions")


class Tariff(Base):
    __tablename__ = "tariffs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    vehicle_type: Mapped[str] = mapped_column(String(32), default="TAXI_SEDAN", nullable=False)
    base_fare_aoa: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("500.00"), nullable=False)
    per_km_aoa: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("100.00"), nullable=False)
    per_minute_aoa: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("15.00"), nullable=False)
    min_fare_aoa: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("800.00"), nullable=False)
    commission_rate: Mapped[Decimal] = mapped_column(Numeric(5, 4), default=Decimal("0.1500"), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_luanda, nullable=False)


class Commission(Base):
    __tablename__ = "commissions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    trip_id: Mapped[int] = mapped_column(
        ForeignKey("trips.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    driver_id: Mapped[int] = mapped_column(ForeignKey("drivers.id", ondelete="RESTRICT"), nullable=False)
    gross_fare_aoa: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    commission_rate: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False)
    platform_fee_aoa: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    driver_net_aoa: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_luanda, nullable=False)
