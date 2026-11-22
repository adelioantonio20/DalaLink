import secrets
from decimal import Decimal
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import now_luanda
from app.core.security import generate_qr_token, verify_qr_token_signature
from app.models.finance import CardTransaction, TransportCard, Wallet
from app.models.identity import Passenger, User
from app.models.mobility import GroupPassenger, GroupRequest, Trip, TripPassenger
from app.services.audit_service import create_notification, record_audit


def _resolve_card_by_input(db: Session, card_identifier: str) -> Optional[TransportCard]:
    """
    Resolve card from:
      1. Signed QR token (DALALINK:MOB-XXXXXX:...)
      2. Physical NFC card UID (NFC:<uid>)
      3. Card code (MOB-000001)
    Balance is NEVER stored on the card/QR/NFC — only verified server-side.
    """
    raw = card_identifier.strip()
    if raw.startswith("DALALINK:"):
        verified_code = verify_qr_token_signature(raw)
        if not verified_code:
            return None
        return db.scalar(
            select(TransportCard).where(
                TransportCard.card_code == verified_code,
                TransportCard.qr_token == raw,
            )
        )
    if raw.upper().startswith("NFC:"):
        uid = raw[4:].strip().upper()
        if not uid:
            return None
        return db.scalar(select(TransportCard).where(TransportCard.nfc_uid == uid))
    return db.scalar(select(TransportCard).where(TransportCard.card_code == raw.upper()))


def bind_nfc_to_card(
    db: Session,
    card_code: str,
    nfc_uid: str,
    card_technology: str = "QR+NFC",
    actor_user_id: Optional[int] = None,
) -> TransportCard:
    card = _resolve_card_by_input(db, card_code)
    if not card:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cartão não encontrado.")
    clean_uid = nfc_uid.strip().upper()
    existing = db.scalar(
        select(TransportCard).where(TransportCard.nfc_uid == clean_uid, TransportCard.id != card.id)
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Este UID NFC ({clean_uid}) já está associado ao cartão {existing.card_code}.",
        )
    card.nfc_uid = clean_uid
    card.card_technology = card_technology
    record_audit(
        db,
        action="CARD_NFC_BOUND",
        entity_type="TransportCard",
        entity_id=card.id,
        actor_user_id=actor_user_id,
        details={"card_code": card.card_code, "nfc_uid": clean_uid, "technology": card_technology},
    )
    return card


def _lock_wallet(db: Session, wallet_id: int) -> Wallet:
    stmt = select(Wallet).where(Wallet.id == wallet_id)
    # Apply row-level FOR UPDATE lock on PostgreSQL (SQLite serializes write transactions automatically)
    if db.bind and db.bind.dialect.name != "sqlite":
        stmt = stmt.with_for_update()
    wallet = db.scalar(stmt)
    if not wallet:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Carteira não encontrada.")
    return wallet


def issue_card_for_passenger(
    db: Session,
    passenger: Passenger,
    initial_balance_aoa: Decimal = Decimal("0.00"),
    custom_card_code: Optional[str] = None,
    actor_user_id: Optional[int] = None,
) -> TransportCard:
    wallet = db.scalar(select(Wallet).where(Wallet.passenger_id == passenger.id))
    if not wallet:
        wallet = Wallet(passenger_id=passenger.id, balance_aoa=Decimal("0.00"), currency="AOA")
        db.add(wallet)
        db.flush()

    if custom_card_code:
        card_code = custom_card_code.upper()
    else:
        total_cards = db.scalar(select(func.count(TransportCard.id))) or 0
        next_num = total_cards + 1
        card_code = f"MOB-{next_num:06d}"
        while db.scalar(select(TransportCard.id).where(TransportCard.card_code == card_code)):
            next_num += 1
            card_code = f"MOB-{next_num:06d}"

    qr_token = generate_qr_token(card_code)
    card = TransportCard(
        wallet_id=wallet.id,
        card_code=card_code,
        qr_token=qr_token,
        card_technology="QR",
        status="ACTIVE",
    )
    db.add(card)
    db.flush()

    record_audit(
        db,
        action="CARD_ISSUED",
        entity_type="TransportCard",
        entity_id=card.id,
        actor_user_id=actor_user_id,
        details={"card_code": card_code, "passenger_id": passenger.id},
    )

    if initial_balance_aoa > Decimal("0.00"):
        topup_card_admin(
            db=db,
            card_code=card.card_code,
            amount_aoa=initial_balance_aoa,
            description="Saldo inicial administrativo do cartão",
            actor_user_id=actor_user_id,
            idempotency_key=f"INIT-{card.card_code}-{secrets.token_hex(4)}",
        )

    return card


def topup_card_admin(
    db: Session,
    card_code: str,
    amount_aoa: Decimal,
    description: str,
    actor_user_id: Optional[int],
    idempotency_key: Optional[str] = None,
) -> CardTransaction:
    if amount_aoa <= Decimal("0.00"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="O valor do carregamento deve ser superior a 0 AOA.",
        )

    idem_key = idempotency_key or f"TOPUP-{card_code.upper()}-{secrets.token_hex(6)}"
    existing = db.scalar(select(CardTransaction).where(CardTransaction.idempotency_key == idem_key))
    if existing:
        return existing

    card = _resolve_card_by_input(db, card_code)
    if not card:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cartão não encontrado.")

    wallet = _lock_wallet(db, card.wallet_id)
    before = Decimal(wallet.balance_aoa)
    after = (before + amount_aoa).quantize(Decimal("0.01"))
    wallet.balance_aoa = after

    tx = CardTransaction(
        card_id=card.id,
        wallet_id=wallet.id,
        tx_type="TOPUP_ADMIN",
        amount_aoa=amount_aoa.quantize(Decimal("0.01")),
        balance_before_aoa=before,
        balance_after_aoa=after,
        idempotency_key=idem_key,
        status="COMPLETED",
        description=description or "Carregamento administrativo",
        performed_by_user_id=actor_user_id,
    )
    db.add(tx)
    db.flush()

    passenger = db.get(Passenger, wallet.passenger_id)
    if passenger:
        create_notification(
            db,
            user_id=passenger.user_id,
            title="Carregamento confirmado",
            message=f"Cartão {card.card_code} carregado com {amount_aoa:,.0f} AOA. Saldo atual: {after:,.0f} AOA.",
            category="WALLET",
        )

    record_audit(
        db,
        action="CARD_TOPUP",
        entity_type="CardTransaction",
        entity_id=tx.id,
        actor_user_id=actor_user_id,
        details={
            "card_code": card.card_code,
            "amount_aoa": str(amount_aoa),
            "balance_after_aoa": str(after),
        },
    )
    return tx


def set_card_status(
    db: Session,
    card_code: str,
    new_status: str,
    reason: Optional[str],
    actor_user_id: Optional[int],
) -> TransportCard:
    if new_status not in {"ACTIVE", "BLOCKED", "LOST", "REVOKED"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Estado de cartão inválido.")

    card = _resolve_card_by_input(db, card_code)
    if not card:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cartão não encontrado.")

    prev_status = card.status
    card.status = new_status
    if new_status in {"BLOCKED", "LOST", "REVOKED"}:
        card.blocked_at = now_luanda()
        card.block_reason = reason or "Bloqueio administrativo"
    else:
        card.blocked_at = None
        card.block_reason = None

    record_audit(
        db,
        action=f"CARD_STATUS_{new_status}",
        entity_type="TransportCard",
        entity_id=card.id,
        actor_user_id=actor_user_id,
        details={"card_code": card.card_code, "previous": prev_status, "new": new_status, "reason": reason},
    )
    return card


def refund_transaction(
    db: Session,
    transaction_id: int,
    reason: str,
    actor_user_id: int,
) -> CardTransaction:
    original = db.get(CardTransaction, transaction_id)
    if not original or original.tx_type != "TRIP_DEBIT" or original.status != "COMPLETED":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Apenas débitos de viagem concluídos podem ser reembolsados.",
        )

    idem_key = f"REFUND-TX-{original.id}"
    existing = db.scalar(select(CardTransaction).where(CardTransaction.idempotency_key == idem_key))
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Esta transação já foi reembolsada anteriormente.",
        )

    wallet = _lock_wallet(db, original.wallet_id)
    before = Decimal(wallet.balance_aoa)
    amount = Decimal(original.amount_aoa)
    after = (before + amount).quantize(Decimal("0.01"))
    wallet.balance_aoa = after

    refund_tx = CardTransaction(
        card_id=original.card_id,
        wallet_id=wallet.id,
        trip_id=original.trip_id,
        tx_type="REFUND",
        amount_aoa=amount,
        balance_before_aoa=before,
        balance_after_aoa=after,
        idempotency_key=idem_key,
        status="COMPLETED",
        description=f"Reembolso autorizado (Tx #{original.id}): {reason}",
        performed_by_user_id=actor_user_id,
    )
    db.add(refund_tx)
    db.flush()

    card = db.get(TransportCard, original.card_id)
    passenger = db.get(Passenger, wallet.passenger_id)
    if passenger and card:
        create_notification(
            db,
            user_id=passenger.user_id,
            title="Reembolso creditado",
            message=f"Reembolso de {amount:,.0f} AOA creditado no cartão {card.card_code}. Saldo: {after:,.0f} AOA.",
            category="WALLET",
        )

    record_audit(
        db,
        action="CARD_REFUND",
        entity_type="CardTransaction",
        entity_id=refund_tx.id,
        actor_user_id=actor_user_id,
        details={"original_tx_id": original.id, "amount_aoa": str(amount), "reason": reason},
    )
    return refund_tx


def validate_and_debit_boarding(
    db: Session,
    trip: Trip,
    card_identifier: str,
    driver_user_id: int,
    idempotency_key: Optional[str] = None,
) -> dict:
    """
    Atomic QR card boarding validation & fare debit.
    Guarantees:
      1. Server-side balance verification only (never trusts client balance).
      2. Card status ACTIVE & valid HMAC QR signature (when QR token supplied).
      3. Duplicate debit prevention via idempotency_key AND unique(trip_id, card_id).
      4. Atomic debit + CardTransaction + TripPassenger + audit log.
    """
    if trip.status not in {"DRIVER_EN_ROUTE", "DRIVER_ARRIVED", "IN_PROGRESS"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Não é possível validar embarque numa viagem no estado {trip.status}.",
        )

    card = _resolve_card_by_input(db, card_identifier)
    if not card:
        record_audit(
            db,
            action="BOARDING_DECLINED_INVALID_CARD",
            entity_type="Trip",
            entity_id=trip.id,
            actor_user_id=driver_user_id,
            details={"card_identifier": card_identifier},
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Cartão QR inválido ou assinatura não reconhecida.",
        )

    idem_key = idempotency_key or f"BOARDING-TRIP-{trip.id}-CARD-{card.id}"

    # Check idempotency first
    existing_tx = db.scalar(select(CardTransaction).where(CardTransaction.idempotency_key == idem_key))
    if existing_tx:
        wallet_now = db.get(Wallet, card.wallet_id)
        passenger = db.get(Passenger, wallet_now.passenger_id) if wallet_now else None
        p_user = db.get(User, passenger.user_id) if passenger else None
        return {
            "authorized": existing_tx.status == "COMPLETED",
            "duplicate_prevented": True,
            "message": "Validação já processada anteriormente (débito duplicado impedido).",
            "card_code": card.card_code,
            "passenger_name": p_user.full_name if p_user else "Passageiro",
            "amount_debited_aoa": float(existing_tx.amount_aoa),
            "balance_before_aoa": float(existing_tx.balance_before_aoa),
            "balance_after_aoa": float(existing_tx.balance_after_aoa),
            "transaction_id": existing_tx.id,
        }

    # Check if this card already boarded this trip
    existing_boarding = db.scalar(
        select(TripPassenger).where(
            TripPassenger.trip_id == trip.id,
            TripPassenger.transport_card_id == card.id,
            TripPassenger.boarding_status == "BOARDED",
        )
    )
    if existing_boarding:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"O cartão {card.card_code} já teve embarque validado nesta viagem (débito duplicado bloqueado).",
        )

    if card.status != "ACTIVE":
        record_audit(
            db,
            action="BOARDING_DECLINED_BLOCKED_CARD",
            entity_type="TransportCard",
            entity_id=card.id,
            actor_user_id=driver_user_id,
            details={"trip_id": trip.id, "card_code": card.card_code, "status": card.status},
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Embarque recusado: cartão {card.card_code} está {card.status}.",
        )

    wallet = _lock_wallet(db, card.wallet_id)
    if wallet.is_locked:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Embarque recusado: a carteira associada encontra-se bloqueada.",
        )

    passenger = db.get(Passenger, wallet.passenger_id)
    passenger_user = db.get(User, passenger.user_id) if passenger else None
    fare_to_charge = Decimal(trip.fare_per_passenger_aoa).quantize(Decimal("0.01"))
    before = Decimal(wallet.balance_aoa)

    # Check if this is a group request and whether the card belongs to it (if group members were specified)
    group_req = db.scalar(
        select(GroupRequest).where(GroupRequest.transport_request_id == trip.transport_request_id)
    )
    group_member = None
    if group_req:
        group_member = db.scalar(
            select(GroupPassenger).where(
                GroupPassenger.group_request_id == group_req.id,
                GroupPassenger.transport_card_id == card.id,
            )
        )
        if group_member:
            fare_to_charge = Decimal(group_member.individual_fare_aoa).quantize(Decimal("0.01"))

    if before < fare_to_charge:
        record_audit(
            db,
            action="BOARDING_DECLINED_INSUFFICIENT_BALANCE",
            entity_type="TransportCard",
            entity_id=card.id,
            actor_user_id=driver_user_id,
            details={
                "trip_id": trip.id,
                "card_code": card.card_code,
                "balance_aoa": str(before),
                "required_aoa": str(fare_to_charge),
            },
        )
        if group_member:
            group_member.validation_status = "DECLINED"
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=(
                f"Saldo insuficiente no cartão {card.card_code}. "
                f"Disponível: {before:,.0f} AOA | Necessário: {fare_to_charge:,.0f} AOA."
            ),
        )

    after = (before - fare_to_charge).quantize(Decimal("0.01"))
    wallet.balance_aoa = after

    tx = CardTransaction(
        card_id=card.id,
        wallet_id=wallet.id,
        trip_id=trip.id,
        tx_type="TRIP_DEBIT",
        amount_aoa=fare_to_charge,
        balance_before_aoa=before,
        balance_after_aoa=after,
        idempotency_key=idem_key,
        status="COMPLETED",
        description=(
            f"Viagem #{trip.id}: {trip.transport_request.pickup_zone} → {trip.transport_request.dropoff_zone}"
        ),
        performed_by_user_id=driver_user_id,
    )
    db.add(tx)
    db.flush()

    tp = TripPassenger(
        trip_id=trip.id,
        passenger_id=wallet.passenger_id,
        transport_card_id=card.id,
        fare_charged_aoa=fare_to_charge,
        card_transaction_id=tx.id,
        boarding_status="BOARDED",
        boarded_at=now_luanda(),
    )
    db.add(tp)

    if group_member:
        group_member.validation_status = "BOARDED"

    trip.paid_total_aoa = (Decimal(trip.paid_total_aoa) + fare_to_charge).quantize(Decimal("0.01"))

    if passenger_user:
        create_notification(
            db,
            user_id=passenger_user.id,
            title="Embarque autorizado",
            message=(
                f"Cartão {card.card_code} validado ({fare_to_charge:,.0f} AOA). "
                f"Saldo disponível: {after:,.0f} AOA."
            ),
            category="WALLET",
        )

    record_audit(
        db,
        action="BOARDING_AUTHORIZED",
        entity_type="Trip",
        entity_id=trip.id,
        actor_user_id=driver_user_id,
        details={
            "card_code": card.card_code,
            "amount_debited_aoa": str(fare_to_charge),
            "balance_before_aoa": str(before),
            "balance_after_aoa": str(after),
            "transaction_id": tx.id,
        },
    )

    return {
        "authorized": True,
        "duplicate_prevented": False,
        "message": f"Embarque autorizado! Debitado {fare_to_charge:,.0f} AOA do cartão {card.card_code}.",
        "card_code": card.card_code,
        "passenger_name": passenger_user.full_name if passenger_user else "Passageiro",
        "amount_debited_aoa": float(fare_to_charge),
        "balance_before_aoa": float(before),
        "balance_after_aoa": float(after),
        "transaction_id": tx.id,
    }
