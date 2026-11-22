from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, CheckConstraint, DateTime, Float, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.config import now_luanda
from app.db.session import Base


class Vehicle(Base):
    __tablename__ = "vehicles"
    __table_args__ = (
        CheckConstraint("capacity >= 1 AND capacity <= 60", name="ck_vehicle_capacity"),
        Index("ix_vehicles_driver_active", "driver_id", "is_active"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    owner_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("vehicle_owners.id", ondelete="SET NULL"), nullable=True
    )
    driver_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("drivers.id", ondelete="SET NULL"), nullable=True
    )
    make: Mapped[str] = mapped_column(String(60), nullable=False)  # e.g. Hyundai
    model: Mapped[str] = mapped_column(String(60), nullable=False)  # e.g. i10
    year: Mapped[int] = mapped_column(Integer, default=2022, nullable=False)
    color: Mapped[str] = mapped_column(String(40), default="Branco", nullable=False)
    license_plate: Mapped[str] = mapped_column(String(32), unique=True, index=True, nullable=False)
    vehicle_type: Mapped[str] = mapped_column(
        String(32), default="TAXI_SEDAN", nullable=False
    )  # TAXI_SEDAN, HATCHBACK, HIACE_VAN, CORPORATE_SHUTTLE
    capacity: Mapped[int] = mapped_column(Integer, default=4, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_luanda, nullable=False)

    owner: Mapped[Optional["VehicleOwner"]] = relationship(back_populates="vehicles")
    driver: Mapped[Optional["Driver"]] = relationship(back_populates="vehicles")
    locations: Mapped[list["VehicleLocation"]] = relationship(back_populates="vehicle")


class VehicleLocation(Base):
    __tablename__ = "vehicle_locations"
    __table_args__ = (
        Index("ix_vehicle_locations_vehicle_recorded", "vehicle_id", "recorded_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    vehicle_id: Mapped[int] = mapped_column(ForeignKey("vehicles.id", ondelete="CASCADE"), nullable=False)
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    heading: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    speed_kmh: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    zone_name: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_luanda, nullable=False)

    vehicle: Mapped["Vehicle"] = relationship(back_populates="locations")


class DriverAvailability(Base):
    __tablename__ = "driver_availability"
    __table_args__ = (Index("ix_driver_availability_status", "status"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    driver_id: Mapped[int] = mapped_column(
        ForeignKey("drivers.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    active_vehicle_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("vehicles.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[str] = mapped_column(
        String(24), default="OFFLINE", nullable=False
    )  # AVAILABLE, BUSY, OFFLINE
    current_lat: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    current_lng: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    current_zone: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=now_luanda, onupdate=now_luanda, nullable=False
    )

    driver: Mapped["Driver"] = relationship(back_populates="availability")
    active_vehicle: Mapped[Optional["Vehicle"]] = relationship()
