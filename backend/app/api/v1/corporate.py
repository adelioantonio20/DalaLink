from collections import defaultdict
import csv
import io
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.api.deps import require_roles
from app.api.v1.serializers import serialize_request, serialize_trip
from app.core.config import now_luanda
from app.db.session import get_db
from app.models.corporate import (
    Company,
    Employee,
    RecurringCorporateBooking,
    Route,
    Stop,
    Subscription,
)
from app.models.fleet import DriverAvailability, Vehicle
from app.models.identity import Driver, Passenger, User
from app.models.mobility import TransportRequest, Trip
from app.schemas.schemas import (
    AddEmployeeRequest,
    AddRouteStopRequest,
    CorporateBatchDispatchRequest,
    CreateCorporateRouteRequest,
    CreateRecurringBookingRequest,
    EmployeeStatusUpdate,
    UpdateSubscriptionRequest,
)
from app.services.audit_service import create_notification, record_audit
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


def _build_cost_report(
    company: Company,
    employees: list[Employee],
    corp_requests: list[TransportRequest],
    corp_trips: list[Trip],
) -> dict:
    by_route: dict[str, dict] = defaultdict(lambda: {"requests": 0, "passengers": 0, "cost_aoa": 0.0})
    for r in corp_requests:
        corridor = f"{r.pickup_zone} → {r.dropoff_zone}"
        by_route[corridor]["requests"] += 1
        by_route[corridor]["passengers"] += r.passenger_count
        by_route[corridor]["cost_aoa"] += float(r.estimated_total_fare_aoa)

    dept_counts: dict[str, int] = defaultdict(int)
    for e in employees:
        if e.status == "ACTIVE":
            dept_counts[e.department] += 1

    total_active = max(1, sum(dept_counts.values()))
    total_cost = sum(float(r.estimated_total_fare_aoa) for r in corp_requests)

    by_department = [
        {
            "department": dept,
            "active_employees": cnt,
            "allocated_cost_aoa": round((cnt / total_active) * total_cost, 2),
        }
        for dept, cnt in sorted(dept_counts.items())
    ]

    completed_trips = [t for t in corp_trips if t.status == "COMPLETED"]
    return {
        "company_name": company.name,
        "total_requests": len(corp_requests),
        "total_trips": len(corp_trips),
        "completed_trips": len(completed_trips),
        "total_estimated_cost_aoa": round(total_cost, 2),
        "actual_paid_cost_aoa": round(sum(float(t.paid_total_aoa) for t in corp_trips), 2),
        "active_employees": sum(dept_counts.values()),
        "by_route": [
            {"corridor": k, **v, "cost_aoa": round(v["cost_aoa"], 2)}
            for k, v in sorted(by_route.items(), key=lambda kv: -kv[1]["cost_aoa"])
        ],
        "by_department": by_department,
    }


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
    recurring = db.scalars(
        select(RecurringCorporateBooking)
        .where(RecurringCorporateBooking.company_id == company.id)
        .order_by(desc(RecurringCorporateBooking.created_at))
    ).all()
    corp_requests = db.scalars(
        select(TransportRequest)
        .where(TransportRequest.company_id == company.id)
        .order_by(desc(TransportRequest.created_at))
        .limit(40)
    ).all()
    corp_trips = db.scalars(
        select(Trip)
        .join(TransportRequest, TransportRequest.id == Trip.transport_request_id)
        .where(TransportRequest.company_id == company.id)
        .order_by(desc(Trip.created_at))
        .limit(40)
    ).all()

    # Live vehicles currently assigned to corporate trips
    live_vehicles = []
    for t in corp_trips:
        if t.status in {"DRIVER_EN_ROUTE", "DRIVER_ARRIVED", "IN_PROGRESS"}:
            avail = db.scalar(select(DriverAvailability).where(DriverAvailability.driver_id == t.driver_id))
            veh = db.get(Vehicle, t.vehicle_id)
            drv = db.get(Driver, t.driver_id)
            d_usr = db.get(User, drv.user_id) if drv else None
            if avail and avail.current_lat and avail.current_lng:
                live_vehicles.append(
                    {
                        "trip_id": t.id,
                        "status": t.status,
                        "driver_name": d_usr.full_name if d_usr else "Motorista",
                        "vehicle_label": f"{veh.make} {veh.model} ({veh.license_plate})" if veh else "Veículo",
                        "latitude": avail.current_lat,
                        "longitude": avail.current_lng,
                        "zone": avail.current_zone,
                    }
                )

    routes_by_id = {r.id: r for r in routes}
    route_stops_map: dict[int, list[dict]] = defaultdict(list)
    all_route_stops = db.scalars(
        select(Stop).where(Stop.route_id.in_(list(routes_by_id.keys()))).order_by(Stop.sequence_order)
    ).all() if routes_by_id else []
    for st in all_route_stops:
        if st.route_id:
            route_stops_map[st.route_id].append(
                {
                    "id": st.id,
                    "name": st.name,
                    "zone_name": st.zone_name,
                    "latitude": st.latitude,
                    "longitude": st.longitude,
                    "sequence_order": st.sequence_order,
                }
            )

    cost_report = _build_cost_report(company, employees, corp_requests, corp_trips)

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
            "id": sub.id,
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
                "stops": route_stops_map.get(r.id, []),
            }
            for r in routes
        ],
        "recurring_bookings": [
            {
                "id": rb.id,
                "route_id": rb.route_id,
                "route_name": routes_by_id[rb.route_id].name if rb.route_id in routes_by_id else f"Rota #{rb.route_id}",
                "origin_zone": routes_by_id[rb.route_id].origin_zone if rb.route_id in routes_by_id else "Talatona",
                "destination_zone": routes_by_id[rb.route_id].destination_zone if rb.route_id in routes_by_id else "Aeroporto",
                "days_of_week": rb.days_of_week,
                "shift_time": rb.shift_time,
                "vehicle_capacity_hint": rb.vehicle_capacity_hint,
                "is_active": rb.is_active,
                "last_dispatched_at": rb.last_dispatched_at.isoformat() if rb.last_dispatched_at else None,
            }
            for rb in recurring
        ],
        "requests": [serialize_request(db, r) for r in corp_requests],
        "trips": [serialize_trip(db, t) for t in corp_trips],
        "live_vehicles": live_vehicles,
        "cost_summary": cost_report,
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


@router.patch("/employees/{employee_id}/status")
def update_employee_status(
    employee_id: int,
    payload: EmployeeStatusUpdate,
    user: User = Depends(require_roles("COMPANY_ADMIN", "ADMIN")),
    db: Session = Depends(get_db),
):
    company = _resolve_company(db, user)
    emp = db.get(Employee, employee_id)
    if not emp or emp.company_id != company.id:
        raise HTTPException(status_code=404, detail="Colaborador não encontrado.")
    new_status = payload.status.upper()
    if new_status not in {"INVITED", "ACTIVE", "SUSPENDED"}:
        raise HTTPException(status_code=400, detail="Estado inválido.")
    emp.status = new_status
    record_audit(
        db,
        action=f"CORPORATE_EMPLOYEE_{new_status}",
        entity_type="Employee",
        entity_id=emp.id,
        actor_user_id=user.id,
    )
    db.commit()
    return {"id": emp.id, "status": emp.status}


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


@router.post("/routes/{route_id}/stops", status_code=status.HTTP_201_CREATED)
def add_corporate_route_stop(
    route_id: int,
    payload: AddRouteStopRequest,
    user: User = Depends(require_roles("COMPANY_ADMIN", "ADMIN")),
    db: Session = Depends(get_db),
):
    company = _resolve_company(db, user)
    route = db.get(Route, route_id)
    if not route or route.company_id != company.id:
        raise HTTPException(status_code=404, detail="Rota corporativa não encontrada.")
    stop = Stop(
        route_id=route.id,
        name=payload.name.strip(),
        zone_name=payload.zone_name.strip(),
        latitude=payload.latitude,
        longitude=payload.longitude,
        sequence_order=payload.sequence_order,
        is_public_hub=False,
    )
    db.add(stop)
    db.commit()
    return {
        "id": stop.id,
        "route_id": route.id,
        "name": stop.name,
        "zone_name": stop.zone_name,
        "sequence_order": stop.sequence_order,
    }


@router.post("/recurring", status_code=status.HTTP_201_CREATED)
def create_recurring_booking(
    payload: CreateRecurringBookingRequest,
    user: User = Depends(require_roles("COMPANY_ADMIN", "ADMIN")),
    db: Session = Depends(get_db),
):
    company = _resolve_company(db, user)
    route = db.get(Route, payload.route_id)
    if not route or route.company_id != company.id:
        raise HTTPException(status_code=404, detail="Rota corporativa não encontrada.")
    rb = RecurringCorporateBooking(
        company_id=company.id,
        route_id=route.id,
        days_of_week=payload.days_of_week.strip().upper(),
        shift_time=payload.shift_time.strip(),
        vehicle_capacity_hint=payload.vehicle_capacity_hint,
        is_active=True,
    )
    db.add(rb)
    db.flush()
    record_audit(
        db,
        action="CORPORATE_RECURRING_CREATED",
        entity_type="RecurringCorporateBooking",
        entity_id=rb.id,
        actor_user_id=user.id,
        details={"route_id": route.id, "days": rb.days_of_week, "shift_time": rb.shift_time},
    )
    db.commit()
    return {
        "id": rb.id,
        "route_id": rb.route_id,
        "days_of_week": rb.days_of_week,
        "shift_time": rb.shift_time,
        "vehicle_capacity_hint": rb.vehicle_capacity_hint,
        "is_active": rb.is_active,
    }


async def _dispatch_employees_into_capacity_batches(
    db: Session,
    company: Company,
    actor_user_id: int,
    origin_zone: str,
    shift_time: str,
    destination_zone: Optional[str],
    max_vehicle_capacity: int,
) -> dict:
    employees = db.scalars(
        select(Employee).where(
            Employee.company_id == company.id,
            Employee.status == "ACTIVE",
            Employee.shift_time == shift_time,
        )
    ).all()

    if destination_zone:
        employees = [e for e in employees if e.dropoff_zone.lower() == destination_zone.lower()]

    if not employees:
        raise HTTPException(
            status_code=400,
            detail=f"Nenhum colaborador ativo encontrado para o turno das {shift_time}.",
        )

    rep_passenger = db.scalar(select(Passenger))
    if not rep_passenger:
        raise HTTPException(status_code=400, detail="Nenhum passageiro base disponível.")

    stops = {
        s.zone_name.lower(): s
        for s in db.scalars(select(Stop).where(Stop.is_public_hub == True)).all()  # noqa: E712
    }
    origin_stop = stops.get(origin_zone.lower()) or next(iter(stops.values()))

    grouped: dict[str, list[Employee]] = defaultdict(list)
    for emp in employees:
        grouped[emp.dropoff_zone].append(emp)

    created_requests = []
    cap = max(2, min(max_vehicle_capacity, 20))

    for dest_zone, emp_list in grouped.items():
        dest_stop = stops.get(dest_zone.lower()) or origin_stop
        # Split automatically into vehicle-sized chunks (e.g. 35 employees -> batches of 12, 12, 11)
        for idx in range(0, len(emp_list), cap):
            batch = emp_list[idx : idx + cap]
            count = len(batch)
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
                pickup_label=f"{company.name} ({origin_stop.zone_name}) • Turno {shift_time}",
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

            for emp in batch:
                if emp.user_id:
                    create_notification(
                        db,
                        user_id=emp.user_id,
                        title="Transporte corporativo agendado",
                        message=(
                            f"Solicitação recebida ({origin_stop.zone_name} → {dest_stop.zone_name}, "
                            f"turno {shift_time})."
                        ),
                        category="CORPORATE",
                    )

    record_audit(
        db,
        action="CORPORATE_SHIFT_DISPATCHED",
        entity_type="Company",
        entity_id=company.id,
        actor_user_id=actor_user_id,
        details={
            "shift_time": shift_time,
            "groups_created": len(created_requests),
            "employees": len(employees),
            "max_vehicle_capacity": cap,
        },
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


@router.post("/dispatch-shift")
async def dispatch_corporate_shift(
    payload: CorporateBatchDispatchRequest,
    user: User = Depends(require_roles("COMPANY_ADMIN", "ADMIN")),
    db: Session = Depends(get_db),
):
    company = _resolve_company(db, user)
    return await _dispatch_employees_into_capacity_batches(
        db=db,
        company=company,
        actor_user_id=user.id,
        origin_zone=payload.origin_zone,
        shift_time=payload.shift_time,
        destination_zone=payload.destination_zone,
        max_vehicle_capacity=payload.max_vehicle_capacity,
    )


@router.post("/recurring/{recurring_id}/trigger")
async def trigger_recurring_booking(
    recurring_id: int,
    user: User = Depends(require_roles("COMPANY_ADMIN", "ADMIN")),
    db: Session = Depends(get_db),
):
    company = _resolve_company(db, user)
    rb = db.get(RecurringCorporateBooking, recurring_id)
    if not rb or rb.company_id != company.id:
        raise HTTPException(status_code=404, detail="Agendamento recorrente não encontrado.")
    route = db.get(Route, rb.route_id)
    if not route:
        raise HTTPException(status_code=404, detail="Rota associada não encontrada.")

    result = await _dispatch_employees_into_capacity_batches(
        db=db,
        company=company,
        actor_user_id=user.id,
        origin_zone=route.origin_zone,
        shift_time=rb.shift_time,
        destination_zone=None,
        max_vehicle_capacity=rb.vehicle_capacity_hint,
    )
    rb.last_dispatched_at = now_luanda()
    db.commit()
    return result


@router.put("/subscription")
def update_corporate_subscription(
    payload: UpdateSubscriptionRequest,
    user: User = Depends(require_roles("COMPANY_ADMIN", "ADMIN")),
    db: Session = Depends(get_db),
):
    company = _resolve_company(db, user)
    sub = db.scalar(
        select(Subscription)
        .where(Subscription.company_id == company.id)
        .order_by(desc(Subscription.created_at))
    )
    if not sub:
        raise HTTPException(status_code=404, detail="Subscrição não encontrada.")
    sub.plan_name = payload.plan_name.strip()
    sub.max_employees = payload.max_employees
    sub.monthly_fee_aoa = payload.monthly_fee_aoa
    sub.status = payload.status.upper()
    record_audit(
        db,
        action="CORPORATE_SUBSCRIPTION_UPDATED",
        entity_type="Subscription",
        entity_id=sub.id,
        actor_user_id=user.id,
        details={"plan_name": sub.plan_name, "status": sub.status},
    )
    db.commit()
    return {
        "id": sub.id,
        "plan_name": sub.plan_name,
        "max_employees": sub.max_employees,
        "monthly_fee_aoa": float(sub.monthly_fee_aoa),
        "status": sub.status,
    }


@router.get("/reports/costs")
def get_corporate_cost_report(
    user: User = Depends(require_roles("COMPANY_ADMIN", "ADMIN")),
    db: Session = Depends(get_db),
):
    company = _resolve_company(db, user)
    employees = db.scalars(select(Employee).where(Employee.company_id == company.id)).all()
    corp_requests = db.scalars(
        select(TransportRequest).where(TransportRequest.company_id == company.id)
    ).all()
    corp_trips = db.scalars(
        select(Trip)
        .join(TransportRequest, TransportRequest.id == Trip.transport_request_id)
        .where(TransportRequest.company_id == company.id)
    ).all()
    return _build_cost_report(company, employees, corp_requests, corp_trips)


@router.get("/reports/costs.csv")
def export_corporate_cost_csv(
    user: User = Depends(require_roles("COMPANY_ADMIN", "ADMIN")),
    db: Session = Depends(get_db),
):
    company = _resolve_company(db, user)
    corp_requests = db.scalars(
        select(TransportRequest)
        .where(TransportRequest.company_id == company.id)
        .order_by(desc(TransportRequest.created_at))
    ).all()

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["ID", "Data", "Origem", "Destino", "Passageiros", "Estado", "Custo Estimado (AOA)"])
    for r in corp_requests:
        writer.writerow(
            [
                r.id,
                r.created_at.isoformat() if r.created_at else "",
                r.pickup_zone,
                r.dropoff_zone,
                r.passenger_count,
                r.status,
                f"{float(r.estimated_total_fare_aoa):.2f}",
            ]
        )

    return Response(
        content=buf.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="dalalink_custos_{company.nif}.csv"'},
    )
