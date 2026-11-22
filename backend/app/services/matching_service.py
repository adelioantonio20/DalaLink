from datetime import timedelta
from decimal import Decimal
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import now_luanda, settings
from app.models.finance import Tariff
from app.models.fleet import DriverAvailability, Vehicle
from app.models.identity import Driver
from app.models.mobility import TransportRequest
from app.services.audit_service import create_notification, record_audit
from app.services.geo_service import estimate_duration_minutes, road_distance_km


def get_active_tariff(db: Session, vehicle_type: str = "TAXI_SEDAN") -> Tariff:
    tariff = db.scalar(
        select(Tariff).where(Tariff.is_active == True, Tariff.vehicle_type == vehicle_type)  # noqa: E712
    )
    if not tariff:
        tariff = db.scalar(select(Tariff).where(Tariff.is_active == True))  # noqa: E712
    if not tariff:
        # Fallback in-memory tariff if DB not seeded yet
        return Tariff(
            name="Tarifa Urbana Padrão Luanda",
            vehicle_type="TAXI_SEDAN",
            base_fare_aoa=Decimal("450.00"),
            per_km_aoa=Decimal("90.00"),
            per_minute_aoa=Decimal("15.00"),
            min_fare_aoa=Decimal("800.00"),
            commission_rate=Decimal("0.1500"),
        )
    return tariff


def estimate_trip_quote(
    db: Session,
    pickup_lat: float,
    pickup_lng: float,
    dropoff_lat: float,
    dropoff_lng: float,
    passenger_count: int = 1,
    traffic_factor: float = 1.25,
) -> dict:
    """
    Estimate road distance, duration, and Kwanza (AOA) fare per passenger & total.
    Calibrated so Gamek -> Aeroporto (~4.3 km, ~11 min) estimates cleanly at 1.000 AOA.
    """
    tariff = get_active_tariff(db)
    dist_km = road_distance_km(pickup_lat, pickup_lng, dropoff_lat, dropoff_lng)
    dur_min = estimate_duration_minutes(dist_km, traffic_factor=traffic_factor)

    raw_fare = (
        Decimal(tariff.base_fare_aoa)
        + Decimal(str(dist_km)) * Decimal(tariff.per_km_aoa)
        + Decimal(dur_min) * Decimal(tariff.per_minute_aoa)
    )
    # Round to nearest 50 AOA for practical Luanda pricing
    rounded_50 = (raw_fare / Decimal("50")).quantize(Decimal("1")) * Decimal("50")
    fare_per_passenger = max(Decimal(tariff.min_fare_aoa), rounded_50).quantize(Decimal("0.01"))
    total_fare = (fare_per_passenger * Decimal(passenger_count)).quantize(Decimal("0.01"))

    return {
        "tariff_id": tariff.id,
        "tariff_name": tariff.name,
        "distance_km": dist_km,
        "duration_min": dur_min,
        "fare_per_passenger_aoa": fare_per_passenger,
        "total_fare_aoa": total_fare,
        "currency": "AOA",
    }


def _parse_rejected_ids(raw: str) -> set[int]:
    if not raw:
        return set()
    return {int(x) for x in raw.split(",") if x.strip().isdigit()}


def find_ranked_drivers(db: Session, req: TransportRequest) -> list[dict]:
    """
    Match passenger request with eligible APPROVED + AVAILABLE drivers.
    Weighted score considers:
      - Distance to pickup (50%)
      - Estimated arrival time (25%)
      - Vehicle capacity & route/zone compatibility (15%)
      - Driver rating (10%)
    """
    rejected_ids = _parse_rejected_ids(req.rejected_driver_ids)

    rows = db.execute(
        select(Driver, DriverAvailability, Vehicle)
        .join(DriverAvailability, DriverAvailability.driver_id == Driver.id)
        .join(Vehicle, Vehicle.id == DriverAvailability.active_vehicle_id)
        .where(
            Driver.verification_status == "APPROVED",
            DriverAvailability.status == "AVAILABLE",
            Vehicle.is_active == True,  # noqa: E712
            Vehicle.capacity >= req.passenger_count,
        )
    ).all()

    candidates: list[dict] = []
    for driver, avail, vehicle in rows:
        if driver.id in rejected_ids:
            continue
        d_lat = avail.current_lat if avail.current_lat is not None else -8.8750
        d_lng = avail.current_lng if avail.current_lng is not None else 13.2200
        dist_km = road_distance_km(d_lat, d_lng, req.pickup_lat, req.pickup_lng)
        eta_min = estimate_duration_minutes(dist_km, traffic_factor=1.2)

        # Higher score is better (0..100)
        dist_score = max(0.0, 100.0 - dist_km * 6.5)
        eta_score = max(0.0, 100.0 - eta_min * 3.5)
        zone_bonus = 20.0 if (avail.current_zone or "").lower() == req.pickup_zone.lower() else 0.0
        capacity_fit = max(0.0, 80.0 - abs(vehicle.capacity - req.passenger_count) * 8.0) + zone_bonus
        rating_score = (float(driver.rating_avg) / 5.0) * 100.0

        total_score = (
            0.50 * dist_score
            + 0.25 * eta_score
            + 0.15 * min(100.0, capacity_fit)
            + 0.10 * rating_score
        )
        candidates.append(
            {
                "driver": driver,
                "availability": avail,
                "vehicle": vehicle,
                "distance_km": dist_km,
                "eta_min": eta_min,
                "score": round(total_score, 2),
            }
        )

    candidates.sort(key=lambda c: c["score"], reverse=True)
    return candidates


def dispatch_request_to_next_driver(
    db: Session,
    req: TransportRequest,
    timeout_seconds: Optional[int] = None,
) -> Optional[dict]:
    """Offer the transport request to the highest-ranked available driver."""
    candidates = find_ranked_drivers(db, req)
    if not candidates:
        req.offered_driver_id = None
        req.offer_expires_at = None
        if req.status == "OFFERED":
            req.status = "PENDING"
        return None

    chosen = candidates[0]
    driver: Driver = chosen["driver"]
    ttl = timeout_seconds if timeout_seconds is not None else settings.MATCHING_OFFER_TIMEOUT_SECONDS

    req.offered_driver_id = driver.id
    req.offer_expires_at = now_luanda() + timedelta(seconds=ttl)
    req.status = "OFFERED"

    create_notification(
        db,
        user_id=driver.user_id,
        title="Nova solicitação de transporte",
        message=(
            f"{req.pickup_zone} → {req.dropoff_zone} ({req.passenger_count} pass.) | "
            f"Tarifa estimada: {float(req.estimated_total_fare_aoa):,.0f} AOA"
        ),
        category="OFFER",
    )
    record_audit(
        db,
        action="REQUEST_OFFERED",
        entity_type="TransportRequest",
        entity_id=req.id,
        details={
            "driver_id": driver.id,
            "score": chosen["score"],
            "distance_km": chosen["distance_km"],
            "eta_min": chosen["eta_min"],
        },
    )
    return chosen


def redistribute_expired_offers(db: Session) -> list[dict]:
    """Check OFFERED requests past offer_expires_at and redistribute to next eligible driver."""
    now = now_luanda()
    expired_reqs = db.scalars(
        select(TransportRequest).where(
            TransportRequest.status == "OFFERED",
            TransportRequest.offer_expires_at.is_not(None),
        )
    ).all()

    redistributed: list[dict] = []
    for req in expired_reqs:
        exp = req.offer_expires_at
        if exp is None:
            continue
        # Handle naive vs aware datetimes safely (SQLite stores naive timestamps)
        now_cmp = now.replace(tzinfo=None) if exp.tzinfo is None else now
        if exp <= now_cmp:
            prev_driver_id = req.offered_driver_id
            if prev_driver_id is not None:
                rejected = _parse_rejected_ids(req.rejected_driver_ids)
                rejected.add(prev_driver_id)
                req.rejected_driver_ids = ",".join(str(i) for i in sorted(rejected))

            record_audit(
                db,
                action="REQUEST_OFFER_TIMEOUT",
                entity_type="TransportRequest",
                entity_id=req.id,
                details={"timed_out_driver_id": prev_driver_id},
            )
            chosen = dispatch_request_to_next_driver(db, req)
            redistributed.append(
                {
                    "request_id": req.id,
                    "previous_driver_id": prev_driver_id,
                    "new_driver_id": chosen["driver"].id if chosen else None,
                    "status": req.status,
                }
            )
    return redistributed
