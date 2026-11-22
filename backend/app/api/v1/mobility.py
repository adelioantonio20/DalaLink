from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_roles
from app.api.v1.serializers import (
    serialize_card,
    serialize_request,
    serialize_transaction,
    serialize_trip,
)
from app.db.session import get_db
from app.models.corporate import Stop
from app.models.finance import CardTransaction, TransportCard, Wallet
from app.models.identity import Driver, Passenger, User
from app.models.mobility import (
    GroupPassenger,
    GroupRequest,
    Notification,
    Rating,
    TransportRequest,
    Trip,
)
from app.schemas.schemas import CreateTransportRequest, QuoteRequest, RateTripRequest
from app.services.audit_service import create_notification, record_audit
from app.services.card_wallet_service import _resolve_card_by_input
from app.services.matching_service import (
    dispatch_request_to_next_driver,
    estimate_trip_quote,
    redistribute_expired_offers,
)
from app.services.realtime_hub import realtime_hub

router = APIRouter(prefix="/mobility", tags=["Passageiro & Mobilidade"])


@router.get("/stops")
def list_luanda_stops(db: Session = Depends(get_db)):
    stops = db.scalars(
        select(Stop).where(Stop.is_public_hub == True).order_by(Stop.sequence_order)  # noqa: E712
    ).all()
    return [
        {
            "id": s.id,
            "name": s.name,
            "zone_name": s.zone_name,
            "latitude": s.latitude,
            "longitude": s.longitude,
        }
        for s in stops
    ]


@router.post("/quote")
def get_quote(payload: QuoteRequest, db: Session = Depends(get_db)):
    quote = estimate_trip_quote(
        db,
        pickup_lat=payload.pickup_lat,
        pickup_lng=payload.pickup_lng,
        dropoff_lat=payload.dropoff_lat,
        dropoff_lng=payload.dropoff_lng,
        passenger_count=payload.passenger_count,
    )
    return {
        "tariff_name": quote["tariff_name"],
        "distance_km": quote["distance_km"],
        "duration_min": quote["duration_min"],
        "passenger_count": payload.passenger_count,
        "fare_per_passenger_aoa": float(quote["fare_per_passenger_aoa"]),
        "total_fare_aoa": float(quote["total_fare_aoa"]),
        "currency": "AOA",
    }


@router.post("/cards/verify-companion")
def verify_companion_card(
    payload: dict,
    user: User = Depends(require_roles("PASSENGER", "ADMIN")),
    db: Session = Depends(get_db),
):
    """
    Validate a companion's QR card for group transport without exposing private wallet balances.
    """
    identifier = str(payload.get("card_identifier", "")).strip()
    if not identifier:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Indique o código ou QR do cartão.")

    card = _resolve_card_by_input(db, identifier)
    if not card:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cartão não encontrado.")

    wallet = db.get(Wallet, card.wallet_id)
    passenger = db.get(Passenger, wallet.passenger_id) if wallet else None
    p_user = db.get(User, passenger.user_id) if passenger else None

    if card.status != "ACTIVE":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cartão {card.card_code} está {card.status} e não pode ser adicionado ao grupo.",
        )

    return {
        "valid": True,
        "card_code": card.card_code,
        "passenger_name": p_user.full_name if p_user else "Passageiro",
        "status": card.status,
    }


@router.post("/requests", status_code=status.HTTP_201_CREATED)
async def create_transport_request(
    payload: CreateTransportRequest,
    user: User = Depends(require_roles("PASSENGER")),
    db: Session = Depends(get_db),
):
    if not user.passenger:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Perfil de passageiro não encontrado.")

    # Redistribute any stale offers first so driver availability is accurate
    redistribute_expired_offers(db)

    # Prevent duplicate active requests by the same passenger
    existing_active = db.scalar(
        select(TransportRequest).where(
            TransportRequest.passenger_id == user.passenger.id,
            TransportRequest.status.in_(["PENDING", "OFFERED"]),
        )
    )
    if existing_active:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Já possui uma solicitação de transporte ativa. Cancele-a antes de criar outra.",
        )

    active_trip = db.scalar(
        select(Trip)
        .join(TransportRequest, TransportRequest.id == Trip.transport_request_id)
        .where(
            TransportRequest.passenger_id == user.passenger.id,
            Trip.status.in_(["DRIVER_EN_ROUTE", "DRIVER_ARRIVED", "IN_PROGRESS"]),
        )
    )
    if active_trip:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Já se encontra numa viagem em curso.",
        )

    # Resolve cards for group request if applicable
    resolved_group_cards: list[tuple[TransportCard, Passenger]] = []
    is_group = payload.request_type.upper() == "GROUP" or payload.passenger_count > 1 or len(payload.companion_card_codes) > 0

    if is_group:
        seen_card_ids: set[int] = set()
        if payload.include_requester_card:
            req_wallet = db.scalar(select(Wallet).where(Wallet.passenger_id == user.passenger.id))
            req_card = (
                db.scalar(
                    select(TransportCard).where(
                        TransportCard.wallet_id == req_wallet.id,
                        TransportCard.status == "ACTIVE",
                    )
                )
                if req_wallet
                else None
            )
            if req_card:
                resolved_group_cards.append((req_card, user.passenger))
                seen_card_ids.add(req_card.id)

        for code in payload.companion_card_codes:
            c = _resolve_card_by_input(db, code)
            if not c:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Cartão de acompanhante inválido: {code}",
                )
            if c.status != "ACTIVE":
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Cartão {c.card_code} está {c.status} e não pode participar no grupo.",
                )
            if c.id not in seen_card_ids:
                w = db.get(Wallet, c.wallet_id)
                p = db.get(Passenger, w.passenger_id) if w else None
                if p:
                    resolved_group_cards.append((c, p))
                    seen_card_ids.add(c.id)

    effective_count = max(payload.passenger_count, len(resolved_group_cards), 1)
    quote = estimate_trip_quote(
        db,
        pickup_lat=payload.pickup_lat,
        pickup_lng=payload.pickup_lng,
        dropoff_lat=payload.dropoff_lat,
        dropoff_lng=payload.dropoff_lng,
        passenger_count=effective_count,
    )

    req = TransportRequest(
        passenger_id=user.passenger.id,
        request_type="GROUP" if is_group else "INDIVIDUAL",
        pickup_label=payload.pickup_label,
        pickup_zone=payload.pickup_zone,
        pickup_lat=payload.pickup_lat,
        pickup_lng=payload.pickup_lng,
        dropoff_label=payload.dropoff_label,
        dropoff_zone=payload.dropoff_zone,
        dropoff_lat=payload.dropoff_lat,
        dropoff_lng=payload.dropoff_lng,
        passenger_count=effective_count,
        estimated_distance_km=quote["distance_km"],
        estimated_duration_min=quote["duration_min"],
        fare_per_passenger_aoa=quote["fare_per_passenger_aoa"],
        estimated_total_fare_aoa=quote["total_fare_aoa"],
        status="PENDING",
    )
    db.add(req)
    db.flush()

    if is_group:
        grp = GroupRequest(
            transport_request_id=req.id,
            requester_passenger_id=user.passenger.id,
            total_passengers=effective_count,
            fare_per_passenger_aoa=quote["fare_per_passenger_aoa"],
            total_fare_aoa=quote["total_fare_aoa"],
        )
        db.add(grp)
        db.flush()
        for card, member_passenger in resolved_group_cards:
            db.add(
                GroupPassenger(
                    group_request_id=grp.id,
                    passenger_id=member_passenger.id,
                    transport_card_id=card.id,
                    individual_fare_aoa=quote["fare_per_passenger_aoa"],
                    validation_status="PENDING",
                )
            )

    chosen = dispatch_request_to_next_driver(db, req)

    create_notification(
        db,
        user_id=user.id,
        title="Solicitação enviada",
        message=f"A procurar motorista disponível de {req.pickup_zone} para {req.dropoff_zone}.",
        category="TRIP",
    )
    record_audit(
        db,
        action="TRANSPORT_REQUEST_CREATED",
        entity_type="TransportRequest",
        entity_id=req.id,
        actor_user_id=user.id,
        details={
            "type": req.request_type,
            "pickup_zone": req.pickup_zone,
            "dropoff_zone": req.dropoff_zone,
            "passenger_count": req.passenger_count,
            "total_fare_aoa": str(req.estimated_total_fare_aoa),
        },
    )
    db.commit()
    db.refresh(req)

    serialized = serialize_request(db, req)

    channels = ["role:ADMIN"]
    if chosen:
        channels.append(f"user:{chosen['driver'].user_id}")
    await realtime_hub.publish(channels, "NEW_OFFER", serialized)

    return {
        "request": serialized,
        "matched_driver_found": chosen is not None,
        "estimated_driver_eta_min": chosen["eta_min"] if chosen else None,
    }


@router.get("/requests/active")
def get_active_passenger_state(
    user: User = Depends(require_roles("PASSENGER")),
    db: Session = Depends(get_db),
):
    if not user.passenger:
        raise HTTPException(status_code=400, detail="Perfil de passageiro não encontrado.")

    redistribute_expired_offers(db)
    db.commit()

    active_trip = db.scalar(
        select(Trip)
        .join(TransportRequest, TransportRequest.id == Trip.transport_request_id)
        .where(
            TransportRequest.passenger_id == user.passenger.id,
            Trip.status.in_(["DRIVER_EN_ROUTE", "DRIVER_ARRIVED", "IN_PROGRESS"]),
        )
        .order_by(desc(Trip.created_at))
    )
    if active_trip:
        return {"active_request": None, "active_trip": serialize_trip(db, active_trip)}

    active_req = db.scalar(
        select(TransportRequest)
        .where(
            TransportRequest.passenger_id == user.passenger.id,
            TransportRequest.status.in_(["PENDING", "OFFERED"]),
        )
        .order_by(desc(TransportRequest.created_at))
    )
    return {
        "active_request": serialize_request(db, active_req) if active_req else None,
        "active_trip": None,
    }


@router.post("/requests/{request_id}/cancel")
async def cancel_request(
    request_id: int,
    user: User = Depends(require_roles("PASSENGER", "ADMIN")),
    db: Session = Depends(get_db),
):
    req = db.get(TransportRequest, request_id)
    if not req:
        raise HTTPException(status_code=404, detail="Solicitação não encontrada.")
    if user.role == "PASSENGER" and (not user.passenger or req.passenger_id != user.passenger.id):
        raise HTTPException(status_code=403, detail="Não autorizado a cancelar esta solicitação.")
    if req.status not in {"PENDING", "OFFERED"}:
        raise HTTPException(status_code=400, detail="Esta solicitação já não pode ser cancelada.")

    prev_driver_id = req.offered_driver_id
    req.status = "CANCELLED"
    req.offered_driver_id = None
    record_audit(
        db,
        action="TRANSPORT_REQUEST_CANCELLED",
        entity_type="TransportRequest",
        entity_id=req.id,
        actor_user_id=user.id,
    )
    db.commit()

    channels = ["role:ADMIN"]
    if prev_driver_id:
        drv = db.get(Driver, prev_driver_id)
        if drv:
            channels.append(f"user:{drv.user_id}")
    await realtime_hub.publish(channels, "REQUEST_CANCELLED", {"request_id": req.id})
    return {"cancelled": True, "request_id": req.id}


@router.get("/trips/history")
def get_passenger_trip_history(
    user: User = Depends(require_roles("PASSENGER")),
    db: Session = Depends(get_db),
):
    trips = db.scalars(
        select(Trip)
        .join(TransportRequest, TransportRequest.id == Trip.transport_request_id)
        .where(TransportRequest.passenger_id == user.passenger.id)
        .order_by(desc(Trip.created_at))
        .limit(30)
    ).all()
    return [serialize_trip(db, t) for t in trips]


@router.post("/trips/{trip_id}/rate")
def rate_trip(
    trip_id: int,
    payload: RateTripRequest,
    user: User = Depends(require_roles("PASSENGER")),
    db: Session = Depends(get_db),
):
    trip = db.get(Trip, trip_id)
    if not trip:
        raise HTTPException(status_code=404, detail="Viagem não encontrada.")
    req = db.get(TransportRequest, trip.transport_request_id)
    if not req or not user.passenger or req.passenger_id != user.passenger.id:
        raise HTTPException(status_code=403, detail="Apenas o passageiro da viagem pode avaliá-la.")
    if trip.status != "COMPLETED":
        raise HTTPException(status_code=400, detail="Só é possível avaliar viagens concluídas.")

    existing = db.scalar(
        select(Rating).where(Rating.trip_id == trip.id, Rating.rater_user_id == user.id)
    )
    if existing:
        raise HTTPException(status_code=409, detail="Esta viagem já foi avaliada.")

    driver = db.get(Driver, trip.driver_id)
    rating = Rating(
        trip_id=trip.id,
        rater_user_id=user.id,
        rated_user_id=driver.user_id,
        score=payload.score,
        comment=payload.comment,
    )
    db.add(rating)
    db.flush()

    avg_score = db.scalar(
        select(func.avg(Rating.score)).where(Rating.rated_user_id == driver.user_id)
    )
    if avg_score is not None:
        driver.rating_avg = Decimal(str(round(float(avg_score), 2)))

    db.commit()
    return {"rated": True, "score": payload.score, "driver_rating_avg": float(driver.rating_avg)}


@router.get("/wallet")
def get_my_wallet(
    user: User = Depends(require_roles("PASSENGER")),
    db: Session = Depends(get_db),
):
    if not user.passenger:
        raise HTTPException(status_code=400, detail="Perfil de passageiro não encontrado.")

    wallet = db.scalar(select(Wallet).where(Wallet.passenger_id == user.passenger.id))
    if not wallet:
        raise HTTPException(status_code=404, detail="Carteira não encontrada.")

    cards = db.scalars(select(TransportCard).where(TransportCard.wallet_id == wallet.id)).all()
    txs = db.scalars(
        select(CardTransaction)
        .where(CardTransaction.wallet_id == wallet.id)
        .order_by(desc(CardTransaction.created_at))
        .limit(40)
    ).all()

    return {
        "wallet_id": wallet.id,
        "balance_aoa": float(wallet.balance_aoa),
        "currency": wallet.currency,
        "is_locked": wallet.is_locked,
        "cards": [serialize_card(db, c) for c in cards],
        "transactions": [serialize_transaction(db, t) for t in txs],
    }


@router.get("/notifications")
def get_my_notifications(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    notifs = db.scalars(
        select(Notification)
        .where(Notification.user_id == user.id)
        .order_by(desc(Notification.created_at))
        .limit(25)
    ).all()
    return [
        {
            "id": n.id,
            "title": n.title,
            "message": n.message,
            "category": n.category,
            "is_read": n.is_read,
            "created_at": n.created_at.isoformat() if n.created_at else None,
        }
        for n in notifs
    ]
