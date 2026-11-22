from datetime import datetime
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.api.deps import require_roles
from app.api.v1.serializers import (
    serialize_card,
    serialize_request,
    serialize_transaction,
    serialize_trip,
)
from app.core.config import now_luanda
from app.db.session import get_db
from app.models.corporate import Company, Stop
from app.models.finance import CardTransaction, Commission, TransportCard, Wallet
from app.models.fleet import DriverAvailability, Vehicle
from app.models.identity import Driver, Passenger, User
from app.models.mobility import AuditLog, TransportRequest, Trip
from app.schemas.schemas import (
    BindNfcRequest,
    CardStatusRequest,
    CardTopupRequest,
    IssueCardAdminRequest,
    RefundRequest,
    VerifyDriverRequest,
)
from app.services.audit_service import create_notification, record_audit
from app.services.card_wallet_service import (
    bind_nfc_to_card,
    issue_card_for_passenger,
    refund_transaction,
    set_card_status,
    topup_card_admin,
)
from app.services.integrations import list_registered_integrations
from app.services.intelligence_service import (
    compute_mobility_intelligence,
    compute_zone_demand_pressure,
)
from app.services.matching_service import redistribute_expired_offers
from app.services.realtime_hub import realtime_hub

router = APIRouter(prefix="/admin", tags=["Painel Administrativo"])


@router.get("/overview")
def get_admin_overview(
    zone: Optional[str] = Query(default=None),
    user: User = Depends(require_roles("ADMIN")),
    db: Session = Depends(get_db),
):
    redistribute_expired_offers(db)
    db.commit()

    passengers_count = db.scalar(select(func.count(Passenger.id))) or 0
    drivers_count = db.scalar(select(func.count(Driver.id))) or 0
    approved_drivers = db.scalar(
        select(func.count(Driver.id)).where(Driver.verification_status == "APPROVED")
    ) or 0
    pending_drivers = db.scalar(
        select(func.count(Driver.id)).where(Driver.verification_status == "PENDING")
    ) or 0
    active_vehicles = db.scalar(
        select(func.count(Vehicle.id)).where(Vehicle.is_active == True)  # noqa: E712
    ) or 0
    available_vehicles = db.scalar(
        select(func.count(DriverAvailability.id)).where(DriverAvailability.status == "AVAILABLE")
    ) or 0

    req_base = select(TransportRequest)
    if zone:
        req_base = req_base.where(TransportRequest.pickup_zone == zone)
    all_reqs = db.scalars(req_base).all()

    pending_requests = [r for r in all_reqs if r.status in {"PENDING", "OFFERED"}]
    cancelled_requests = [r for r in all_reqs if r.status in {"CANCELLED", "EXPIRED"}]

    trips_all = db.scalars(select(Trip).order_by(desc(Trip.created_at))).all()
    if zone:
        trips_all = [
            t for t in trips_all if t.transport_request and t.transport_request.pickup_zone == zone
        ]

    active_trips = [t for t in trips_all if t.status in {"DRIVER_EN_ROUTE", "DRIVER_ARRIVED", "IN_PROGRESS"}]
    completed_trips = [t for t in trips_all if t.status == "COMPLETED"]

    gross_revenue = db.scalar(select(func.coalesce(func.sum(Commission.gross_fare_aoa), 0))) or 0
    platform_commissions = db.scalar(select(func.coalesce(func.sum(Commission.platform_fee_aoa), 0))) or 0
    total_wallet_balance = db.scalar(select(func.coalesce(func.sum(Wallet.balance_aoa), 0))) or 0
    active_cards = db.scalar(
        select(func.count(TransportCard.id)).where(TransportCard.status == "ACTIVE")
    ) or 0
    blocked_cards = db.scalar(
        select(func.count(TransportCard.id)).where(TransportCard.status != "ACTIVE")
    ) or 0
    companies_count = db.scalar(select(func.count(Company.id))) or 0

    # Live fleet markers for Luanda operational map
    fleet_rows = db.execute(
        select(Driver, User, DriverAvailability, Vehicle)
        .join(User, User.id == Driver.user_id)
        .join(DriverAvailability, DriverAvailability.driver_id == Driver.id)
        .outerjoin(Vehicle, Vehicle.id == DriverAvailability.active_vehicle_id)
    ).all()

    live_vehicles = []
    for drv, usr, avail, veh in fleet_rows:
        if avail.current_lat is None or avail.current_lng is None:
            continue
        if zone and (avail.current_zone or "").lower() != zone.lower():
            continue
        live_vehicles.append(
            {
                "driver_id": drv.id,
                "driver_name": usr.full_name,
                "verification_status": drv.verification_status,
                "status": avail.status,
                "latitude": avail.current_lat,
                "longitude": avail.current_lng,
                "zone": avail.current_zone,
                "vehicle_label": f"{veh.make} {veh.model} ({veh.license_plate})" if veh else "Sem veículo",
                "capacity": veh.capacity if veh else 0,
            }
        )

    stops = db.scalars(select(Stop).where(Stop.is_public_hub == True)).all()  # noqa: E712

    return {
        "kpis": {
            "passengers_registered": passengers_count,
            "drivers_registered": drivers_count,
            "drivers_approved": approved_drivers,
            "drivers_pending_verification": pending_drivers,
            "active_vehicles": active_vehicles,
            "available_vehicles": available_vehicles,
            "pending_requests": len(pending_requests),
            "active_trips": len(active_trips),
            "completed_trips": len(completed_trips),
            "cancelled_requests": len(cancelled_requests),
            "gross_revenue_aoa": float(gross_revenue),
            "platform_commissions_aoa": float(platform_commissions),
            "total_cards_balance_aoa": float(total_wallet_balance),
            "active_cards": active_cards,
            "blocked_cards": blocked_cards,
            "partner_companies": companies_count,
        },
        "map_data": {
            "vehicles": live_vehicles,
            "pending_requests": [serialize_request(db, r) for r in pending_requests],
            "active_trips": [serialize_trip(db, t) for t in active_trips],
            "stops": [
                {
                    "id": s.id,
                    "name": s.name,
                    "zone_name": s.zone_name,
                    "latitude": s.latitude,
                    "longitude": s.longitude,
                }
                for s in stops
            ],
        },
        "demand_pressure": compute_zone_demand_pressure(db),
    }


@router.get("/drivers")
def list_drivers(
    status_filter: Optional[str] = Query(default=None),
    user: User = Depends(require_roles("ADMIN")),
    db: Session = Depends(get_db),
):
    stmt = (
        select(Driver, User, DriverAvailability, Vehicle)
        .join(User, User.id == Driver.user_id)
        .outerjoin(DriverAvailability, DriverAvailability.driver_id == Driver.id)
        .outerjoin(Vehicle, Vehicle.id == DriverAvailability.active_vehicle_id)
        .order_by(desc(Driver.created_at))
    )
    if status_filter:
        stmt = stmt.where(Driver.verification_status == status_filter.upper())

    rows = db.execute(stmt).all()
    return [
        {
            "id": d.id,
            "full_name": u.full_name,
            "email": u.email,
            "phone": u.phone,
            "license_number": d.license_number,
            "national_id": d.national_id,
            "verification_status": d.verification_status,
            "verification_notes": d.verification_notes,
            "rating_avg": float(d.rating_avg),
            "total_trips": d.total_trips,
            "operational_status": a.status if a else "OFFLINE",
            "current_zone": a.current_zone if a else None,
            "vehicle": {
                "make": v.make,
                "model": v.model,
                "license_plate": v.license_plate,
                "capacity": v.capacity,
                "color": v.color,
            }
            if v
            else None,
        }
        for d, u, a, v in rows
    ]


@router.post("/drivers/{driver_id}/verify")
async def verify_driver(
    driver_id: int,
    payload: VerifyDriverRequest,
    user: User = Depends(require_roles("ADMIN")),
    db: Session = Depends(get_db),
):
    new_status = payload.verification_status.upper()
    if new_status not in {"APPROVED", "REJECTED", "SUSPENDED"}:
        raise HTTPException(status_code=400, detail="Estado de verificação inválido.")

    driver = db.get(Driver, driver_id)
    if not driver:
        raise HTTPException(status_code=404, detail="Motorista não encontrado.")

    driver.verification_status = new_status
    driver.verification_notes = payload.notes or f"Atualizado por {user.full_name}"
    if new_status == "APPROVED":
        driver.verified_at = now_luanda()
    else:
        avail = db.scalar(select(DriverAvailability).where(DriverAvailability.driver_id == driver.id))
        if avail:
            avail.status = "OFFLINE"

    create_notification(
        db,
        user_id=driver.user_id,
        title=f"Verificação documental: {new_status}",
        message=driver.verification_notes,
        category="DRIVER",
    )
    record_audit(
        db,
        action=f"DRIVER_{new_status}",
        entity_type="Driver",
        entity_id=driver.id,
        actor_user_id=user.id,
        details={"notes": driver.verification_notes},
    )
    db.commit()
    await realtime_hub.publish(
        [f"user:{driver.user_id}", "role:ADMIN"],
        "DRIVER_VERIFICATION_UPDATED",
        {"driver_id": driver.id, "verification_status": new_status},
    )
    return {"driver_id": driver.id, "verification_status": new_status}


@router.get("/cards")
def list_all_cards(
    status_filter: Optional[str] = Query(default=None),
    user: User = Depends(require_roles("ADMIN")),
    db: Session = Depends(get_db),
):
    stmt = select(TransportCard).order_by(TransportCard.card_code)
    if status_filter:
        stmt = stmt.where(TransportCard.status == status_filter.upper())
    cards = db.scalars(stmt).all()
    txs = db.scalars(
        select(CardTransaction).order_by(desc(CardTransaction.created_at)).limit(40)
    ).all()
    return {
        "cards": [serialize_card(db, c) for c in cards],
        "recent_transactions": [serialize_transaction(db, t) for t in txs],
    }


@router.post("/cards/topup")
async def admin_topup_card(
    payload: CardTopupRequest,
    user: User = Depends(require_roles("ADMIN")),
    db: Session = Depends(get_db),
):
    tx = topup_card_admin(
        db=db,
        card_code=payload.card_code,
        amount_aoa=Decimal(payload.amount_aoa),
        description=payload.description,
        actor_user_id=user.id,
        idempotency_key=payload.idempotency_key,
    )
    db.commit()
    serialized = serialize_transaction(db, tx)
    await realtime_hub.publish(["role:ADMIN"], "WALLET_TOPUP", serialized)
    return serialized


@router.put("/cards/{card_code}/status")
async def admin_update_card_status(
    card_code: str,
    payload: CardStatusRequest,
    user: User = Depends(require_roles("ADMIN")),
    db: Session = Depends(get_db),
):
    card = set_card_status(
        db=db,
        card_code=card_code,
        new_status=payload.status.upper(),
        reason=payload.reason,
        actor_user_id=user.id,
    )
    db.commit()
    serialized = serialize_card(db, card)
    await realtime_hub.publish(["role:ADMIN"], "CARD_STATUS_CHANGED", serialized)
    return serialized


@router.post("/transactions/{transaction_id}/refund")
def admin_refund_transaction(
    transaction_id: int,
    payload: RefundRequest,
    user: User = Depends(require_roles("ADMIN")),
    db: Session = Depends(get_db),
):
    tx = refund_transaction(
        db=db,
        transaction_id=transaction_id,
        reason=payload.reason,
        actor_user_id=user.id,
    )
    db.commit()
    return serialize_transaction(db, tx)


@router.put("/cards/{card_code}/nfc")
def admin_bind_nfc(
    card_code: str,
    payload: BindNfcRequest,
    user: User = Depends(require_roles("ADMIN")),
    db: Session = Depends(get_db),
):
    card = bind_nfc_to_card(
        db=db,
        card_code=card_code,
        nfc_uid=payload.nfc_uid,
        card_technology=payload.card_technology,
        actor_user_id=user.id,
    )
    db.commit()
    return serialize_card(db, card)


@router.post("/cards/issue", status_code=status.HTTP_201_CREATED)
def admin_issue_card(
    payload: IssueCardAdminRequest,
    user: User = Depends(require_roles("ADMIN")),
    db: Session = Depends(get_db),
):
    passenger = db.get(Passenger, payload.passenger_id)
    if not passenger:
        raise HTTPException(status_code=404, detail="Passageiro não encontrado.")
    card = issue_card_for_passenger(
        db=db,
        passenger=passenger,
        initial_balance_aoa=Decimal(payload.initial_balance_aoa),
        actor_user_id=user.id,
    )
    if payload.nfc_uid:
        bind_nfc_to_card(
            db=db,
            card_code=card.card_code,
            nfc_uid=payload.nfc_uid,
            card_technology="QR+NFC",
            actor_user_id=user.id,
        )
    db.commit()
    return serialize_card(db, card)


@router.get("/passengers")
def list_passengers(
    user: User = Depends(require_roles("ADMIN")),
    db: Session = Depends(get_db),
):
    rows = db.execute(
        select(Passenger, User, Wallet)
        .join(User, User.id == Passenger.user_id)
        .outerjoin(Wallet, Wallet.passenger_id == Passenger.id)
        .order_by(Passenger.id)
    ).all()
    return [
        {
            "id": p.id,
            "full_name": u.full_name,
            "email": u.email,
            "phone": u.phone,
            "default_zone": p.default_zone,
            "total_trips": p.total_trips,
            "balance_aoa": float(w.balance_aoa) if w else 0.0,
        }
        for p, u, w in rows
    ]


@router.get("/intelligence")
def get_mobility_intelligence(
    zone: Optional[str] = Query(default=None),
    date_from: Optional[str] = Query(default=None),
    date_to: Optional[str] = Query(default=None),
    user: User = Depends(require_roles("ADMIN")),
    db: Session = Depends(get_db),
):
    df = datetime.fromisoformat(date_from) if date_from else None
    dt = datetime.fromisoformat(date_to) if date_to else None
    return compute_mobility_intelligence(db, date_from=df, date_to=dt, zone=zone)


@router.get("/integrations")
def get_integrations_registry(
    user: User = Depends(require_roles("ADMIN")),
):
    return {"integrations": list_registered_integrations()}


@router.get("/trips")
def list_filtered_trips(
    status_filter: Optional[str] = Query(default=None),
    zone: Optional[str] = Query(default=None),
    driver_id: Optional[int] = Query(default=None),
    vehicle_id: Optional[int] = Query(default=None),
    company_id: Optional[int] = Query(default=None),
    date_from: Optional[str] = Query(default=None),
    date_to: Optional[str] = Query(default=None),
    user: User = Depends(require_roles("ADMIN")),
    db: Session = Depends(get_db),
):
    stmt = select(Trip).join(TransportRequest, TransportRequest.id == Trip.transport_request_id)
    if status_filter:
        stmt = stmt.where(Trip.status == status_filter.upper())
    if zone:
        stmt = stmt.where(
            (TransportRequest.pickup_zone == zone) | (TransportRequest.dropoff_zone == zone)
        )
    if driver_id:
        stmt = stmt.where(Trip.driver_id == driver_id)
    if vehicle_id:
        stmt = stmt.where(Trip.vehicle_id == vehicle_id)
    if company_id:
        stmt = stmt.where(TransportRequest.company_id == company_id)

    trips = db.scalars(stmt.order_by(desc(Trip.created_at)).limit(100)).all()
    if date_from:
        df = datetime.fromisoformat(date_from).replace(tzinfo=None)
        trips = [t for t in trips if t.created_at and t.created_at.replace(tzinfo=None) >= df]
    if date_to:
        dt = datetime.fromisoformat(date_to).replace(tzinfo=None)
        trips = [t for t in trips if t.created_at and t.created_at.replace(tzinfo=None) <= dt]

    return [serialize_trip(db, t) for t in trips]


@router.get("/audit-logs")
def list_audit_logs(
    entity_type: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    user: User = Depends(require_roles("ADMIN")),
    db: Session = Depends(get_db),
):
    stmt = select(AuditLog).order_by(desc(AuditLog.created_at)).limit(limit)
    if entity_type:
        stmt = stmt.where(AuditLog.entity_type == entity_type)
    logs = db.scalars(stmt).all()
    return [
        {
            "id": l.id,
            "actor_user_id": l.actor_user_id,
            "action": l.action,
            "entity_type": l.entity_type,
            "entity_id": l.entity_id,
            "details_json": l.details_json,
            "created_at": l.created_at.isoformat() if l.created_at else None,
        }
        for l in logs
    ]


@router.post("/matching/redistribute-expired")
def trigger_redistribution(
    user: User = Depends(require_roles("ADMIN")),
    db: Session = Depends(get_db),
):
    results = redistribute_expired_offers(db)
    db.commit()
    return {"redistributed_count": len(results), "items": results}
