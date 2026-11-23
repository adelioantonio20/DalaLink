from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.config import now_luanda
from app.db.session import Base


class Municipality(Base):
    __tablename__ = "municipalities"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    province: Mapped[str] = mapped_column(String(80), default="Luanda", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_luanda, nullable=False)

    neighborhoods: Mapped[list["Neighborhood"]] = relationship(back_populates="municipality")


class Neighborhood(Base):
    __tablename__ = "neighborhoods"
    __table_args__ = (Index("ix_neighborhoods_municipality", "municipality_id"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    municipality_id: Mapped[int] = mapped_column(
        ForeignKey("municipalities.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(120), unique=True, index=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_luanda, nullable=False)

    municipality: Mapped["Municipality"] = relationship(back_populates="neighborhoods")
    zones: Mapped[list["TransportZone"]] = relationship(back_populates="neighborhood")


class TransportZone(Base):
    __tablename__ = "transport_zones"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    neighborhood_id: Mapped[int] = mapped_column(
        ForeignKey("neighborhoods.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(120), unique=True, index=True, nullable=False)
    center_lat: Mapped[float] = mapped_column(Float, nullable=False)
    center_lng: Mapped[float] = mapped_column(Float, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_luanda, nullable=False)

    neighborhood: Mapped["Neighborhood"] = relationship(back_populates="zones")
    stops: Mapped[list["TaxiStop"]] = relationship(back_populates="zone")


class TaxiStop(Base):
    __tablename__ = "taxi_stops"
    __table_args__ = (Index("ix_taxi_stops_zone_active", "zone_id", "is_active"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    zone_id: Mapped[int] = mapped_column(ForeignKey("transport_zones.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    landmark: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    is_validated: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_luanda, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=now_luanda, onupdate=now_luanda, nullable=False
    )

    zone: Mapped["TransportZone"] = relationship(back_populates="stops")


class TransportRoute(Base):
    __tablename__ = "transport_routes"
    __table_args__ = (
        Index("ix_transport_routes_origin_dest", "origin_zone_id", "destination_zone_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(180), nullable=False)
    origin_zone_id: Mapped[int] = mapped_column(
        ForeignKey("transport_zones.id", ondelete="RESTRICT"), nullable=False
    )
    destination_zone_id: Mapped[int] = mapped_column(
        ForeignKey("transport_zones.id", ondelete="RESTRICT"), nullable=False
    )
    corridor_description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    road_condition: Mapped[str] = mapped_column(
        String(32), default="NORMAL", nullable=False
    )  # NORMAL, MODERATE_TRAFFIC, HEAVY_TRAFFIC, DISRUPTED
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_luanda, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=now_luanda, onupdate=now_luanda, nullable=False
    )

    destinations: Mapped[list["RouteDestination"]] = relationship(back_populates="route")


class RouteDestination(Base):
    __tablename__ = "route_destinations"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    route_id: Mapped[int] = mapped_column(
        ForeignKey("transport_routes.id", ondelete="CASCADE"), nullable=False
    )
    taxi_stop_id: Mapped[int] = mapped_column(
        ForeignKey("taxi_stops.id", ondelete="CASCADE"), nullable=False
    )
    sequence_order: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    is_primary_destination: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_luanda, nullable=False)

    route: Mapped["TransportRoute"] = relationship(back_populates="destinations")


class TransportIntention(Base):
    """Passenger's declared intention to travel on a route/stop (NOT a paid booking)."""

    __tablename__ = "transport_intentions"
    __table_args__ = (
        CheckConstraint("passenger_count >= 1 AND passenger_count <= 20", name="ck_intention_count"),
        Index("ix_intentions_route_status", "route_id", "status"),
        Index("ix_intentions_passenger_status", "passenger_id", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    passenger_id: Mapped[int] = mapped_column(
        ForeignKey("passengers.id", ondelete="CASCADE"), nullable=False
    )
    route_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("transport_routes.id", ondelete="SET NULL"), nullable=True
    )
    origin_stop_id: Mapped[int] = mapped_column(
        ForeignKey("taxi_stops.id", ondelete="RESTRICT"), nullable=False
    )
    destination_stop_id: Mapped[int] = mapped_column(
        ForeignKey("taxi_stops.id", ondelete="RESTRICT"), nullable=False
    )
    origin_zone_name: Mapped[str] = mapped_column(String(120), nullable=False)
    destination_zone_name: Mapped[str] = mapped_column(String(120), nullable=False)
    passenger_count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), default="DECLARED", nullable=False
    )  # DECLARED, CONFIRMED_AT_STOP, CANCELLED, EXPIRED
    source_type: Mapped[str] = mapped_column(
        String(32), default="DECLARED_PASSENGER", nullable=False
    )
    validation_status: Mapped[str] = mapped_column(
        String(24), default="UNVERIFIED", nullable=False
    )  # UNVERIFIED, CONFIRMED, FLAGGED_SUSPICIOUS
    confidence_level: Mapped[str] = mapped_column(
        String(16), default="MEDIUM", nullable=False
    )  # LOW, MEDIUM, HIGH
    is_demo_data: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    last_confirmed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_luanda, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_luanda, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=now_luanda, onupdate=now_luanda, nullable=False
    )


class GroupIntention(Base):
    __tablename__ = "group_intentions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    transport_intention_id: Mapped[int] = mapped_column(
        ForeignKey("transport_intentions.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    group_size: Mapped[int] = mapped_column(Integer, default=2, nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_luanda, nullable=False)


class PassengerConfirmation(Base):
    """Confirms that a passenger with an active intention is physically waiting at a stop."""

    __tablename__ = "passenger_confirmations"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    intention_id: Mapped[int] = mapped_column(
        ForeignKey("transport_intentions.id", ondelete="CASCADE"), nullable=False
    )
    passenger_id: Mapped[int] = mapped_column(
        ForeignKey("passengers.id", ondelete="CASCADE"), nullable=False
    )
    taxi_stop_id: Mapped[int] = mapped_column(
        ForeignKey("taxi_stops.id", ondelete="RESTRICT"), nullable=False
    )
    latitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    longitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    distance_to_stop_m: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    is_location_consistent: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    confirmed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_luanda, nullable=False)


class DriverReport(Base):
    """Time-bounded driver availability declaration for a specific Luanda stop/route."""

    __tablename__ = "driver_reports"
    __table_args__ = (
        Index("ix_driver_reports_driver_active", "driver_id", "is_active"),
        Index("ix_driver_reports_route_active", "route_id", "is_active"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    driver_id: Mapped[int] = mapped_column(
        ForeignKey("drivers.id", ondelete="CASCADE"), nullable=False
    )
    route_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("transport_routes.id", ondelete="SET NULL"), nullable=True
    )
    taxi_stop_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("taxi_stops.id", ondelete="SET NULL"), nullable=True
    )
    origin_zone_name: Mapped[str] = mapped_column(String(120), nullable=False)
    destination_zone_name: Mapped[str] = mapped_column(String(120), nullable=False)
    availability_status: Mapped[str] = mapped_column(
        String(24), default="AVAILABLE", nullable=False
    )  # AVAILABLE, AT_STOP, EN_ROUTE, UNAVAILABLE
    estimated_seats: Mapped[int] = mapped_column(Integer, default=4, nullable=False)
    source_type: Mapped[str] = mapped_column(
        String(32), default="DECLARED_DRIVER", nullable=False
    )
    validation_status: Mapped[str] = mapped_column(
        String(24), default="UNVERIFIED", nullable=False
    )
    confidence_level: Mapped[str] = mapped_column(
        String(16), default="MEDIUM", nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_demo_data: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    reported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_luanda, nullable=False)
    last_confirmed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_luanda, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class SupplyObservation(Base):
    """Field/operational observation of taxis physically present at a stop/route."""

    __tablename__ = "supply_observations"
    __table_args__ = (Index("ix_supply_obs_route_time", "route_id", "observed_at"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    observer_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    taxi_stop_id: Mapped[int] = mapped_column(
        ForeignKey("taxi_stops.id", ondelete="RESTRICT"), nullable=False
    )
    route_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("transport_routes.id", ondelete="SET NULL"), nullable=True
    )
    origin_zone_name: Mapped[str] = mapped_column(String(120), nullable=False)
    destination_zone_name: Mapped[str] = mapped_column(String(120), nullable=False)
    observed_taxis_count: Mapped[int] = mapped_column(Integer, nullable=False)
    road_condition: Mapped[str] = mapped_column(String(32), default="NORMAL", nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source_type: Mapped[str] = mapped_column(String(32), default="OBSERVED_FIELD", nullable=False)
    validation_status: Mapped[str] = mapped_column(
        String(24), default="VALIDATED", nullable=False
    )  # PENDING, VALIDATED, REJECTED
    confidence_level: Mapped[str] = mapped_column(String(16), default="HIGH", nullable=False)
    is_demo_data: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_luanda, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class DemandObservation(Base):
    """Field/operational observation of passengers waiting at a stop/route."""

    __tablename__ = "demand_observations"
    __table_args__ = (Index("ix_demand_obs_route_time", "route_id", "observed_at"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    observer_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    taxi_stop_id: Mapped[int] = mapped_column(
        ForeignKey("taxi_stops.id", ondelete="RESTRICT"), nullable=False
    )
    route_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("transport_routes.id", ondelete="SET NULL"), nullable=True
    )
    origin_zone_name: Mapped[str] = mapped_column(String(120), nullable=False)
    destination_zone_name: Mapped[str] = mapped_column(String(120), nullable=False)
    observed_passengers_count: Mapped[int] = mapped_column(Integer, nullable=False)
    estimated_wait_min: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source_type: Mapped[str] = mapped_column(String(32), default="OBSERVED_FIELD", nullable=False)
    validation_status: Mapped[str] = mapped_column(
        String(24), default="VALIDATED", nullable=False
    )  # PENDING, VALIDATED, REJECTED
    confidence_level: Mapped[str] = mapped_column(String(16), default="HIGH", nullable=False)
    is_demo_data: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_luanda, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class MobilityIndicator(Base):
    """Historical snapshot of calculated demand/supply indicators for descriptive analytics."""

    __tablename__ = "mobility_indicators"
    __table_args__ = (Index("ix_mobility_indicators_route_captured", "route_id", "captured_at"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    route_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("transport_routes.id", ondelete="SET NULL"), nullable=True
    )
    taxi_stop_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("taxi_stops.id", ondelete="SET NULL"), nullable=True
    )
    origin_zone_name: Mapped[str] = mapped_column(String(120), nullable=False)
    destination_zone_name: Mapped[str] = mapped_column(String(120), nullable=False)
    estimated_demand: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    confirmed_demand: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    declared_supply: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    observed_supply: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    demand_supply_ratio: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    demand_level: Mapped[str] = mapped_column(String(32), default="INSUFFICIENT_DATA", nullable=False)
    supply_level: Mapped[str] = mapped_column(String(32), default="INSUFFICIENT_DATA", nullable=False)
    estimated_wait_min: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    freshness_status: Mapped[str] = mapped_column(String(24), default="RECENT", nullable=False)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_luanda, nullable=False)


class LocationUpdate(Base):
    """Consent-aware location update log (never exposing individual passenger coordinates to others)."""

    __tablename__ = "location_updates"
    __table_args__ = (Index("ix_location_updates_user_time", "user_id", "recorded_at"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    zone_name: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    is_aggregated_only: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_luanda, nullable=False)


class DataValidation(Base):
    """Administrative validation and quality control ledger for observations, intentions, and reports."""

    __tablename__ = "data_validations"
    __table_args__ = (Index("ix_data_validations_target", "target_type", "target_id"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    target_type: Mapped[str] = mapped_column(String(40), nullable=False)  # SUPPLY_OBS, DEMAND_OBS, INTENTION, DRIVER_REPORT
    target_id: Mapped[int] = mapped_column(Integer, nullable=False)
    validator_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    decision: Mapped[str] = mapped_column(
        String(32), nullable=False
    )  # VALIDATED, REJECTED, FLAGGED_SUSPICIOUS, FLAGGED_DUPLICATE
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    validated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_luanda, nullable=False)


class PlatformConfig(Base):
    """Admin-configurable thresholds for demand/supply classification and data expiration windows."""

    __tablename__ = "platform_configs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    key: Mapped[str] = mapped_column(String(80), unique=True, index=True, nullable=False)
    value: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str] = mapped_column(String(240), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=now_luanda, onupdate=now_luanda, nullable=False
    )
