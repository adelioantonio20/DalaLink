from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.config import now_luanda
from app.db.session import Base


class TransportRequest(Base):
    __tablename__ = "transport_requests"
    __table_args__ = (
        CheckConstraint("passenger_count >= 1 AND passenger_count <= 20", name="ck_request_passenger_count"),
        Index("ix_transport_requests_status_zone", "status", "pickup_zone"),
        Index("ix_transport_requests_offered_driver", "offered_driver_id", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    passenger_id: Mapped[int] = mapped_column(
        ForeignKey("passengers.id", ondelete="CASCADE"), nullable=False
    )
    company_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("companies.id", ondelete="SET NULL"), nullable=True
    )
    request_type: Mapped[str] = mapped_column(
        String(24), default="INDIVIDUAL", nullable=False
    )  # INDIVIDUAL, GROUP, CORPORATE
    pickup_label: Mapped[str] = mapped_column(String(160), nullable=False)
    pickup_zone: Mapped[str] = mapped_column(String(80), nullable=False)
    pickup_lat: Mapped[float] = mapped_column(Float, nullable=False)
    pickup_lng: Mapped[float] = mapped_column(Float, nullable=False)
    dropoff_label: Mapped[str] = mapped_column(String(160), nullable=False)
    dropoff_zone: Mapped[str] = mapped_column(String(80), nullable=False)
    dropoff_lat: Mapped[float] = mapped_column(Float, nullable=False)
    dropoff_lng: Mapped[float] = mapped_column(Float, nullable=False)
    passenger_count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    estimated_distance_km: Mapped[float] = mapped_column(Float, nullable=False)
    estimated_duration_min: Mapped[int] = mapped_column(Integer, nullable=False)
    fare_per_passenger_aoa: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    estimated_total_fare_aoa: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    status: Mapped[str] = mapped_column(
        String(24), default="PENDING", nullable=False
    )  # PENDING, OFFERED, ACCEPTED, CANCELLED, EXPIRED
    offered_driver_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("drivers.id", ondelete="SET NULL"), nullable=True
    )
    offer_expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    rejected_driver_ids: Mapped[str] = mapped_column(Text, default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_luanda, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=now_luanda, onupdate=now_luanda, nullable=False
    )

    group_request: Mapped[Optional["GroupRequest"]] = relationship(
        back_populates="transport_request", uselist=False
    )
    trip: Mapped[Optional["Trip"]] = relationship(back_populates="transport_request", uselist=False)


class GroupRequest(Base):
    __tablename__ = "group_requests"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    transport_request_id: Mapped[int] = mapped_column(
        ForeignKey("transport_requests.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    requester_passenger_id: Mapped[int] = mapped_column(
        ForeignKey("passengers.id", ondelete="CASCADE"), nullable=False
    )
    total_passengers: Mapped[int] = mapped_column(Integer, nullable=False)
    fare_per_passenger_aoa: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    total_fare_aoa: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_luanda, nullable=False)

    transport_request: Mapped["TransportRequest"] = relationship(back_populates="group_request")
    members: Mapped[list["GroupPassenger"]] = relationship(back_populates="group_request")


class GroupPassenger(Base):
    __tablename__ = "group_passengers"
    __table_args__ = (
        UniqueConstraint("group_request_id", "transport_card_id", name="uq_group_request_card"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    group_request_id: Mapped[int] = mapped_column(
        ForeignKey("group_requests.id", ondelete="CASCADE"), nullable=False
    )
    passenger_id: Mapped[int] = mapped_column(
        ForeignKey("passengers.id", ondelete="RESTRICT"), nullable=False
    )
    transport_card_id: Mapped[int] = mapped_column(
        ForeignKey("transport_cards.id", ondelete="RESTRICT"), nullable=False
    )
    individual_fare_aoa: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    validation_status: Mapped[str] = mapped_column(
        String(24), default="PENDING", nullable=False
    )  # PENDING, BOARDED, DECLINED
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_luanda, nullable=False)

    group_request: Mapped["GroupRequest"] = relationship(back_populates="members")


class Trip(Base):
    __tablename__ = "trips"
    __table_args__ = (
        Index("ix_trips_status_created", "status", "created_at"),
        Index("ix_trips_driver_status", "driver_id", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    transport_request_id: Mapped[int] = mapped_column(
        ForeignKey("transport_requests.id", ondelete="RESTRICT"), unique=True, nullable=False
    )
    driver_id: Mapped[int] = mapped_column(ForeignKey("drivers.id", ondelete="RESTRICT"), nullable=False)
    vehicle_id: Mapped[int] = mapped_column(ForeignKey("vehicles.id", ondelete="RESTRICT"), nullable=False)
    tariff_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("tariffs.id", ondelete="SET NULL"), nullable=True
    )
    boarding_code: Mapped[str] = mapped_column(String(8), nullable=False)
    status: Mapped[str] = mapped_column(
        String(24), default="DRIVER_EN_ROUTE", nullable=False
    )  # DRIVER_EN_ROUTE, DRIVER_ARRIVED, IN_PROGRESS, COMPLETED, CANCELLED
    eta_minutes: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    fare_per_passenger_aoa: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    total_fare_aoa: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    paid_total_aoa: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"), nullable=False)
    accepted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_luanda, nullable=False)
    arrived_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_luanda, nullable=False)

    transport_request: Mapped["TransportRequest"] = relationship(back_populates="trip")
    trip_passengers: Mapped[list["TripPassenger"]] = relationship(back_populates="trip")


class TripPassenger(Base):
    __tablename__ = "trip_passengers"
    __table_args__ = (
        UniqueConstraint("trip_id", "transport_card_id", name="uq_trip_card_single_boarding"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    trip_id: Mapped[int] = mapped_column(ForeignKey("trips.id", ondelete="CASCADE"), nullable=False)
    passenger_id: Mapped[int] = mapped_column(
        ForeignKey("passengers.id", ondelete="RESTRICT"), nullable=False
    )
    transport_card_id: Mapped[int] = mapped_column(
        ForeignKey("transport_cards.id", ondelete="RESTRICT"), nullable=False
    )
    fare_charged_aoa: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    card_transaction_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("card_transactions.id", ondelete="SET NULL"), nullable=True
    )
    boarding_status: Mapped[str] = mapped_column(
        String(24), default="BOARDED", nullable=False
    )  # PENDING, BOARDED, DECLINED
    boarded_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), default=now_luanda)

    trip: Mapped["Trip"] = relationship(back_populates="trip_passengers")


class Rating(Base):
    __tablename__ = "ratings"
    __table_args__ = (
        CheckConstraint("score >= 1 AND score <= 5", name="ck_rating_score_range"),
        UniqueConstraint("trip_id", "rater_user_id", name="uq_rating_trip_rater"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    trip_id: Mapped[int] = mapped_column(ForeignKey("trips.id", ondelete="CASCADE"), nullable=False)
    rater_user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    rated_user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    score: Mapped[int] = mapped_column(Integer, nullable=False)
    comment: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_luanda, nullable=False)


class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = (Index("ix_notifications_user_read", "user_id", "is_read"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    title: Mapped[str] = mapped_column(String(140), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(String(32), default="TRIP", nullable=False)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_luanda, nullable=False)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    __table_args__ = (Index("ix_audit_logs_entity_created", "entity_type", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    actor_user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    action: Mapped[str] = mapped_column(String(80), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(60), nullable=False)
    entity_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    details_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_luanda, nullable=False)
