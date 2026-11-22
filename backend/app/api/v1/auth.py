from datetime import date, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.v1.serializers import serialize_user
from app.core.security import create_access_token, hash_password, verify_password
from app.db.session import get_db
from app.models.corporate import Company, Subscription
from app.models.fleet import DriverAvailability, Vehicle
from app.models.identity import Driver, Passenger, User
from app.schemas.schemas import LoginRequest, RegisterRequest, TokenResponse
from app.services.audit_service import record_audit
from app.services.card_wallet_service import issue_card_for_passenger

router = APIRouter(prefix="/auth", tags=["Autenticação"])


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, db: Session = Depends(get_db)):
    role = payload.role.upper()
    if role not in {"PASSENGER", "DRIVER", "COMPANY_ADMIN"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Perfil inválido. Escolha PASSENGER, DRIVER ou COMPANY_ADMIN.",
        )

    if db.scalar(select(User).where(User.email == payload.email.lower())):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Este email já está registado.")
    if db.scalar(select(User).where(User.phone == payload.phone.strip())):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Este número de telefone já está registado.",
        )

    user = User(
        full_name=payload.full_name.strip(),
        email=payload.email.lower(),
        phone=payload.phone.strip(),
        password_hash=hash_password(payload.password),
        role=role,
    )
    db.add(user)
    db.flush()

    if role == "PASSENGER":
        passenger = Passenger(user_id=user.id, default_zone="Gamek")
        db.add(passenger)
        db.flush()
        # Issue a prepaid QR mobility card automatically (starting balance 0 AOA until admin top-up)
        issue_card_for_passenger(
            db,
            passenger=passenger,
            initial_balance_aoa=Decimal("0.00"),
            actor_user_id=user.id,
        )
    elif role == "DRIVER":
        if not payload.license_number or not payload.national_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Motoristas devem indicar carta de condução e número do BI.",
            )
        driver = Driver(
            user_id=user.id,
            license_number=payload.license_number.strip(),
            national_id=payload.national_id.strip(),
            verification_status="PENDING",
            verification_notes="Aguarda validação documental pelo administrador.",
        )
        db.add(driver)
        db.flush()

        vehicle_id = None
        if payload.vehicle_make and payload.vehicle_model and payload.vehicle_plate:
            veh = Vehicle(
                driver_id=driver.id,
                make=payload.vehicle_make.strip(),
                model=payload.vehicle_model.strip(),
                color=payload.vehicle_color or "Branco",
                license_plate=payload.vehicle_plate.strip().upper(),
                capacity=payload.vehicle_capacity,
                is_active=True,
            )
            db.add(veh)
            db.flush()
            vehicle_id = veh.id

        db.add(
            DriverAvailability(
                driver_id=driver.id,
                active_vehicle_id=vehicle_id,
                status="OFFLINE",
                current_lat=-8.8842,
                current_lng=13.2148,
                current_zone="Gamek",
            )
        )
    elif role == "COMPANY_ADMIN":
        cname = payload.company_name or f"Empresa de {payload.full_name}"
        nif = payload.company_nif or f"5417{user.id:06d}"
        company = Company(
            name=cname,
            nif=nif,
            contact_email=user.email,
            contact_phone=user.phone,
            headquarters_zone="Talatona",
        )
        db.add(company)
        db.flush()
        today = date.today()
        db.add(
            Subscription(
                company_id=company.id,
                plan_name="Corporativo Inicial",
                monthly_fee_aoa=Decimal("250000.00"),
                max_employees=50,
                status="ACTIVE",
                start_date=today,
                end_date=today + timedelta(days=365),
            )
        )

    record_audit(
        db,
        action="USER_REGISTERED",
        entity_type="User",
        entity_id=user.id,
        actor_user_id=user.id,
        details={"role": role, "email": user.email},
    )
    db.commit()
    db.refresh(user)

    token = create_access_token(subject=str(user.id), role=user.role)
    return TokenResponse(access_token=token, user=serialize_user(db, user))


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == payload.email.lower()))
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email ou palavra-passe incorretos.",
        )
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Conta desativada.")

    token = create_access_token(subject=str(user.id), role=user.role)
    return TokenResponse(access_token=token, user=serialize_user(db, user))


@router.get("/me")
def get_me(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return serialize_user(db, user)


@router.get("/demo-accounts")
def list_demo_accounts():
    """Return quick-access demo profiles for testing all 4 environments in Luanda."""
    return {
        "default_password": "dalalink123",
        "accounts": [
            {
                "role": "PASSENGER",
                "label": "Passageiro — Mateus Domingos (Cartão MOB-000001 • 10.000 AOA)",
                "email": "passageiro@dalalink.ao",
                "environment": "Aplicação do Passageiro",
            },
            {
                "role": "DRIVER",
                "label": "Motorista — Carlos Eduardo (Hyundai i10 • Gamek)",
                "email": "motorista@dalalink.ao",
                "environment": "Aplicação do Motorista",
            },
            {
                "role": "DRIVER",
                "label": "Motorista 2 — Fernando Quiosa (Toyota HiAce 12 lug. • Maianga)",
                "email": "motorista2@dalalink.ao",
                "environment": "Aplicação do Motorista",
            },
            {
                "role": "COMPANY_ADMIN",
                "label": "Empresa — Sofia Mendes (Atlântico Energia • Talatona)",
                "email": "empresa@dalalink.ao",
                "environment": "Portal Empresarial",
            },
            {
                "role": "ADMIN",
                "label": "Administração — Adélio António (Torre de Controlo Luanda)",
                "email": "admin@dalalink.ao",
                "environment": "Painel Administrativo",
            },
        ],
    }
