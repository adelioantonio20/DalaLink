from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.api.deps import require_roles
from app.db.session import get_db
from app.models.finance import Commission
from app.models.fleet import DriverAvailability, Vehicle
from app.models.identity import Driver, User, VehicleOwner
from app.models.mobility import Trip
from app.schemas.schemas import AssignVehicleDriverRequest, RegisterVehicleRequest
from app.services.audit_service import record_audit

router = APIRouter(prefix="/owner", tags=["Proprietário & Gestão de Frotas"])


def _resolve_owner(db: Session, user: User) -> VehicleOwner:
    owner = db.scalar(select(VehicleOwner).where(VehicleOwner.user_id == user.id))
    if not owner:
        owner = db.scalar(select(VehicleOwner))
    if not owner:
        raise HTTPException(status_code=404, detail="Perfil de proprietário de frota não encontrado.")
    return owner


@router.get("/dashboard")
def get_owner_fleet_dashboard(
    user: User = Depends(require_roles("OWNER", "ADMIN")),
    db: Session = Depends(get_db),
):
    owner = _resolve_owner(db, user)
    vehicles = db.scalars(
        select(Vehicle).where(Vehicle.owner_id == owner.id).order_by(Vehicle.id)
    ).all()

    fleet_items = []
    total_gross = 0.0
    total_platform_fee = 0.0
    total_net = 0.0
    total_completed_trips = 0
    available_count = 0
    busy_count = 0

    for v in vehicles:
        driver = db.get(Driver, v.driver_id) if v.driver_id else None
        d_user = db.get(User, driver.user_id) if driver else None
        avail = (
            db.scalar(select(DriverAvailability).where(DriverAvailability.driver_id == driver.id))
            if driver
            else None
        )
        if avail:
            if avail.status == "AVAILABLE":
                available_count += 1
            elif avail.status == "BUSY":
                busy_count += 1

        trip_ids = db.scalars(
            select(Trip.id).where(Trip.vehicle_id == v.id, Trip.status == "COMPLETED")
        ).all()
        gross = 0.0
        fee = 0.0
        net = 0.0
        if trip_ids:
            gross = float(
                db.scalar(
                    select(func.coalesce(func.sum(Commission.gross_fare_aoa), 0)).where(
                        Commission.trip_id.in_(trip_ids)
                    )
                )
                or 0
            )
            fee = float(
                db.scalar(
                    select(func.coalesce(func.sum(Commission.platform_fee_aoa), 0)).where(
                        Commission.trip_id.in_(trip_ids)
                    )
                )
                or 0
            )
            net = float(
                db.scalar(
                    select(func.coalesce(func.sum(Commission.driver_net_aoa), 0)).where(
                        Commission.trip_id.in_(trip_ids)
                    )
                )
                or 0
            )

        total_gross += gross
        total_platform_fee += fee
        total_net += net
        total_completed_trips += len(trip_ids)

        fleet_items.append(
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
                "driver": {
                    "id": driver.id,
                    "full_name": d_user.full_name if d_user else "Motorista",
                    "phone": d_user.phone if d_user else None,
                    "verification_status": driver.verification_status,
                    "rating_avg": float(driver.rating_avg),
                }
                if driver
                else None,
                "operational_status": avail.status if avail else "OFFLINE",
                "latitude": avail.current_lat if avail else -8.87,
                "longitude": avail.current_lng if avail else 13.22,
                "current_zone": avail.current_zone if avail else "Luanda",
                "performance": {
                    "completed_trips": len(trip_ids),
                    "gross_revenue_aoa": round(gross, 2),
                    "platform_fee_aoa": round(fee, 2),
                    "net_revenue_aoa": round(net, 2),
                },
            }
        )

    all_drivers = db.execute(
        select(Driver, User).join(User, User.id == Driver.user_id).order_by(desc(Driver.created_at))
    ).all()

    return {
        "owner": {
            "id": owner.id,
            "company_name": owner.company_name,
            "tax_id": owner.tax_id,
            "payout_iban": owner.payout_iban,
        },
        "summary": {
            "total_vehicles": len(vehicles),
            "active_vehicles": sum(1 for v in vehicles if v.is_active),
            "available_vehicles": available_count,
            "busy_vehicles": busy_count,
            "total_completed_trips": total_completed_trips,
            "gross_revenue_aoa": round(total_gross, 2),
            "platform_fee_aoa": round(total_platform_fee, 2),
            "net_revenue_aoa": round(total_net, 2),
        },
        "vehicles": fleet_items,
        "available_drivers": [
            {
                "id": d.id,
                "full_name": u.full_name,
                "verification_status": d.verification_status,
                "rating_avg": float(d.rating_avg),
            }
            for d, u in all_drivers
        ],
    }


@router.post("/vehicles", status_code=status.HTTP_201_CREATED)
def owner_register_vehicle(
    payload: RegisterVehicleRequest,
    user: User = Depends(require_roles("OWNER", "ADMIN")),
    db: Session = Depends(get_db),
):
    owner = _resolve_owner(db, user)
    plate = payload.license_plate.strip().upper()
    if db.scalar(select(Vehicle).where(Vehicle.license_plate == plate)):
        raise HTTPException(status_code=409, detail="Matrícula já registada na plataforma.")

    veh = Vehicle(
        owner_id=owner.id,
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
    record_audit(
        db,
        action="OWNER_VEHICLE_REGISTERED",
        entity_type="Vehicle",
        entity_id=veh.id,
        actor_user_id=user.id,
        details={"owner_id": owner.id, "plate": plate},
    )
    db.commit()
    return {
        "id": veh.id,
        "make": veh.make,
        "model": veh.model,
        "license_plate": veh.license_plate,
        "capacity": veh.capacity,
    }


@router.put("/vehicles/{vehicle_id}/assign-driver")
def owner_assign_driver(
    vehicle_id: int,
    payload: AssignVehicleDriverRequest,
    user: User = Depends(require_roles("OWNER", "ADMIN")),
    db: Session = Depends(get_db),
):
    owner = _resolve_owner(db, user)
    veh = db.get(Vehicle, vehicle_id)
    if not veh or veh.owner_id != owner.id:
        raise HTTPException(status_code=404, detail="Veículo não encontrado na sua frota.")

    if payload.driver_id is not None:
        drv = db.get(Driver, payload.driver_id)
        if not drv:
            raise HTTPException(status_code=404, detail="Motorista não encontrado.")
        veh.driver_id = drv.id
        avail = db.scalar(select(DriverAvailability).where(DriverAvailability.driver_id == drv.id))
        if avail:
            avail.active_vehicle_id = veh.id
    if payload.is_active is not None:
        veh.is_active = payload.is_active

    record_audit(
        db,
        action="OWNER_VEHICLE_UPDATED",
        entity_type="Vehicle",
        entity_id=veh.id,
        actor_user_id=user.id,
        details={"driver_id": veh.driver_id, "is_active": veh.is_active},
    )
    db.commit()
    return {"id": veh.id, "driver_id": veh.driver_id, "is_active": veh.is_active}
