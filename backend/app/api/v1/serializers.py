from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.corporate import Company
from app.models.finance import CardTransaction, Commission, TransportCard, Wallet
from app.models.fleet import DriverAvailability, Vehicle
from app.models.identity import Driver, Passenger, User
from app.models.mobility import GroupPassenger, GroupRequest, Rating, TransportRequest, Trip, TripPassenger


def serialize_user(db: Session, user: User) -> dict:
    data: dict = {
        "id": user.id,
        "full_name": user.full_name,
        "email": user.email,
        "phone": user.phone,
        "role": user.role,
        "is_active": user.is_active,
        "created_at": user.created_at.isoformat() if user.created_at else None,
    }
    if user.role == "PASSENGER" and user.passenger:
        wallet = db.scalar(select(Wallet).where(Wallet.passenger_id == user.passenger.id))
        cards = (
            db.scalars(select(TransportCard).where(TransportCard.wallet_id == wallet.id)).all()
            if wallet
            else []
        )
        data["passenger_id"] = user.passenger.id
        data["default_zone"] = user.passenger.default_zone
        data["wallet_balance_aoa"] = float(wallet.balance_aoa) if wallet else 0.0
        data["primary_card_code"] = cards[0].card_code if cards else None
    elif user.role == "DRIVER" and user.driver:
        data["driver_id"] = user.driver.id
        data["verification_status"] = user.driver.verification_status
        data["rating_avg"] = float(user.driver.rating_avg)
    elif user.role == "COMPANY_ADMIN":
        company = db.scalar(select(Company).where(Company.contact_email == user.email))
        if not company:
            company = db.scalar(select(Company))
        if company:
            data["company_id"] = company.id
            data["company_name"] = company.name
    return data


def serialize_card(db: Session, card: TransportCard) -> dict:
    wallet = db.get(Wallet, card.wallet_id)
    passenger = db.get(Passenger, wallet.passenger_id) if wallet else None
    user = db.get(User, passenger.user_id) if passenger else None
    return {
        "id": card.id,
        "card_code": card.card_code,
        "qr_token": card.qr_token,
        "card_technology": card.card_technology,
        "nfc_uid": card.nfc_uid,
        "status": card.status,
        "block_reason": card.block_reason,
        "balance_aoa": float(wallet.balance_aoa) if wallet else 0.0,
        "currency": wallet.currency if wallet else "AOA",
        "passenger_id": passenger.id if passenger else None,
        "passenger_name": user.full_name if user else "Desconhecido",
        "passenger_email": user.email if user else None,
        "issued_at": card.issued_at.isoformat() if card.issued_at else None,
    }


def serialize_transaction(db: Session, tx: CardTransaction) -> dict:
    card = db.get(TransportCard, tx.card_id)
    return {
        "id": tx.id,
        "card_code": card.card_code if card else None,
        "trip_id": tx.trip_id,
        "tx_type": tx.tx_type,
        "amount_aoa": float(tx.amount_aoa),
        "balance_before_aoa": float(tx.balance_before_aoa),
        "balance_after_aoa": float(tx.balance_after_aoa),
        "status": tx.status,
        "description": tx.description,
        "idempotency_key": tx.idempotency_key,
        "created_at": tx.created_at.isoformat() if tx.created_at else None,
    }


def serialize_request(db: Session, req: TransportRequest) -> dict:
    passenger = db.get(Passenger, req.passenger_id)
    p_user = db.get(User, passenger.user_id) if passenger else None
    group_members: list[dict] = []
    group_req = db.scalar(select(GroupRequest).where(GroupRequest.transport_request_id == req.id))
    if group_req:
        members = db.scalars(
            select(GroupPassenger).where(GroupPassenger.group_request_id == group_req.id)
        ).all()
        for m in members:
            c = db.get(TransportCard, m.transport_card_id)
            mp = db.get(Passenger, m.passenger_id)
            mu = db.get(User, mp.user_id) if mp else None
            group_members.append(
                {
                    "id": m.id,
                    "passenger_name": mu.full_name if mu else "Passageiro",
                    "card_code": c.card_code if c else None,
                    "individual_fare_aoa": float(m.individual_fare_aoa),
                    "validation_status": m.validation_status,
                }
            )

    return {
        "id": req.id,
        "passenger_id": req.passenger_id,
        "passenger_name": p_user.full_name if p_user else "Passageiro",
        "passenger_phone": p_user.phone if p_user else None,
        "company_id": req.company_id,
        "request_type": req.request_type,
        "pickup_label": req.pickup_label,
        "pickup_zone": req.pickup_zone,
        "pickup_lat": req.pickup_lat,
        "pickup_lng": req.pickup_lng,
        "dropoff_label": req.dropoff_label,
        "dropoff_zone": req.dropoff_zone,
        "dropoff_lat": req.dropoff_lat,
        "dropoff_lng": req.dropoff_lng,
        "passenger_count": req.passenger_count,
        "estimated_distance_km": req.estimated_distance_km,
        "estimated_duration_min": req.estimated_duration_min,
        "fare_per_passenger_aoa": float(req.fare_per_passenger_aoa),
        "estimated_total_fare_aoa": float(req.estimated_total_fare_aoa),
        "status": req.status,
        "offered_driver_id": req.offered_driver_id,
        "offer_expires_at": req.offer_expires_at.isoformat() if req.offer_expires_at else None,
        "group_members": group_members,
        "created_at": req.created_at.isoformat() if req.created_at else None,
    }


def serialize_trip(db: Session, trip: Trip) -> dict:
    req = db.get(TransportRequest, trip.transport_request_id)
    driver = db.get(Driver, trip.driver_id)
    d_user = db.get(User, driver.user_id) if driver else None
    vehicle = db.get(Vehicle, trip.vehicle_id)
    avail = (
        db.scalar(select(DriverAvailability).where(DriverAvailability.driver_id == driver.id))
        if driver
        else None
    )
    commission: Optional[Commission] = db.scalar(
        select(Commission).where(Commission.trip_id == trip.id)
    )
    rating: Optional[Rating] = db.scalar(select(Rating).where(Rating.trip_id == trip.id))

    boarded_rows = db.scalars(select(TripPassenger).where(TripPassenger.trip_id == trip.id)).all()
    boarded_passengers: list[dict] = []
    for tp in boarded_rows:
        card = db.get(TransportCard, tp.transport_card_id)
        p = db.get(Passenger, tp.passenger_id)
        pu = db.get(User, p.user_id) if p else None
        boarded_passengers.append(
            {
                "id": tp.id,
                "passenger_name": pu.full_name if pu else "Passageiro",
                "card_code": card.card_code if card else None,
                "fare_charged_aoa": float(tp.fare_charged_aoa),
                "boarding_status": tp.boarding_status,
                "boarded_at": tp.boarded_at.isoformat() if tp.boarded_at else None,
                "card_transaction_id": tp.card_transaction_id,
            }
        )

    return {
        "id": trip.id,
        "transport_request_id": trip.transport_request_id,
        "status": trip.status,
        "boarding_code": trip.boarding_code,
        "eta_minutes": trip.eta_minutes,
        "fare_per_passenger_aoa": float(trip.fare_per_passenger_aoa),
        "total_fare_aoa": float(trip.total_fare_aoa),
        "paid_total_aoa": float(trip.paid_total_aoa),
        "request": serialize_request(db, req) if req else None,
        "driver": {
            "id": driver.id,
            "full_name": d_user.full_name if d_user else "Motorista",
            "phone": d_user.phone if d_user else None,
            "rating_avg": float(driver.rating_avg),
            "total_trips": driver.total_trips,
            "current_lat": avail.current_lat if avail else None,
            "current_lng": avail.current_lng if avail else None,
            "current_zone": avail.current_zone if avail else None,
        }
        if driver
        else None,
        "vehicle": {
            "id": vehicle.id,
            "make": vehicle.make,
            "model": vehicle.model,
            "year": vehicle.year,
            "color": vehicle.color,
            "license_plate": vehicle.license_plate,
            "vehicle_type": vehicle.vehicle_type,
            "capacity": vehicle.capacity,
        }
        if vehicle
        else None,
        "boarded_passengers": boarded_passengers,
        "boarded_count": len([b for b in boarded_passengers if b["boarding_status"] == "BOARDED"]),
        "commission": {
            "gross_fare_aoa": float(commission.gross_fare_aoa),
            "platform_fee_aoa": float(commission.platform_fee_aoa),
            "driver_net_aoa": float(commission.driver_net_aoa),
            "commission_rate": float(commission.commission_rate),
        }
        if commission
        else None,
        "rating": {
            "score": rating.score,
            "comment": rating.comment,
        }
        if rating
        else None,
        "accepted_at": trip.accepted_at.isoformat() if trip.accepted_at else None,
        "arrived_at": trip.arrived_at.isoformat() if trip.arrived_at else None,
        "started_at": trip.started_at.isoformat() if trip.started_at else None,
        "completed_at": trip.completed_at.isoformat() if trip.completed_at else None,
    }
