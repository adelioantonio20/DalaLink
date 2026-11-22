from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.config import now_luanda
from app.db.session import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    full_name: Mapped[str] = mapped_column(String(140), nullable=False)
    email: Mapped[str] = mapped_column(String(160), unique=True, index=True, nullable=False)
    phone: Mapped[str] = mapped_column(String(32), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(
        String(32),
        index=True,
        nullable=False,
        default="PASSENGER",
    )  # PASSENGER, DRIVER, COMPANY_ADMIN, EMPLOYEE, OWNER, ADMIN
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_luanda, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=now_luanda, onupdate=now_luanda, nullable=False
    )

    passenger: Mapped[Optional["Passenger"]] = relationship(back_populates="user", uselist=False)
    driver: Mapped[Optional["Driver"]] = relationship(back_populates="user", uselist=False)
    vehicle_owner: Mapped[Optional["VehicleOwner"]] = relationship(back_populates="user", uselist=False)
    employee: Mapped[Optional["Employee"]] = relationship(back_populates="user", uselist=False)


class Passenger(Base):
    __tablename__ = "passengers"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)
    document_number: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    default_zone: Mapped[str] = mapped_column(String(80), default="Gamek", nullable=False)
    rating_avg: Mapped[float] = mapped_column(Numeric(3, 2), default=5.00, nullable=False)
    total_trips: Mapped[int] = mapped_column(default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_luanda, nullable=False)

    user: Mapped["User"] = relationship(back_populates="passenger")
    wallet: Mapped[Optional["Wallet"]] = relationship(back_populates="passenger", uselist=False)


class VehicleOwner(Base):
    __tablename__ = "vehicle_owners"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)
    company_name: Mapped[Optional[str]] = mapped_column(String(160), nullable=True)
    tax_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    payout_iban: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_luanda, nullable=False)

    user: Mapped["User"] = relationship(back_populates="vehicle_owner")
    vehicles: Mapped[list["Vehicle"]] = relationship(back_populates="owner")


class Driver(Base):
    __tablename__ = "drivers"
    __table_args__ = (Index("ix_drivers_verification_status", "verification_status"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)
    license_number: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    national_id: Mapped[str] = mapped_column(String(64), nullable=False)
    verification_status: Mapped[str] = mapped_column(
        String(24), default="PENDING", nullable=False
    )  # PENDING, APPROVED, REJECTED, SUSPENDED
    verification_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    verified_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    rating_avg: Mapped[float] = mapped_column(Numeric(3, 2), default=4.90, nullable=False)
    total_trips: Mapped[int] = mapped_column(default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_luanda, nullable=False)

    user: Mapped["User"] = relationship(back_populates="driver")
    vehicles: Mapped[list["Vehicle"]] = relationship(back_populates="driver")
    availability: Mapped[Optional["DriverAvailability"]] = relationship(back_populates="driver", uselist=False)
