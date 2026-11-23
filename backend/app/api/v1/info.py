from datetime import timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_roles
from app.core.config import now_luanda
from app.db.session import get_db
from app.models.identity import Driver, Passenger, User
from app.models.intelligence import (
    DataValidation,
    DemandObservation,
    DriverReport,
    GroupIntention,
    LocationUpdate,
    Municipality,
    Neighborhood,
    PassengerConfirmation,
    PlatformConfig,
    RouteDestination,
    SupplyObservation,
    TaxiStop,
    TransportIntention,
    TransportRoute,
    TransportZone,
)
from app.models.mobility import AuditLog
from app.services.audit_service import create_notification, record_audit
from app.services.geo_service import haversine_km
from app.services.info_engine_service import (
    classify_freshness,
    compute_all_routes_overview,
    compute_historical_analytics,
    evaluate_corridor_status,
    expire_stale_records,
    get_thresholds,
    record_indicator_snapshot,
)
from app.services.realtime_hub import realtime_hub

router = APIRouter(prefix="/info", tags=["Inteligência de Mobilidade (MVP)"])


# --- Schemas ---
class DeclareIntentionRequest(BaseModel):
    origin_zone: str = Field(min_length=2, max_length=120)
    destination_zone: str = Field(min_length=2, max_length=120)
    origin_stop_id: Optional[int] = None
    destination_stop_id: Optional[int] = None
    passenger_count: int = Field(default=1, ge=1, le=20)
    notes: Optional[str] = Field(default=None, max_length=300)


class UpdateIntentionRequest(BaseModel):
    destination_zone: Optional[str] = None
    passenger_count: Optional[int] = Field(default=None, ge=1, le=20)
    notes: Optional[str] = Field(default=None, max_length=300)


class ConfirmAtStopRequest(BaseModel):
    latitude: Optional[float] = None
    longitude: Optional[float] = None


class DriverAvailabilityReportRequest(BaseModel):
    origin_zone: str = Field(min_length=2, max_length=120)
    destination_zone: str = Field(min_length=2, max_length=120)
    taxi_stop_id: Optional[int] = None
    availability_status: str = Field(default="AVAILABLE")  # AVAILABLE, AT_STOP, EN_ROUTE, UNAVAILABLE
    estimated_seats: int = Field(default=4, ge=1, le=50)
    latitude: Optional[float] = None
    longitude: Optional[float] = None


class FieldObservationRequest(BaseModel):
    origin_zone: str
    destination_zone: str
    taxi_stop_id: Optional[int] = None
    observed_taxis_count: int = Field(ge=0, le=500)
    observed_passengers_count: int = Field(ge=0, le=2000)
    estimated_wait_min: Optional[int] = Field(default=None, ge=0, le=180)
    road_condition: str = "NORMAL"  # NORMAL, MODERATE_TRAFFIC, HEAVY_TRAFFIC, DISRUPTED
    notes: Optional[str] = Field(default=None, max_length=400)
    auto_validate: bool = True


class DataValidationDecisionRequest(BaseModel):
    decision: str  # VALIDATED, REJECTED, FLAGGED_SUSPICIOUS, FLAGGED_DUPLICATE
    reason: Optional[str] = Field(default=None, max_length=300)


class CreateStopRequest(BaseModel):
    zone_id: int
    name: str = Field(min_length=3, max_length=160)
    landmark: Optional[str] = None
    latitude: float
    longitude: float
    is_validated: bool = True


class CreateRouteRequest(BaseModel):
    code: str = Field(min_length=3, max_length=40)
    name: str = Field(min_length=3, max_length=180)
    origin_zone_id: int
    destination_zone_id: int
    corridor_description: Optional[str] = None
    road_condition: str = "NORMAL"


class UpdateConfigRequest(BaseModel):
    updates: dict[str, str]


# --- Helpers ---
def _find_stop_for_zone(db: Session, zone_name: str, stop_id: Optional[int] = None) -> TaxiStop:
    if stop_id:
        st = db.get(TaxiStop, stop_id)
        if st:
            return st
    z = db.scalar(select(TransportZone).where(TransportZone.name.ilike(zone_name.strip())))
    if not z:
        raise HTTPException(status_code=404, detail=f"Zona de transporte não encontrada: {zone_name}")
    st = db.scalar(select(TaxiStop).where(TaxiStop.zone_id == z.id, TaxiStop.is_active == True))  # noqa: E712
    if not st:
        raise HTTPException(status_code=404, detail=f"Nenhuma paragem activa na zona {zone_name}")
    return st


def _find_route(db: Session, origin_zone: str, destination_zone: str) -> Optional[TransportRoute]:
    oz = db.scalar(select(TransportZone).where(TransportZone.name.ilike(origin_zone.strip())))
    dz = db.scalar(select(TransportZone).where(TransportZone.name.ilike(destination_zone.strip())))
    if not oz or not dz:
        return None
    return db.scalar(
        select(TransportRoute).where(
            TransportRoute.origin_zone_id == oz.id,
            TransportRoute.destination_zone_id == dz.id,
        )
    )


def _serialize_intention(i: TransportIntention, thresholds: dict[str, float]) -> dict:
    freshness, age_min = classify_freshness(i.last_confirmed_at, i.expires_at, thresholds)
    return {
        "id": i.id,
        "route_id": i.route_id,
        "origin_stop_id": i.origin_stop_id,
        "destination_stop_id": i.destination_stop_id,
        "origin_zone": i.origin_zone_name,
        "destination_zone": i.destination_zone_name,
        "passenger_count": i.passenger_count,
        "status": i.status,
        "source_type": i.source_type,
        "validation_status": i.validation_status,
        "confidence_level": i.confidence_level,
        "freshness_status": freshness,
        "age_minutes": age_min,
        "notes": i.notes,
        "is_demo_data": i.is_demo_data,
        "last_confirmed_at": i.last_confirmed_at.isoformat() if i.last_confirmed_at else None,
        "expires_at": i.expires_at.isoformat() if i.expires_at else None,
        "created_at": i.created_at.isoformat() if i.created_at else None,
    }


# --- 1. GEOGRAPHY & CONSULTATION ---
@router.get("/geography")
def get_geography(db: Session = Depends(get_db)):
    munis = db.scalars(select(Municipality).where(Municipality.is_active == True).order_by(Municipality.name)).all()  # noqa: E712
    neighs = db.scalars(select(Neighborhood).where(Neighborhood.is_active == True).order_by(Neighborhood.name)).all()  # noqa: E712
    zones = db.scalars(select(TransportZone).where(TransportZone.is_active == True).order_by(TransportZone.name)).all()  # noqa: E712
    stops = db.scalars(select(TaxiStop).where(TaxiStop.is_active == True).order_by(TaxiStop.name)).all()  # noqa: E712
    routes = db.scalars(select(TransportRoute).where(TransportRoute.is_active == True).order_by(TransportRoute.name)).all()  # noqa: E712

    zones_by_id = {z.id: z for z in zones}
    neighs_by_id = {n.id: n for n in neighs}
    munis_by_id = {m.id: m for m in munis}

    return {
        "municipalities": [{"id": m.id, "name": m.name, "province": m.province} for m in munis],
        "neighborhoods": [
            {"id": n.id, "name": n.name, "municipality_id": n.municipality_id} for n in neighs
        ],
        "zones": [
            {
                "id": z.id,
                "name": z.name,
                "neighborhood": neighs_by_id[z.neighborhood_id].name if z.neighborhood_id in neighs_by_id else "",
                "municipality": (
                    munis_by_id[neighs_by_id[z.neighborhood_id].municipality_id].name
                    if z.neighborhood_id in neighs_by_id
                    and neighs_by_id[z.neighborhood_id].municipality_id in munis_by_id
                    else "Luanda"
                ),
                "latitude": z.center_lat,
                "longitude": z.center_lng,
            }
            for z in zones
        ],
        "stops": [
            {
                "id": s.id,
                "zone_id": s.zone_id,
                "zone_name": zones_by_id[s.zone_id].name if s.zone_id in zones_by_id else "",
                "name": s.name,
                "landmark": s.landmark,
                "latitude": s.latitude,
                "longitude": s.longitude,
                "is_validated": s.is_validated,
            }
            for s in stops
        ],
        "routes": [
            {
                "id": r.id,
                "code": r.code,
                "name": r.name,
                "origin_zone": zones_by_id[r.origin_zone_id].name if r.origin_zone_id in zones_by_id else "",
                "destination_zone": zones_by_id[r.destination_zone_id].name if r.destination_zone_id in zones_by_id else "",
                "road_condition": r.road_condition,
                "corridor_description": r.corridor_description,
            }
            for r in routes
        ],
    }


@router.get("/corridor")
def consult_corridor(
    origin_zone: str = Query(..., min_length=2),
    destination_zone: str = Query(..., min_length=2),
    db: Session = Depends(get_db),
):
    expire_stale_records(db)
    db.commit()
    return evaluate_corridor_status(
        db,
        origin_zone=origin_zone,
        destination_zone=destination_zone,
        include_alternatives=True,
    )


@router.get("/routes")
def list_routes_with_indicators(
    zone: Optional[str] = Query(default=None),
    municipality: Optional[str] = Query(default=None),
    destination: Optional[str] = Query(default=None),
    demand_level: Optional[str] = Query(default=None),
    supply_level: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
):
    items = compute_all_routes_overview(
        db,
        zone=zone,
        municipality=municipality,
        destination=destination,
        demand_level_filter=demand_level,
        supply_level_filter=supply_level,
    )
    db.commit()
    return {"routes": items, "server_time_luanda": now_luanda().isoformat()}


@router.get("/map")
def get_mobility_map_data(
    zone: Optional[str] = Query(default=None),
    municipality: Optional[str] = Query(default=None),
    destination: Optional[str] = Query(default=None),
    demand_level: Optional[str] = Query(default=None),
    supply_level: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
):
    """
    Aggregated map data for Leaflet/OpenStreetMap.
    Privacy rule: NEVER returns individual passenger GPS coordinates.
    """
    routes = compute_all_routes_overview(
        db,
        zone=zone,
        municipality=municipality,
        destination=destination,
        demand_level_filter=demand_level,
        supply_level_filter=supply_level,
    )
    stops = db.scalars(select(TaxiStop).where(TaxiStop.is_active == True)).all()  # noqa: E712
    zones = {z.id: z for z in db.scalars(select(TransportZone)).all()}

    stop_markers = []
    for s in stops:
        z_name = zones[s.zone_id].name if s.zone_id in zones else ""
        matching_routes = [r for r in routes if r["origin_zone"].lower() == z_name.lower()]
        est_dem = sum(r["estimated_demand"] for r in matching_routes)
        tot_sup = sum(r["total_supply"] for r in matching_routes)
        levels = [r["demand_level"] for r in matching_routes]
        top_level = (
            "PROCURA_ELEVADA"
            if "PROCURA_ELEVADA" in levels
            else "PROCURA_MODERADA"
            if "PROCURA_MODERADA" in levels
            else "PROCURA_BAIXA"
            if "PROCURA_BAIXA" in levels
            else "INSUFFICIENT_DATA"
        )
        stop_markers.append(
            {
                "id": s.id,
                "name": s.name,
                "zone_name": z_name,
                "landmark": s.landmark,
                "latitude": s.latitude,
                "longitude": s.longitude,
                "is_validated": s.is_validated,
                "estimated_demand": est_dem,
                "total_supply": tot_sup,
                "demand_level": top_level,
            }
        )

    db.commit()
    return {
        "stops": stop_markers,
        "routes": routes,
        "server_time_luanda": now_luanda().isoformat(),
    }


# --- 2. PASSENGER INTENTIONS & CONFIRMATIONS ---
@router.post("/intentions", status_code=status.HTTP_201_CREATED)
async def declare_travel_intention(
    payload: DeclareIntentionRequest,
    user: User = Depends(require_roles("PASSENGER", "ADMIN")),
    db: Session = Depends(get_db),
):
    if payload.origin_zone.strip().lower() == payload.destination_zone.strip().lower():
        raise HTTPException(status_code=400, detail="A origem e o destino devem ser diferentes.")

    passenger = db.scalar(select(Passenger).where(Passenger.user_id == user.id))
    if not passenger:
        passenger = Passenger(user_id=user.id, default_zone=payload.origin_zone)
        db.add(passenger)
        db.flush()

    expire_stale_records(db)
    thresholds = get_thresholds(db)

    # Anti-duplication rule (Section 6.1 & 12): prevent multiple simultaneous active intentions by same passenger
    existing = db.scalar(
        select(TransportIntention).where(
            TransportIntention.passenger_id == passenger.id,
            TransportIntention.status.in_(["DECLARED", "CONFIRMED_AT_STOP"]),
        )
    )
    if existing:
        if (
            existing.origin_zone_name.lower() == payload.origin_zone.strip().lower()
            and existing.destination_zone_name.lower() == payload.destination_zone.strip().lower()
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Já declarou uma intenção activa para esta mesma via. Actualize ou cancele a existente.",
            )
        # Cancel previous route intention cleanly when switching to a new route
        existing.status = "CANCELLED"

    origin_stop = _find_stop_for_zone(db, payload.origin_zone, payload.origin_stop_id)
    dest_stop = _find_stop_for_zone(db, payload.destination_zone, payload.destination_stop_id)
    route = _find_route(db, payload.origin_zone, payload.destination_zone)

    now = now_luanda()
    ttl_min = int(thresholds["intention_ttl_minutes"])

    # Flag suspicious unusually large passenger count declarations
    is_suspicious = payload.passenger_count > 12

    intention = TransportIntention(
        passenger_id=passenger.id,
        route_id=route.id if route else None,
        origin_stop_id=origin_stop.id,
        destination_stop_id=dest_stop.id,
        origin_zone_name=payload.origin_zone.strip(),
        destination_zone_name=payload.destination_zone.strip(),
        passenger_count=payload.passenger_count,
        status="DECLARED",
        source_type="DECLARED_PASSENGER",
        validation_status="FLAGGED_SUSPICIOUS" if is_suspicious else "UNVERIFIED",
        confidence_level="LOW" if is_suspicious else "MEDIUM",
        notes=payload.notes,
        last_confirmed_at=now,
        expires_at=now + timedelta(minutes=ttl_min),
    )
    db.add(intention)
    db.flush()

    if payload.passenger_count > 1:
        db.add(
            GroupIntention(
                transport_intention_id=intention.id,
                group_size=payload.passenger_count,
                notes=payload.notes,
            )
        )

    record_audit(
        db,
        action="INTENTION_DECLARED",
        entity_type="TransportIntention",
        entity_id=intention.id,
        actor_user_id=user.id,
        details={
            "origin": intention.origin_zone_name,
            "destination": intention.destination_zone_name,
            "count": intention.passenger_count,
            "suspicious": is_suspicious,
        },
    )
    eval_data = evaluate_corridor_status(
        db, intention.origin_zone_name, intention.destination_zone_name, include_alternatives=False
    )
    record_indicator_snapshot(db, eval_data, taxi_stop_id=origin_stop.id)
    db.commit()
    db.refresh(intention)

    await realtime_hub.publish(
        ["role:DRIVER", "role:ADMIN"],
        "MOBILITY_DEMAND_UPDATED",
        {
            "origin_zone": intention.origin_zone_name,
            "destination_zone": intention.destination_zone_name,
            "estimated_demand": eval_data["estimated_demand"],
        },
    )
    return {
        "intention": _serialize_intention(intention, thresholds),
        "corridor": eval_data,
    }


@router.get("/intentions/mine")
def list_my_intentions(
    user: User = Depends(require_roles("PASSENGER", "ADMIN")),
    db: Session = Depends(get_db),
):
    expire_stale_records(db)
    db.commit()
    thresholds = get_thresholds(db)
    passenger = db.scalar(select(Passenger).where(Passenger.user_id == user.id))
    if not passenger:
        return {"active": None, "history": []}

    rows = db.scalars(
        select(TransportIntention)
        .where(TransportIntention.passenger_id == passenger.id)
        .order_by(desc(TransportIntention.created_at))
        .limit(25)
    ).all()
    serialized = [_serialize_intention(r, thresholds) for r in rows]
    active = next((x for x in serialized if x["status"] in {"DECLARED", "CONFIRMED_AT_STOP"}), None)
    return {"active": active, "history": serialized}


@router.put("/intentions/{intention_id}")
def update_intention(
    intention_id: int,
    payload: UpdateIntentionRequest,
    user: User = Depends(require_roles("PASSENGER", "ADMIN")),
    db: Session = Depends(get_db),
):
    intention = db.get(TransportIntention, intention_id)
    if not intention:
        raise HTTPException(status_code=404, detail="Intenção de viagem não encontrada.")
    passenger = db.scalar(select(Passenger).where(Passenger.user_id == user.id))
    if user.role == "PASSENGER" and (not passenger or intention.passenger_id != passenger.id):
        raise HTTPException(status_code=403, detail="Não autorizado a alterar esta intenção.")
    if intention.status not in {"DECLARED", "CONFIRMED_AT_STOP"}:
        raise HTTPException(status_code=400, detail="Apenas intenções activas podem ser actualizadas.")

    thresholds = get_thresholds(db)
    now = now_luanda()
    if payload.destination_zone:
        dest_stop = _find_stop_for_zone(db, payload.destination_zone)
        intention.destination_stop_id = dest_stop.id
        intention.destination_zone_name = payload.destination_zone.strip()
        route = _find_route(db, intention.origin_zone_name, intention.destination_zone_name)
        intention.route_id = route.id if route else None
    if payload.passenger_count is not None:
        intention.passenger_count = payload.passenger_count
    if payload.notes is not None:
        intention.notes = payload.notes

    intention.last_confirmed_at = now
    intention.expires_at = now + timedelta(minutes=int(thresholds["intention_ttl_minutes"]))
    db.commit()
    return _serialize_intention(intention, thresholds)


@router.post("/intentions/{intention_id}/confirm-at-stop")
async def confirm_presence_at_stop(
    intention_id: int,
    payload: ConfirmAtStopRequest,
    user: User = Depends(require_roles("PASSENGER", "ADMIN")),
    db: Session = Depends(get_db),
):
    """Distinguishes declared travel intention from physically confirmed waiting passenger."""
    intention = db.get(TransportIntention, intention_id)
    if not intention:
        raise HTTPException(status_code=404, detail="Intenção não encontrada.")
    passenger = db.scalar(select(Passenger).where(Passenger.user_id == user.id))
    if user.role == "PASSENGER" and (not passenger or intention.passenger_id != passenger.id):
        raise HTTPException(status_code=403, detail="Não autorizado.")
    if intention.status not in {"DECLARED", "CONFIRMED_AT_STOP"}:
        raise HTTPException(status_code=400, detail="Intenção já expirada ou cancelada.")

    stop = db.get(TaxiStop, intention.origin_stop_id)
    dist_m = None
    consistent = True
    if payload.latitude is not None and payload.longitude is not None and stop:
        dist_km = haversine_km(payload.latitude, payload.longitude, stop.latitude, stop.longitude)
        dist_m = round(dist_km * 1000.0, 1)
        # Flag inconsistent location if > 2.5 km away from stop
        consistent = dist_km <= 2.5
        db.add(
            LocationUpdate(
                user_id=user.id,
                role=user.role,
                latitude=payload.latitude,
                longitude=payload.longitude,
                zone_name=intention.origin_zone_name,
                is_aggregated_only=True,
            )
        )

    thresholds = get_thresholds(db)
    now = now_luanda()
    db.add(
        PassengerConfirmation(
            intention_id=intention.id,
            passenger_id=intention.passenger_id,
            taxi_stop_id=intention.origin_stop_id,
            latitude=payload.latitude,
            longitude=payload.longitude,
            distance_to_stop_m=dist_m,
            is_location_consistent=consistent,
            confirmed_at=now,
        )
    )
    intention.status = "CONFIRMED_AT_STOP"
    intention.validation_status = "CONFIRMED" if consistent else "FLAGGED_SUSPICIOUS"
    intention.confidence_level = "HIGH" if consistent else "LOW"
    intention.last_confirmed_at = now
    intention.expires_at = now + timedelta(minutes=int(thresholds["intention_ttl_minutes"]))

    record_audit(
        db,
        action="PASSENGER_CONFIRMED_AT_STOP",
        entity_type="TransportIntention",
        entity_id=intention.id,
        actor_user_id=user.id,
        details={"stop_id": intention.origin_stop_id, "distance_m": dist_m, "consistent": consistent},
    )
    db.commit()
    await realtime_hub.publish(
        ["role:DRIVER", "role:ADMIN"],
        "MOBILITY_DEMAND_UPDATED",
        {"origin_zone": intention.origin_zone_name, "destination_zone": intention.destination_zone_name},
    )
    return {
        "intention": _serialize_intention(intention, thresholds),
        "location_consistent": consistent,
        "distance_to_stop_m": dist_m,
    }


@router.post("/intentions/{intention_id}/cancel")
async def cancel_intention(
    intention_id: int,
    user: User = Depends(require_roles("PASSENGER", "ADMIN")),
    db: Session = Depends(get_db),
):
    intention = db.get(TransportIntention, intention_id)
    if not intention:
        raise HTTPException(status_code=404, detail="Intenção não encontrada.")
    passenger = db.scalar(select(Passenger).where(Passenger.user_id == user.id))
    if user.role == "PASSENGER" and (not passenger or intention.passenger_id != passenger.id):
        raise HTTPException(status_code=403, detail="Não autorizado.")

    intention.status = "CANCELLED"
    record_audit(
        db,
        action="INTENTION_CANCELLED",
        entity_type="TransportIntention",
        entity_id=intention.id,
        actor_user_id=user.id,
    )
    db.commit()
    await realtime_hub.publish(
        ["role:DRIVER", "role:ADMIN"],
        "MOBILITY_DEMAND_UPDATED",
        {"origin_zone": intention.origin_zone_name, "destination_zone": intention.destination_zone_name},
    )
    return {"cancelled": True, "id": intention.id}


# --- 3. DRIVER DEMAND INTELLIGENCE & AVAILABILITY ---
@router.get("/driver/overview")
def get_driver_intelligence_overview(
    origin_zone: Optional[str] = Query(default=None),
    user: User = Depends(require_roles("DRIVER", "ADMIN")),
    db: Session = Depends(get_db),
):
    expire_stale_records(db)
    thresholds = get_thresholds(db)

    driver = db.scalar(select(Driver).where(Driver.user_id == user.id))
    active_report = (
        db.scalar(
            select(DriverReport)
            .where(DriverReport.driver_id == driver.id, DriverReport.is_active == True)  # noqa: E712
            .order_by(desc(DriverReport.last_confirmed_at))
        )
        if driver
        else None
    )

    routes = compute_all_routes_overview(db, zone=origin_zone)
    # Top destinations ranked by estimated demand
    dest_totals: dict[str, dict] = {}
    for r in routes:
        d = r["destination_zone"]
        if d not in dest_totals:
            dest_totals[d] = {"destination": d, "estimated_demand": 0, "total_supply": 0, "routes_count": 0}
        dest_totals[d]["estimated_demand"] += r["estimated_demand"]
        dest_totals[d]["total_supply"] += r["total_supply"]
        dest_totals[d]["routes_count"] += 1
    top_destinations = sorted(dest_totals.values(), key=lambda x: -x["estimated_demand"])

    hist = compute_historical_analytics(db)
    db.commit()

    report_payload = None
    if active_report:
        fr, age = classify_freshness(active_report.last_confirmed_at, active_report.expires_at, thresholds)
        report_payload = {
            "id": active_report.id,
            "origin_zone": active_report.origin_zone_name,
            "destination_zone": active_report.destination_zone_name,
            "availability_status": active_report.availability_status,
            "estimated_seats": active_report.estimated_seats,
            "freshness_status": fr,
            "age_minutes": age,
            "last_confirmed_at": active_report.last_confirmed_at.isoformat(),
            "expires_at": active_report.expires_at.isoformat(),
        }

    return {
        "safety_notice": (
            "Segurança rodoviária: consulte esta informação apenas com o veículo imobilizado. "
            "Os indicadores são estimativas baseadas nos últimos registos disponíveis."
        ),
        "my_report": report_payload,
        "routes": routes,
        "top_destinations": top_destinations,
        "peak_hours": hist["demand_by_hour"],
        "server_time_luanda": now_luanda().isoformat(),
    }


@router.post("/driver/availability")
async def declare_driver_availability(
    payload: DriverAvailabilityReportRequest,
    user: User = Depends(require_roles("DRIVER", "ADMIN")),
    db: Session = Depends(get_db),
):
    driver = db.scalar(select(Driver).where(Driver.user_id == user.id))
    if not driver:
        raise HTTPException(status_code=400, detail="Perfil de motorista não encontrado.")

    status_up = payload.availability_status.upper()
    if status_up not in {"AVAILABLE", "AT_STOP", "EN_ROUTE", "UNAVAILABLE"}:
        raise HTTPException(status_code=400, detail="Estado inválido.")

    thresholds = get_thresholds(db)
    now = now_luanda()
    ttl_min = int(thresholds["driver_report_ttl_minutes"])

    # Deactivate any prior active report by this driver (prevents double-counting same taxi!)
    prev_reports = db.scalars(
        select(DriverReport).where(DriverReport.driver_id == driver.id, DriverReport.is_active == True)  # noqa: E712
    ).all()
    for pr in prev_reports:
        pr.is_active = False

    stop = _find_stop_for_zone(db, payload.origin_zone, payload.taxi_stop_id)
    route = _find_route(db, payload.origin_zone, payload.destination_zone)

    report = DriverReport(
        driver_id=driver.id,
        route_id=route.id if route else None,
        taxi_stop_id=stop.id,
        origin_zone_name=payload.origin_zone.strip(),
        destination_zone_name=payload.destination_zone.strip(),
        availability_status=status_up,
        estimated_seats=payload.estimated_seats,
        source_type="DECLARED_DRIVER",
        validation_status="UNVERIFIED",
        confidence_level="MEDIUM",
        is_active=status_up != "UNAVAILABLE",
        reported_at=now,
        last_confirmed_at=now,
        expires_at=now + timedelta(minutes=ttl_min),
    )
    db.add(report)
    db.flush()

    if payload.latitude is not None and payload.longitude is not None:
        db.add(
            LocationUpdate(
                user_id=user.id,
                role=user.role,
                latitude=payload.latitude,
                longitude=payload.longitude,
                zone_name=payload.origin_zone.strip(),
                is_aggregated_only=False,
            )
        )

    record_audit(
        db,
        action="DRIVER_AVAILABILITY_REPORTED",
        entity_type="DriverReport",
        entity_id=report.id,
        actor_user_id=user.id,
        details={
            "origin": report.origin_zone_name,
            "destination": report.destination_zone_name,
            "status": status_up,
            "seats": report.estimated_seats,
        },
    )
    eval_data = evaluate_corridor_status(
        db, report.origin_zone_name, report.destination_zone_name, include_alternatives=False
    )
    record_indicator_snapshot(db, eval_data, taxi_stop_id=stop.id)
    db.commit()

    await realtime_hub.publish(
        ["role:PASSENGER", "role:ADMIN"],
        "MOBILITY_SUPPLY_UPDATED",
        {
            "origin_zone": report.origin_zone_name,
            "destination_zone": report.destination_zone_name,
            "total_supply": eval_data["total_supply"],
        },
    )
    return {
        "report": {
            "id": report.id,
            "origin_zone": report.origin_zone_name,
            "destination_zone": report.destination_zone_name,
            "availability_status": report.availability_status,
            "estimated_seats": report.estimated_seats,
            "expires_at": report.expires_at.isoformat(),
        },
        "corridor": eval_data,
    }


# --- 4. FIELD OBSERVATIONS & ADMIN OPERATIONS ---
@router.post("/observations/field", status_code=status.HTTP_201_CREATED)
async def record_field_observation(
    payload: FieldObservationRequest,
    user: User = Depends(require_roles("ADMIN", "FIELD_COLLECTOR")),
    db: Session = Depends(get_db),
):
    stop = _find_stop_for_zone(db, payload.origin_zone, payload.taxi_stop_id)
    route = _find_route(db, payload.origin_zone, payload.destination_zone)
    thresholds = get_thresholds(db)
    now = now_luanda()
    ttl_min = int(thresholds["observation_ttl_minutes"])

    val_status = "VALIDATED" if (user.role == "ADMIN" and payload.auto_validate) else "PENDING"
    conf = "HIGH" if val_status == "VALIDATED" else "MEDIUM"

    supply_obs = SupplyObservation(
        observer_user_id=user.id,
        taxi_stop_id=stop.id,
        route_id=route.id if route else None,
        origin_zone_name=payload.origin_zone.strip(),
        destination_zone_name=payload.destination_zone.strip(),
        observed_taxis_count=payload.observed_taxis_count,
        road_condition=payload.road_condition,
        notes=payload.notes,
        source_type="OBSERVED_FIELD",
        validation_status=val_status,
        confidence_level=conf,
        observed_at=now,
        expires_at=now + timedelta(minutes=ttl_min),
    )
    demand_obs = DemandObservation(
        observer_user_id=user.id,
        taxi_stop_id=stop.id,
        route_id=route.id if route else None,
        origin_zone_name=payload.origin_zone.strip(),
        destination_zone_name=payload.destination_zone.strip(),
        observed_passengers_count=payload.observed_passengers_count,
        estimated_wait_min=payload.estimated_wait_min,
        notes=payload.notes,
        source_type="OBSERVED_FIELD",
        validation_status=val_status,
        confidence_level=conf,
        observed_at=now,
        expires_at=now + timedelta(minutes=ttl_min),
    )
    if route and val_status == "VALIDATED":
        route.road_condition = payload.road_condition

    db.add_all([supply_obs, demand_obs])
    db.flush()

    record_audit(
        db,
        action="FIELD_OBSERVATION_RECORDED",
        entity_type="FieldObservation",
        entity_id=f"S{supply_obs.id}-D{demand_obs.id}",
        actor_user_id=user.id,
        details={
            "origin": payload.origin_zone,
            "destination": payload.destination_zone,
            "taxis": payload.observed_taxis_count,
            "passengers": payload.observed_passengers_count,
            "validation_status": val_status,
        },
    )
    eval_data = evaluate_corridor_status(
        db, payload.origin_zone, payload.destination_zone, include_alternatives=False
    )
    record_indicator_snapshot(db, eval_data, taxi_stop_id=stop.id)
    db.commit()

    await realtime_hub.publish(
        ["role:PASSENGER", "role:DRIVER", "role:ADMIN"],
        "FIELD_OBSERVATION_ADDED",
        {"origin_zone": payload.origin_zone, "destination_zone": payload.destination_zone},
    )
    return {
        "supply_observation_id": supply_obs.id,
        "demand_observation_id": demand_obs.id,
        "validation_status": val_status,
        "corridor": eval_data,
    }


@router.get("/admin/dashboard")
def get_admin_info_dashboard(
    user: User = Depends(require_roles("ADMIN", "FIELD_COLLECTOR")),
    db: Session = Depends(get_db),
):
    expire_stale_records(db)
    thresholds = get_thresholds(db)

    active_passengers = db.scalar(select(func.count(Passenger.id))) or 0
    active_drivers = db.scalar(select(func.count(Driver.id))) or 0
    active_intentions = db.scalars(
        select(TransportIntention).where(TransportIntention.status.in_(["DECLARED", "CONFIRMED_AT_STOP"]))
    ).all()
    confirmed_passengers = sum(
        i.passenger_count for i in active_intentions if i.status == "CONFIRMED_AT_STOP"
    )
    active_driver_reports = db.scalars(
        select(DriverReport).where(
            DriverReport.is_active == True,  # noqa: E712
            DriverReport.availability_status.in_(["AVAILABLE", "AT_STOP"]),
        )
    ).all()

    routes_overview = compute_all_routes_overview(db)
    analytics = compute_historical_analytics(db)

    # Observations queue (recent + pending)
    demand_obs = db.scalars(select(DemandObservation).order_by(desc(DemandObservation.observed_at)).limit(25)).all()
    supply_obs = db.scalars(select(SupplyObservation).order_by(desc(SupplyObservation.observed_at)).limit(25)).all()
    configs = db.scalars(select(PlatformConfig).order_by(PlatformConfig.key)).all()
    logs = db.scalars(select(AuditLog).order_by(desc(AuditLog.created_at)).limit(30)).all()
    users = db.scalars(select(User).order_by(User.id)).all()

    db.commit()
    return {
        "kpis": {
            "active_passengers": active_passengers,
            "active_drivers": active_drivers,
            "active_intentions_count": len(active_intentions),
            "declared_waiting_passengers": sum(i.passenger_count for i in active_intentions),
            "confirmed_passengers": confirmed_passengers,
            "available_drivers": len({d.driver_id for d in active_driver_reports}),
            "validated_data_pct": analytics["data_quality"]["validated_pct"],
            "stale_or_expired_pct": analytics["data_quality"]["stale_or_expired_pct"],
            "pending_validations": analytics["data_quality"]["pending_validations"],
            "suspicious_records": analytics["data_quality"]["suspicious_records"],
        },
        "routes": routes_overview,
        "analytics": analytics,
        "demand_observations": [
            {
                "id": o.id,
                "origin_zone": o.origin_zone_name,
                "destination_zone": o.destination_zone_name,
                "observed_passengers_count": o.observed_passengers_count,
                "estimated_wait_min": o.estimated_wait_min,
                "validation_status": o.validation_status,
                "freshness_status": classify_freshness(o.observed_at, o.expires_at, thresholds)[0],
                "notes": o.notes,
                "is_demo_data": o.is_demo_data,
                "observed_at": o.observed_at.isoformat() if o.observed_at else None,
            }
            for o in demand_obs
        ],
        "supply_observations": [
            {
                "id": o.id,
                "origin_zone": o.origin_zone_name,
                "destination_zone": o.destination_zone_name,
                "observed_taxis_count": o.observed_taxis_count,
                "road_condition": o.road_condition,
                "validation_status": o.validation_status,
                "freshness_status": classify_freshness(o.observed_at, o.expires_at, thresholds)[0],
                "notes": o.notes,
                "is_demo_data": o.is_demo_data,
                "observed_at": o.observed_at.isoformat() if o.observed_at else None,
            }
            for o in supply_obs
        ],
        "active_intentions": [_serialize_intention(i, thresholds) for i in active_intentions],
        "configs": [{"key": c.key, "value": c.value, "description": c.description} for c in configs],
        "users": [
            {"id": u.id, "full_name": u.full_name, "email": u.email, "phone": u.phone, "role": u.role, "is_active": u.is_active}
            for u in users
        ],
        "audit_logs": [
            {
                "id": l.id,
                "action": l.action,
                "entity_type": l.entity_type,
                "entity_id": l.entity_id,
                "details_json": l.details_json,
                "created_at": l.created_at.isoformat() if l.created_at else None,
            }
            for l in logs
        ],
    }


@router.post("/admin/validations/{target_type}/{target_id}")
def validate_record(
    target_type: str,
    target_id: int,
    payload: DataValidationDecisionRequest,
    user: User = Depends(require_roles("ADMIN")),
    db: Session = Depends(get_db),
):
    tt = target_type.upper()
    dec = payload.decision.upper()
    if dec not in {"VALIDATED", "REJECTED", "FLAGGED_SUSPICIOUS", "FLAGGED_DUPLICATE"}:
        raise HTTPException(status_code=400, detail="Decisão de validação inválida.")

    if tt == "DEMAND_OBS":
        obj = db.get(DemandObservation, target_id)
    elif tt == "SUPPLY_OBS":
        obj = db.get(SupplyObservation, target_id)
    elif tt == "INTENTION":
        obj = db.get(TransportIntention, target_id)
    elif tt == "DRIVER_REPORT":
        obj = db.get(DriverReport, target_id)
    else:
        raise HTTPException(status_code=400, detail="Tipo de registo inválido.")

    if not obj:
        raise HTTPException(status_code=404, detail="Registo não encontrado.")

    obj.validation_status = dec
    if dec == "VALIDATED":
        obj.confidence_level = "HIGH"
    elif dec in {"REJECTED", "FLAGGED_SUSPICIOUS", "FLAGGED_DUPLICATE"}:
        obj.confidence_level = "LOW"
        if hasattr(obj, "is_active"):
            obj.is_active = False

    db.add(
        DataValidation(
            target_type=tt,
            target_id=target_id,
            validator_user_id=user.id,
            decision=dec,
            reason=payload.reason,
        )
    )
    record_audit(
        db,
        action=f"DATA_{dec}",
        entity_type=tt,
        entity_id=target_id,
        actor_user_id=user.id,
        details={"reason": payload.reason},
    )
    db.commit()
    return {"target_type": tt, "target_id": target_id, "decision": dec}


@router.post("/admin/stops", status_code=status.HTTP_201_CREATED)
def admin_create_stop(
    payload: CreateStopRequest,
    user: User = Depends(require_roles("ADMIN")),
    db: Session = Depends(get_db),
):
    zone = db.get(TransportZone, payload.zone_id)
    if not zone:
        raise HTTPException(status_code=404, detail="Zona não encontrada.")
    stop = TaxiStop(
        zone_id=zone.id,
        name=payload.name.strip(),
        landmark=payload.landmark,
        latitude=payload.latitude,
        longitude=payload.longitude,
        is_validated=payload.is_validated,
        is_active=True,
    )
    db.add(stop)
    db.flush()
    record_audit(
        db,
        action="STOP_CREATED",
        entity_type="TaxiStop",
        entity_id=stop.id,
        actor_user_id=user.id,
        details={"name": stop.name, "zone": zone.name},
    )
    db.commit()
    return {"id": stop.id, "name": stop.name, "zone_name": zone.name, "is_validated": stop.is_validated}


@router.post("/admin/routes", status_code=status.HTTP_201_CREATED)
def admin_create_route(
    payload: CreateRouteRequest,
    user: User = Depends(require_roles("ADMIN")),
    db: Session = Depends(get_db),
):
    if db.scalar(select(TransportRoute).where(TransportRoute.code == payload.code.strip().upper())):
        raise HTTPException(status_code=409, detail="Código de via já existente.")
    route = TransportRoute(
        code=payload.code.strip().upper(),
        name=payload.name.strip(),
        origin_zone_id=payload.origin_zone_id,
        destination_zone_id=payload.destination_zone_id,
        corridor_description=payload.corridor_description,
        road_condition=payload.road_condition,
        is_active=True,
    )
    db.add(route)
    db.flush()
    record_audit(
        db,
        action="ROUTE_CREATED",
        entity_type="TransportRoute",
        entity_id=route.id,
        actor_user_id=user.id,
        details={"code": route.code, "name": route.name},
    )
    db.commit()
    return {"id": route.id, "code": route.code, "name": route.name}


@router.put("/admin/config")
def admin_update_configs(
    payload: UpdateConfigRequest,
    user: User = Depends(require_roles("ADMIN")),
    db: Session = Depends(get_db),
):
    updated = []
    for k, v in payload.updates.items():
        cfg = db.scalar(select(PlatformConfig).where(PlatformConfig.key == k))
        if cfg:
            cfg.value = str(v)
            updated.append(k)
    record_audit(
        db,
        action="THRESHOLDS_UPDATED",
        entity_type="PlatformConfig",
        actor_user_id=user.id,
        details=payload.updates,
    )
    db.commit()
    return {"updated_keys": updated, "thresholds": get_thresholds(db)}


@router.post("/admin/expire-stale")
def trigger_expiration_sweep(
    user: User = Depends(require_roles("ADMIN")),
    db: Session = Depends(get_db),
):
    res = expire_stale_records(db)
    db.commit()
    return res
