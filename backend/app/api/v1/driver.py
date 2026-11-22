import random
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.api.deps import require_roles
from app.api.v1.serializers import serialize_request, serialize_trip
from app.core.config import now_luanda, settings
from app.db.session import get_db
from app.models.finance import Commission, Tariff
from app.models.fleet import DriverAvailability, Vehicle, VehicleLocation
from app.models.identity import Driver, Passenger, User
from app.models.mobility import TransportRequest, Trip, TripPassenger
from app.schemas.schemas import (
    DriverLocationUpdate,
    DriverStatusUpdate,
    RegisterVehicleRequest,
    ValidateBoardingRequest,
)
from app.services.audit_service import create_notification, record_audit
from app.services.card_wallet_service import validate_and_debit_boarding
from app.services.geo_service import (
    detect_nearest_zone,
    estimate_duration_minutes,
    interpolate_position,
    road_distance_km,
)
from app.services.intelligence_service import compute_zone_demand_pressure
from app.services.matching_service import (
    dispatch_request_to_next_driver,
    get_active_tariff,
    redistribute_expired_offers,
)
from app.services.realtime_hub import realtime_hub

router = APIRouter(prefix="/driver", tags=["Motorista & Frota"])


def _get_driver_or_400(db: Session, user: User) -> Driver:
    driver = db.scalar(select(Driver).where(Driver.user_id == user.id))
    if not driver:
        raise HTTPException(status_code=400, detail="Perfil de motorista não encontrado.")
    return driver


@router.get("/dashboard")
def get_driver_dashboard(
    user: User = Depends(require_roles("DRIVER")),
    db: Session = Depends(get_db),
):
    driver = _get_driver_or_400(db, user)
    redistribute_expired_offers(db)
    db.commit()

    avail = db.scalar(select(DriverAvailability).where(DriverAvailability.driver_id == driver.id))
    vehicles = db.scalars(select(Vehicle).where(Vehicle.driver_id == driver.id)).all()

    pending_offer = db.scalar(
        select(TransportRequest)
        .where(
            TransportRequest.offered_driver_id == driver.id,
            TransportRequest.status == "OFFERED",
        )
        .order_by(desc(TransportRequest.created_at))
    )
    active_trip = db.scalar(
        select(Trip)
        .where(
            Trip.driver_id == driver.id,
            Trip.status.in_(["DRIVER_EN_ROUTE", "DRIVER_ARRIVED", "IN_PROGRESS"]),
        )
        .order_by(desc(Trip.created_at))
    )
    recent_trips = db.scalars(
        select(Trip)
        .where(Trip.driver_id == driver.id, Trip.status == "COMPLETED")
        .order_by(desc(Trip.completed_at))
        .limit(15)
    ).all()

    gross_total = db.scalar(
        select(func.coalesce(func.sum(Commission.gross_fare_aoa), 0)).where(
            Commission.driver_id == driver.id
        )
    )
    fee_total = db.scalar(
        select(func.coalesce(func.sum(Commission.platform_fee_aoa), 0)).where(
            Commission.driver_id == driver.id
        )
    )
    net_total = db.scalar(
        select(func.coalesce(func.sum(Commission.driver_net_aoa), 0)).where(
            Commission.driver_id == driver.id
        )
    )

    demand_zones = compute_zone_demand_pressure(db)[:4]

    return {
        "driver": {
            "id": driver.id,
            "full_name": user.full_name,
            "phone": user.phone,
            "license_number": driver.license_number,
            "national_id": driver.national_id,
            "verification_status": driver.verification_status,
            "verification_notes": driver.verification_notes,
            "rating_avg": float(driver.rating_avg),
            "total_trips": driver.total_trips,
        },
        "availability": {
            "status": avail.status if avail else "OFFLINE",
            "active_vehicle_id": avail.active_vehicle_id if avail else None,
            "current_lat": avail.current_lat if avail else -8.8805,
            "current_lng": avail.current_lng if avail else 13.2175,
            "current_zone": avail.current_zone if avail else "Gamek",
        },
        "vehicles": [
            {
                "id": v.id,
                "make": v.make,
                "model": v.model,
                "year": v.year,
                "color": v.color,
                "license_plate": v.license_plate,
                "vehicle_type": v.vehicle_type,
                "capacity": v.capacity,
                "is_active": v.is_active,
            }
            for v in vehicles
        ],
        "pending_offer": serialize_request(db, pending_offer) if pending_offer else None,
        "active_trip": serialize_trip(db, active_trip) if active_trip else None,
        "recent_trips": [serialize_trip(db, t) for t in recent_trips],
        "earnings": {
            "gross_aoa": float(gross_total or 0),
            "platform_commission_aoa": float(fee_total or 0),
            "driver_net_aoa": float(net_total or 0),
        },
        "opportunity_zones": demand_zones,
    }


@router.put("/status")
async def update_driver_status(
    payload: DriverStatusUpdate,
    user: User = Depends(require_roles("DRIVER")),
    db: Session = Depends(get_db),
):
    driver = _get_driver_or_400(db, user)
    new_status = payload.status.upper()
    if new_status not in {"AVAILABLE", "BUSY", "OFFLINE"}:
        raise HTTPException(status_code=400, detail="Estado inválido. Use AVAILABLE, BUSY ou OFFLINE.")

    if new_status == "AVAILABLE" and driver.verification_status != "APPROVED":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="A sua documentação ainda aguarda aprovação do administrador para ficar disponível.",
        )

    avail = db.scalar(select(DriverAvailability).where(DriverAvailability.driver_id == driver.id))
    if not avail:
        veh = db.scalar(select(Vehicle).where(Vehicle.driver_id == driver.id, Vehicle.is_active == True))  # noqa: E712
        avail = DriverAvailability(driver_id=driver.id, active_vehicle_id=veh.id if veh else None)
        db.add(avail)

    if new_status == "AVAILABLE" and not avail.active_vehicle_id:
        veh = db.scalar(select(Vehicle).where(Vehicle.driver_id == driver.id, Vehicle.is_active == True))  # noqa: E712
        if not veh:
            raise HTTPException(
                status_code=400,
                detail="Registe pelo menos um veículo ativo antes de ficar disponível.",
            )
        avail.active_vehicle_id = veh.id

    avail.status = new_status
    if payload.latitude is not None and payload.longitude is not None:
        avail.current_lat = payload.latitude
        avail.current_lng = payload.longitude
        avail.current_zone = payload.zone_name or detect_nearest_zone(payload.latitude, payload.longitude)
    elif payload.zone_name:
        avail.current_zone = payload.zone_name

    # If driver just became AVAILABLE, attempt to assign any waiting PENDING request!
    assigned_req = None
    if new_status == "AVAILABLE":
        waiting = db.scalar(
            select(TransportRequest)
            .where(TransportRequest.status == "PENDING")
            .order_by(TransportRequest.created_at)
        )
        if waiting:
            chosen = dispatch_request_to_next_driver(db, waiting)
            if chosen and chosen["driver"].id == driver.id:
                assigned_req = waiting

    db.commit()
    await realtime_hub.publish(
        ["role:ADMIN"],
        "DRIVER_STATUS_UPDATED",
        {"driver_id": driver.id, "status": avail.status, "zone": avail.current_zone},
    )
    if assigned_req:
        await realtime_hub.publish(
            [f"user:{user.id}", "role:ADMIN"],
            "NEW_OFFER",
            serialize_request(db, assigned_req),
        )

    return {
        "status": avail.status,
        "current_zone": avail.current_zone,
        "current_lat": avail.current_lat,
        "current_lng": avail.current_lng,
    }


@router.post("/location")
async def update_driver_location(
    payload: DriverLocationUpdate,
    user: User = Depends(require_roles("DRIVER")),
    db: Session = Depends(get_db),
):
    driver = _get_driver_or_400(db, user)
    avail = db.scalar(select(DriverAvailability).where(DriverAvailability.driver_id == driver.id))
    if not avail:
        raise HTTPException(status_code=400, detail="Estado do motorista não inicializado.")

    zone = payload.zone_name or detect_nearest_zone(payload.latitude, payload.longitude)
    avail.current_lat = payload.latitude
    avail.current_lng = payload.longitude
    avail.current_zone = zone

    if avail.active_vehicle_id:
        db.add(
            VehicleLocation(
                vehicle_id=avail.active_vehicle_id,
                latitude=payload.latitude,
                longitude=payload.longitude,
                heading=payload.heading,
                speed_kmh=payload.speed_kmh,
                zone_name=zone,
            )
        )

    # Update ETA if there is an active trip
    active_trip = db.scalar(
        select(Trip).where(
            Trip.driver_id == driver.id,
            Trip.status.in_(["DRIVER_EN_ROUTE", "DRIVER_ARRIVED", "IN_PROGRESS"]),
        )
    )
    channels = ["role:ADMIN"]
    if active_trip:
        req = db.get(TransportRequest, active_trip.transport_request_id)
        if req:
            target_lat = req.pickup_lat if active_trip.status == "DRIVER_EN_ROUTE" else req.dropoff_lat
            target_lng = req.pickup_lng if active_trip.status == "DRIVER_EN_ROUTE" else req.dropoff_lng
            dist = road_distance_km(payload.latitude, payload.longitude, target_lat, target_lng)
            active_trip.eta_minutes = estimate_duration_minutes(dist, traffic_factor=1.15)
            p = db.get(Passenger, req.passenger_id)
            if p:
                channels.append(f"user:{p.user_id}")

    db.commit()
    await realtime_hub.publish(
        channels,
        "DRIVER_LOCATION",
        {
            "driver_id": driver.id,
            "vehicle_id": avail.active_vehicle_id,
            "latitude": payload.latitude,
            "longitude": payload.longitude,
            "zone": zone,
            "trip_id": active_trip.id if active_trip else None,
            "eta_minutes": active_trip.eta_minutes if active_trip else None,
        },
    )
    return {"updated": True, "zone": zone, "latitude": payload.latitude, "longitude": payload.longitude}


@router.post("/vehicles", status_code=status.HTTP_201_CREATED)
def register_vehicle(
    payload: RegisterVehicleRequest,
    user: User = Depends(require_roles("DRIVER")),
    db: Session = Depends(get_db),
):
    driver = _get_driver_or_400(db, user)
    plate = payload.license_plate.strip().upper()
    if db.scalar(select(Vehicle).where(Vehicle.license_plate == plate)):
        raise HTTPException(status_code=409, detail="Matrícula já registada na plataforma.")

    veh = Vehicle(
        driver_id=driver.id,
        make=payload.make.strip(),
        model=payload.model.strip(),
        year=payload.year,
        color=payload.color.strip(),
        license_plate=plate,
        vehicle_type=payload.vehicle_type,
        capacity=payload.capacity,
        is_active=True,
    )
    db.add(veh)
    db.flush()

    avail = db.scalar(select(DriverAvailability).where(DriverAvailability.driver_id == driver.id))
    if avail and not avail.active_vehicle_id:
        avail.active_vehicle_id = veh.id

    record_audit(
        db,
        action="VEHICLE_REGISTERED",
        entity_type="Vehicle",
        entity_id=veh.id,
        actor_user_id=user.id,
        details={"plate": plate, "make": veh.make, "model": veh.model},
    )
    db.commit()
    return {
        "id": veh.id,
        "make": veh.make,
        "model": veh.model,
        "license_plate": veh.license_plate,
        "capacity": veh.capacity,
    }


@router.post("/offers/{request_id}/accept")
async def accept_offer(
    request_id: int,
    user: User = Depends(require_roles("DRIVER")),
    db: Session = Depends(get_db),
):
    driver = _get_driver_or_400(db, user)
    if driver.verification_status != "APPROVED":
        raise HTTPException(status_code=403, detail="Motorista não verificado.")

    req = db.get(TransportRequest, request_id)
    if not req or req.status != "OFFERED" or req.offered_driver_id != driver.id:
        raise HTTPException(
            status_code=409,
            detail="Esta solicitação já expirou ou foi atribuída a outro motorista.",
        )

    avail = db.scalar(select(DriverAvailability).where(DriverAvailability.driver_id == driver.id))
    if not avail or not avail.active_vehicle_id:
        raise HTTPException(status_code=400, detail="Nenhum veículo ativo associado ao motorista.")

    vehicle = db.get(Vehicle, avail.active_vehicle_id)
    tariff = get_active_tariff(db, vehicle.vehicle_type if vehicle else "TAXI_SEDAN")

    d_lat = avail.current_lat or -8.8805
    d_lng = avail.current_lng or 13.2175
    dist_to_pickup = road_distance_km(d_lat, d_lng, req.pickup_lat, req.pickup_lng)
    eta_min = estimate_duration_minutes(dist_to_pickup, traffic_factor=1.15)
    boarding_code = f"{random.randint(1000, 9999)}"

    req.status = "ACCEPTED"
    avail.status = "BUSY"

    trip = Trip(
        transport_request_id=req.id,
        driver_id=driver.id,
        vehicle_id=avail.active_vehicle_id,
        tariff_id=tariff.id if tariff.id else None,
        boarding_code=boarding_code,
        status="DRIVER_EN_ROUTE",
        eta_minutes=eta_min,
        fare_per_passenger_aoa=req.fare_per_passenger_aoa,
        total_fare_aoa=req.estimated_total_fare_aoa,
        paid_total_aoa=Decimal("0.00"),
    )
    db.add(trip)
    db.flush()

    passenger = db.get(Passenger, req.passenger_id)
    if passenger:
        create_notification(
            db,
            user_id=passenger.user_id,
            title="Motorista a caminho!",
            message=(
                f"{user.full_name} aceitou a sua viagem ({vehicle.make} {vehicle.model} • {vehicle.license_plate}). "
                f"Código de embarque: {boarding_code}."
            ),
            category="TRIP",
        )

    record_audit(
        db,
        action="TRIP_ACCEPTED",
        entity_type="Trip",
        entity_id=trip.id,
        actor_user_id=user.id,
        details={"request_id": req.id, "vehicle_plate": vehicle.license_plate, "boarding_code": boarding_code},
    )
    db.commit()
    db.refresh(trip)

    serialized = serialize_trip(db, trip)
    channels = ["role:ADMIN"]
    if passenger:
        channels.append(f"user:{passenger.user_id}")
    await realtime_hub.publish(channels, "TRIP_ACCEPTED", serialized)
    return serialized


@router.post("/offers/{request_id}/reject")
async def reject_offer(
    request_id: int,
    user: User = Depends(require_roles("DRIVER")),
    db: Session = Depends(get_db),
):
    driver = _get_driver_or_400(db, user)
    req = db.get(TransportRequest, request_id)
    if not req or req.status != "OFFERED" or req.offered_driver_id != driver.id:
        raise HTTPException(status_code=404, detail="Oferta não encontrada ou já expirada.")

    rejected = {int(x) for x in req.rejected_driver_ids.split(",") if x.strip().isdigit()}
    rejected.add(driver.id)
    req.rejected_driver_ids = ",".join(str(i) for i in sorted(rejected))

    record_audit(
        db,
        action="OFFER_REJECTED",
        entity_type="TransportRequest",
        entity_id=req.id,
        actor_user_id=user.id,
        details={"driver_id": driver.id},
    )
    chosen = dispatch_request_to_next_driver(db, req)
    db.commit()

    channels = ["role:ADMIN"]
    if chosen:
        channels.append(f"user:{chosen['driver'].user_id}")
        await realtime_hub.publish(channels, "NEW_OFFER", serialize_request(db, req))
    else:
        await realtime_hub.publish(channels, "REQUEST_PENDING_NO_DRIVER", {"request_id": req.id})

    return {
        "rejected": True,
        "redistributed_to_driver_id": chosen["driver"].id if chosen else None,
        "request_status": req.status,
    }


@router.post("/trips/{trip_id}/simulate-step")
async def simulate_trip_gps_step(
    trip_id: int,
    user: User = Depends(require_roles("DRIVER")),
    db: Session = Depends(get_db),
):
    """Advance driver's GPS coordinate smoothly toward pickup (or dropoff once IN_PROGRESS)."""
    driver = _get_driver_or_400(db, user)
    trip = db.get(Trip, trip_id)
    if not trip or trip.driver_id != driver.id:
        raise HTTPException(status_code=404, detail="Viagem não encontrada.")

    req = db.get(TransportRequest, trip.transport_request_id)
    avail = db.scalar(select(DriverAvailability).where(DriverAvailability.driver_id == driver.id))
    if not req or not avail:
        raise HTTPException(status_code=400, detail="Dados da viagem incompletos.")

    target_lat = req.pickup_lat if trip.status in {"DRIVER_EN_ROUTE", "DRIVER_ARRIVED"} else req.dropoff_lat
    target_lng = req.pickup_lng if trip.status in {"DRIVER_EN_ROUTE", "DRIVER_ARRIVED"} else req.dropoff_lng

    new_lat, new_lng, heading = interpolate_position(
        avail.current_lat or req.pickup_lat,
        avail.current_lng or req.pickup_lng,
        target_lat,
        target_lng,
        step_fraction=0.45,
    )
    zone = detect_nearest_zone(new_lat, new_lng)
    avail.current_lat = new_lat
    avail.current_lng = new_lng
    avail.current_zone = zone

    if avail.active_vehicle_id:
        db.add(
            VehicleLocation(
                vehicle_id=avail.active_vehicle_id,
                latitude=new_lat,
                longitude=new_lng,
                heading=heading,
                speed_kmh=32.0,
                zone_name=zone,
            )
        )

    dist = road_distance_km(new_lat, new_lng, target_lat, target_lng)
    trip.eta_minutes = max(1, estimate_duration_minutes(dist, traffic_factor=1.1))
    db.commit()

    passenger = db.get(Passenger, req.passenger_id)
    channels = ["role:ADMIN"]
    if passenger:
        channels.append(f"user:{passenger.user_id}")
    await realtime_hub.publish(
        channels,
        "DRIVER_LOCATION",
        {
            "driver_id": driver.id,
            "trip_id": trip.id,
            "latitude": new_lat,
            "longitude": new_lng,
            "zone": zone,
            "eta_minutes": trip.eta_minutes,
        },
    )
    return {
        "latitude": new_lat,
        "longitude": new_lng,
        "zone": zone,
        "eta_minutes": trip.eta_minutes,
        "distance_remaining_km": dist,
    }


@router.post("/trips/{trip_id}/arrive")
async def mark_driver_arrived(
    trip_id: int,
    user: User = Depends(require_roles("DRIVER")),
    db: Session = Depends(get_db),
):
    driver = _get_driver_or_400(db, user)
    trip = db.get(Trip, trip_id)
    if not trip or trip.driver_id != driver.id:
        raise HTTPException(status_code=404, detail="Viagem não encontrada.")
    if trip.status != "DRIVER_EN_ROUTE":
        raise HTTPException(status_code=400, detail="Só é possível marcar chegada quando está a caminho.")

    req = db.get(TransportRequest, trip.transport_request_id)
    avail = db.scalar(select(DriverAvailability).where(DriverAvailability.driver_id == driver.id))
    if req and avail:
        avail.current_lat = req.pickup_lat
        avail.current_lng = req.pickup_lng
        avail.current_zone = req.pickup_zone

    trip.status = "DRIVER_ARRIVED"
    trip.eta_minutes = 0
    trip.arrived_at = now_luanda()

    passenger = db.get(Passenger, req.passenger_id) if req else None
    if passenger:
        create_notification(
            db,
            user_id=passenger.user_id,
            title="Motorista chegou ao ponto de recolha",
            message=f"Apresente o seu cartão QR ao motorista. Código: {trip.boarding_code}.",
            category="TRIP",
        )
    record_audit(db, action="DRIVER_ARRIVED", entity_type="Trip", entity_id=trip.id, actor_user_id=user.id)
    db.commit()

    serialized = serialize_trip(db, trip)
    channels = ["role:ADMIN"]
    if passenger:
        channels.append(f"user:{passenger.user_id}")
    await realtime_hub.publish(channels, "TRIP_UPDATED", serialized)
    return serialized


@router.post("/trips/{trip_id}/validate-card")
async def validate_passenger_card_for_trip(
    trip_id: int,
    payload: ValidateBoardingRequest,
    user: User = Depends(require_roles("DRIVER")),
    db: Session = Depends(get_db),
):
    driver = _get_driver_or_400(db, user)
    trip = db.get(Trip, trip_id)
    if not trip or trip.driver_id != driver.id:
        raise HTTPException(status_code=404, detail="Viagem não encontrada.")

    result = validate_and_debit_boarding(
        db=db,
        trip=trip,
        card_identifier=payload.card_identifier,
        driver_user_id=user.id,
        idempotency_key=payload.idempotency_key,
    )
    db.commit()
    db.refresh(trip)

    req = db.get(TransportRequest, trip.transport_request_id)
    passenger = db.get(Passenger, req.passenger_id) if req else None
    channels = ["role:ADMIN"]
    if passenger:
        channels.append(f"user:{passenger.user_id}")
    serialized = serialize_trip(db, trip)
    await realtime_hub.publish(
        channels,
        "BOARDING_VALIDATED",
        {"validation": result, "trip": serialized},
    )
    return {"validation": result, "trip": serialized}


@router.post("/trips/{trip_id}/start")
async def start_trip(
    trip_id: int,
    user: User = Depends(require_roles("DRIVER")),
    db: Session = Depends(get_db),
):
    driver = _get_driver_or_400(db, user)
    trip = db.get(Trip, trip_id)
    if not trip or trip.driver_id != driver.id:
        raise HTTPException(status_code=404, detail="Viagem não encontrada.")
    if trip.status not in {"DRIVER_EN_ROUTE", "DRIVER_ARRIVED"}:
        raise HTTPException(status_code=400, detail="Estado inválido para iniciar a viagem.")

    boarded_count = db.scalar(
        select(func.count(TripPassenger.id)).where(
            TripPassenger.trip_id == trip.id, TripPassenger.boarding_status == "BOARDED"
        )
    )
    if not boarded_count or boarded_count < 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Valide pelo menos um cartão QR de embarque antes de iniciar a viagem.",
        )

    trip.status = "IN_PROGRESS"
    trip.started_at = now_luanda()
    req = db.get(TransportRequest, trip.transport_request_id)
    if req:
        trip.eta_minutes = req.estimated_duration_min

    passenger = db.get(Passenger, req.passenger_id) if req else None
    if passenger:
        create_notification(
            db,
            user_id=passenger.user_id,
            title="Viagem iniciada",
            message=f"Boa viagem com destino a {req.dropoff_zone}!",
            category="TRIP",
        )
    record_audit(db, action="TRIP_STARTED", entity_type="Trip", entity_id=trip.id, actor_user_id=user.id)
    db.commit()

    serialized = serialize_trip(db, trip)
    channels = ["role:ADMIN"]
    if passenger:
        channels.append(f"user:{passenger.user_id}")
    await realtime_hub.publish(channels, "TRIP_UPDATED", serialized)
    return serialized


@router.post("/trips/{trip_id}/complete")
async def complete_trip(
    trip_id: int,
    user: User = Depends(require_roles("DRIVER")),
    db: Session = Depends(get_db),
):
    driver = _get_driver_or_400(db, user)
    trip = db.get(Trip, trip_id)
    if not trip or trip.driver_id != driver.id:
        raise HTTPException(status_code=404, detail="Viagem não encontrada.")
    if trip.status != "IN_PROGRESS":
        raise HTTPException(status_code=400, detail="Apenas viagens em curso podem ser concluídas.")

    req = db.get(TransportRequest, trip.transport_request_id)
    avail = db.scalar(select(DriverAvailability).where(DriverAvailability.driver_id == driver.id))
    tariff = db.get(Tariff, trip.tariff_id) if trip.tariff_id else None
    comm_rate = Decimal(tariff.commission_rate) if tariff else Decimal(str(settings.PLATFORM_COMMISSION_RATE))

    gross = Decimal(trip.paid_total_aoa if trip.paid_total_aoa > 0 else trip.total_fare_aoa).quantize(
        Decimal("0.01")
    )
    platform_fee = (gross * comm_rate).quantize(Decimal("0.01"))
    driver_net = (gross - platform_fee).quantize(Decimal("0.01"))

    trip.status = "COMPLETED"
    trip.completed_at = now_luanda()
    trip.eta_minutes = 0

    existing_comm = db.scalar(select(Commission).where(Commission.trip_id == trip.id))
    if not existing_comm:
        db.add(
            Commission(
                trip_id=trip.id,
                driver_id=driver.id,
                gross_fare_aoa=gross,
                commission_rate=comm_rate,
                platform_fee_aoa=platform_fee,
                driver_net_aoa=driver_net,
            )
        )

    driver.total_trips += 1
    if avail:
        avail.status = "AVAILABLE"
        if req:
            avail.current_lat = req.dropoff_lat
            avail.current_lng = req.dropoff_lng
            avail.current_zone = req.dropoff_zone

    passenger = db.get(Passenger, req.passenger_id) if req else None
    if passenger:
        passenger.total_trips += 1
        create_notification(
            db,
            user_id=passenger.user_id,
            title="Viagem concluída",
            message=f"Chegou a {req.dropoff_zone}. Total pago: {float(gross):,.0f} AOA. Avalie a sua viagem!",
            category="TRIP",
        )

    record_audit(
        db,
        action="TRIP_COMPLETED",
        entity_type="Trip",
        entity_id=trip.id,
        actor_user_id=user.id,
        details={
            "gross_fare_aoa": str(gross),
            "platform_fee_aoa": str(platform_fee),
            "driver_net_aoa": str(driver_net),
        },
    )
    db.commit()

    serialized = serialize_trip(db, trip)
    channels = ["role:ADMIN"]
    if passenger:
        channels.append(f"user:{passenger.user_id}")
    await realtime_hub.publish(channels, "TRIP_COMPLETED", serialized)
    return serialized
