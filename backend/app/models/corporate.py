from datetime import date, datetime
from typing import Optional

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Index, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.config import now_luanda
from app.db.session import Base


class Company(Base):
    __tablename__ = "companies"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    nif: Mapped[str] = mapped_column(String(40), unique=True, index=True, nullable=False)
    contact_email: Mapped[str] = mapped_column(String(160), nullable=False)
    contact_phone: Mapped[str] = mapped_column(String(32), nullable=False)
    headquarters_zone: Mapped[str] = mapped_column(String(80), default="Talatona", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_luanda, nullable=False)

    employees: Mapped[list["Employee"]] = relationship(back_populates="company")
    subscriptions: Mapped[list["Subscription"]] = relationship(back_populates="company")
    routes: Mapped[list["Route"]] = relationship(back_populates="company")


class Employee(Base):
    __tablename__ = "employees"
    __table_args__ = (Index("ix_employees_company_status", "company_id", "status"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), unique=True, nullable=True
    )
    full_name: Mapped[str] = mapped_column(String(140), nullable=False)
    email: Mapped[str] = mapped_column(String(160), nullable=False)
    department: Mapped[str] = mapped_column(String(80), default="Operações", nullable=False)
    pickup_zone: Mapped[str] = mapped_column(String(80), default="Gamek", nullable=False)
    dropoff_zone: Mapped[str] = mapped_column(String(80), default="Talatona", nullable=False)
    shift_time: Mapped[str] = mapped_column(String(16), default="17:00", nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="ACTIVE", nullable=False)  # INVITED, ACTIVE, SUSPENDED
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_luanda, nullable=False)

    company: Mapped["Company"] = relationship(back_populates="employees")
    user: Mapped[Optional["User"]] = relationship(back_populates="employee")


class Subscription(Base):
    __tablename__ = "subscriptions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    plan_name: Mapped[str] = mapped_column(String(80), default="Empresarial Pro Luanda", nullable=False)
    monthly_fee_aoa: Mapped[float] = mapped_column(Numeric(12, 2), default=350000.00, nullable=False)
    max_employees: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="ACTIVE", nullable=False)  # ACTIVE, PAUSED, EXPIRED
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_luanda, nullable=False)

    company: Mapped["Company"] = relationship(back_populates="subscriptions")


class Route(Base):
    __tablename__ = "routes"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    company_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("companies.id", ondelete="SET NULL"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(140), nullable=False)
    origin_zone: Mapped[str] = mapped_column(String(80), nullable=False)
    destination_zone: Mapped[str] = mapped_column(String(80), nullable=False)
    scheduled_time: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)  # e.g. "17:00"
    is_corporate: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_luanda, nullable=False)

    company: Mapped[Optional["Company"]] = relationship(back_populates="routes")
    stops: Mapped[list["Stop"]] = relationship(back_populates="route")


class Stop(Base):
    __tablename__ = "stops"
    __table_args__ = (Index("ix_stops_zone_name", "zone_name"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    route_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("routes.id", ondelete="SET NULL"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(140), nullable=False)
    zone_name: Mapped[str] = mapped_column(String(80), nullable=False)
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    sequence_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_public_hub: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_luanda, nullable=False)

    route: Mapped[Optional["Route"]] = relationship(back_populates="stops")


class RecurringCorporateBooking(Base):
    __tablename__ = "recurring_corporate_bookings"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    route_id: Mapped[int] = mapped_column(ForeignKey("routes.id", ondelete="CASCADE"), nullable=False)
    days_of_week: Mapped[str] = mapped_column(String(64), default="SEG,TER,QUA,QUI,SEX", nullable=False)
    shift_time: Mapped[str] = mapped_column(String(16), default="17:00", nullable=False)
    vehicle_capacity_hint: Mapped[int] = mapped_column(Integer, default=12, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_dispatched_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_luanda, nullable=False)

    company: Mapped["Company"] = relationship()
    route: Mapped["Route"] = relationship()

