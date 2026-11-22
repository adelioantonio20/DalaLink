from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.api.deps import require_roles
from app.api.v1.serializers import serialize_request, serialize_trip
from app.db.session import get_db
from app.models.corporate import Company, Employee, Route, Stop, Subscription
from app.models.identity import Passenger, User
from app.models.mobility import TransportRequest, Trip
from app.schemas.schemas import (
    AddEmployeeRequest,
    CorporateBatchDispatchRequest,
    CreateCorporateRouteRequest,
)
from app.services.audit_service import record_audit
from app.services.matching_service import dispatch_request_to_next_driver, estimate_trip_quote
from app.services.realtime_hub import realtime_hub

router = APIRouter(prefix="/corporate", tags=["Transporte Corporativo"])


def _resolve_company(db: Session, user: User) -> Company:
    company = db.scalar(select(Company).where(Company.contact_email == user.email))
    if not company:
        company = db.scalar(select(Company))
    if not company:
        raise HTTPException(status_code=404, detail="Empresa não encontrada.")
    return company


@router.get("/dashboard")
def get_corporate_dashboard(
    user: User = Depends(require_roles("COMPANY_ADMIN", "ADMIN")),
    db: Session = Depends(get_db),
):
    company = _resolve_company(db, user)
    sub = db.scalar(
        select(Subscription)
        .where(Subscription.company_id == company.id)
        .order_by(desc(Subscription.created_at))
    )
    employees = db.scalars(
        select(Employee).where(Employee.company_id == company.id).order_by(Employee.full_name)
    ).all()
    routes = db.scalars(
        select(Route).where(Route.company_id == company.id).order_by(desc(Route.created_at))
    ).all()
    corp_requests = db.scalars(
        select(TransportRequest)
        .where(TransportRequest.company_id == company.id)
        .order_by(desc(TransportRequest.created_at))
        .limit(25)
    ).all()
    corp_trips = db.scalars(
        select(Trip)
        .join(TransportRequest, TransportRequest.id == Trip.transport_request_id)
        .where(TransportRequest.company_id == company.id)
        .order_by(desc(Trip.created_at))
        .limit(25)
    ).all()

    total_estimated_cost = sum(float(r.estimated_total_fare_aoa) for r in corp_requests)

    return {
        "company": {
            "id": company.id,
            "name": company.name,
            "nif": company.nif,
            "contact_email": company.contact_email,
            "contact_phone": company.contact_phone,
            "headquarters_zone": company.headquarters_zone,
        },
        "subscription": {
            "plan_name": sub.plan_name,
            "monthly_fee_aoa": float(sub.monthly_fee_aoa),
            "max_employees": sub.max_employees,
            "status": sub.status,
            "start_date": sub.start_date.isoformat(),
            "end_date": sub.end_date.isoformat(),
        }
        if sub
        else None,
        "employees": [
            {
                "id": e.id,
                "full_name": e.full_name,
                "email": e.email,
                "department": e.department,
                "pickup_zone": e.pickup_zone,
                "dropoff_zone": e.dropoff_zone,
                "shift_time": e.shift_time,
                "status": e.status,
            }
            for e in employees
        ],
        "routes": [
            {
                "id": r.id,
                "name": r.name,
                "origin_zone": r.origin_zone,
                "destination_zone": r.destination_zone,
                "scheduled_time": r.scheduled_time,
                "is_active": r.is_active,
                "notes": r.notes,
            }
            for r in routes
        ],
        "requests": [serialize_request(db, r) for r in corp_requests],
        "trips": [serialize_trip(db, t) for t in corp_trips],
        "cost_summary": {
            "total_requests": len(corp_requests),
            "total_trips": len(corp_trips),
            "total_estimated_cost_aoa": total_estimated_cost,
            "active_employees": len([e for e in employees if e.status == "ACTIVE"]),
        },
    }


@router.post("/employees", status_code=status.HTTP_201_CREATED)
def add_corporate_employee(
    payload: AddEmployeeRequest,
    user: User = Depends(require_roles("COMPANY_ADMIN", "ADMIN")),
    db: Session = Depends(get_db),
):
    company = _resolve_company(db, user)
    emp = Employee(
        company_id=company.id,
        full_name=payload.full_name.strip(),
        email=payload.email.lower(),
        department=payload.department.strip(),
        pickup_zone=payload.pickup_zone.strip(),
        dropoff_zone=payload.dropoff_zone.strip(),
        shift_time=payload.shift_time.strip(),
        status="ACTIVE",
    )
    db.add(emp)
    db.flush()
    record_audit(
        db,
        action="CORPORATE_EMPLOYEE_ADDED",
        entity_type="Employee",
        entity_id=emp.id,
        actor_user_id=user.id,
        details={"company_id": company.id, "email": emp.email},
    )
    db.commit()
    return {
        "id": emp.id,
        "full_name": emp.full_name,
        "email": emp.email,
        "department": emp.department,
        "pickup_zone": emp.pickup_zone,
        "dropoff_zone": emp.dropoff_zone,
        "shift_time": emp.shift_time,
        "status": emp.status,
    }


@router.post("/routes", status_code=status.HTTP_201_CREATED)
def create_corporate_route(
    payload: CreateCorporateRouteRequest,
    user: User = Depends(require_roles("COMPANY_ADMIN", "ADMIN")),
    db: Session = Depends(get_db),
):
    company = _resolve_company(db, user)
    route = Route(
        company_id=company.id,
        name=payload.name.strip(),
        origin_zone=payload.origin_zone.strip(),
        destination_zone=payload.destination_zone.strip(),
        scheduled_time=payload.scheduled_time.strip(),
        is_corporate=True,
        notes=payload.notes,
    )
    db.add(route)
    db.flush()
    record_audit(
        db,
        action="CORPORATE_ROUTE_CREATED",
        entity_type="Route",
        entity_id=route.id,
        actor_user_id=user.id,
        details={"company_id": company.id, "name": route.name},
    )
    db.commit()
    return {
        "id": route.id,
        "name": route.name,
        "origin_zone": route.origin_zone,
        "destination_zone": route.destination_zone,
        "scheduled_time": route.scheduled_time,
        "notes": route.notes,
    }


@router.post("/dispatch-shift")
async def dispatch_corporate_shift(
    payload: CorporateBatchDispatchRequest,
    user: User = Depends(require_roles("COMPANY_ADMIN", "ADMIN")),
    db: Session = Depends(get_db),
):
    """
    Group active employees by destination zone for a given shift (e.g. 17:00)
    and create optimized corporate transport requests into the matching engine.
    """
    company = _resolve_company(db, user)
    employees = db.scalars(
        select(Employee).where(
            Employee.company_id == company.id,
            Employee.status == "ACTIVE",
            Employee.shift_time == payload.shift_time,
        )
    ).all()

    if payload.destination_zone:
        employees = [
            e for e in employees if e.dropoff_zone.lower() == payload.destination_zone.lower()
        ]

    if not employees:
        raise HTTPException(
            status_code=400,
            detail=f"Nenhum colaborador ativo encontrado para o turno das {payload.shift_time}.",
        )

    # Resolve representative passenger profile for corporate request ownership
    rep_passenger = db.scalar(select(Passenger))
    if not rep_passenger:
        raise HTTPException(status_code=400, detail="Nenhum passageiro base disponível.")

    stops = {s.zone_name.lower(): s for s in db.scalars(select(Stop).where(Stop.is_public_hub == True)).all()}  # noqa: E712
    origin_stop = stops.get(payload.origin_zone.lower()) or next(iter(stops.values()))

    grouped: dict[str, list[Employee]] = defaultdict(list)
    for emp in employees:
        grouped[emp.dropoff_zone].append(emp)

    created_requests = []
    for dest_zone, emp_list in grouped.items():
        dest_stop = stops.get(dest_zone.lower()) or origin_stop
        count = len(emp_list)
        quote = estimate_trip_quote(
            db,
            pickup_lat=origin_stop.latitude,
            pickup_lng=origin_stop.longitude,
            dropoff_lat=dest_stop.latitude,
            dropoff_lng=dest_stop.longitude,
            passenger_count=count,
        )
        req = TransportRequest(
            passenger_id=rep_passenger.id,
            company_id=company.id,
            request_type="CORPORATE",
            pickup_label=f"{company.name} ({origin_stop.zone_name})",
            pickup_zone=origin_stop.zone_name,
            pickup_lat=origin_stop.latitude,
            pickup_lng=origin_stop.longitude,
            dropoff_label=dest_stop.name,
            dropoff_zone=dest_stop.zone_name,
            dropoff_lat=dest_stop.latitude,
            dropoff_lng=dest_stop.longitude,
            passenger_count=count,
            estimated_distance_km=quote["distance_km"],
            estimated_duration_min=quote["duration_min"],
            fare_per_passenger_aoa=quote["fare_per_passenger_aoa"],
            estimated_total_fare_aoa=quote["total_fare_aoa"],
            status="PENDING",
        )
        db.add(req)
        db.flush()
        chosen = dispatch_request_to_next_driver(db, req)
        created_requests.append((req, chosen))

    record_audit(
        db,
        action="CORPORATE_SHIFT_DISPATCHED",
        entity_type="Company",
        entity_id=company.id,
        actor_user_id=user.id,
        details={"shift_time": payload.shift_time, "groups_created": len(created_requests)},
    )
    db.commit()

    serialized_list = []
    for req, chosen in created_requests:
        s = serialize_request(db, req)
        serialized_list.append(s)
        channels = ["role:ADMIN"]
        if chosen:
            channels.append(f"user:{chosen['driver'].user_id}")
        await realtime_hub.publish(channels, "NEW_OFFER", s)

    return {
        "dispatched_groups": len(serialized_list),
        "total_employees_scheduled": len(employees),
        "requests": serialized_list,
    }
