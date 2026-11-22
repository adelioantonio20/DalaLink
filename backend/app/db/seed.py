from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import now_luanda
from app.core.security import hash_password
from app.models.corporate import Company, Employee, Route, Stop, Subscription
from app.models.finance import Tariff
from app.models.fleet import DriverAvailability, Vehicle, VehicleLocation
from app.models.identity import Driver, Passenger, User, VehicleOwner
from app.services.card_wallet_service import issue_card_for_passenger, set_card_status
from app.services.geo_service import LUANDA_ZONES


def seed_database(db: Session) -> None:
    """Idempotently populate Luanda demo data so all 4 portals are immediately testable."""
    existing_admin = db.scalar(select(User).where(User.email == "admin@dalalink.ao"))
    if existing_admin:
        return

    demo_pw = hash_password("dalalink123")

    # 1. Active Tariffs (calibrated so Gamek -> Aeroporto = 1.000 AOA)
    tariff_sedan = Tariff(
        name="Tarifa Urbana Padrão Luanda",
        vehicle_type="TAXI_SEDAN",
        base_fare_aoa=Decimal("450.00"),
        per_km_aoa=Decimal("90.00"),
        per_minute_aoa=Decimal("15.00"),
        min_fare_aoa=Decimal("800.00"),
        commission_rate=Decimal("0.1500"),
        is_active=True,
    )
    tariff_van = Tariff(
        name="Tarifa Coletiva / Carrinha Luanda",
        vehicle_type="HIACE_VAN",
        base_fare_aoa=Decimal("400.00"),
        per_km_aoa=Decimal("80.00"),
        per_minute_aoa=Decimal("12.00"),
        min_fare_aoa=Decimal("700.00"),
        commission_rate=Decimal("0.1200"),
        is_active=True,
    )
    db.add_all([tariff_sedan, tariff_van])
    db.flush()

    # 2. Luanda Public Hubs / Stops
    for idx, z in enumerate(LUANDA_ZONES, start=1):
        db.add(
            Stop(
                name=z["name"],
                zone_name=z["zone"],
                latitude=z["lat"],
                longitude=z["lng"],
                sequence_order=idx,
                is_public_hub=True,
            )
        )

    # 3. Admin & Owner Users
    admin_user = User(
        full_name="Adélio António (Admin)",
        email="admin@dalalink.ao",
        phone="+244923000001",
        password_hash=demo_pw,
        role="ADMIN",
    )
    owner_user = User(
        full_name="Frota DalaLink Luanda",
        email="frota@dalalink.ao",
        phone="+244923000002",
        password_hash=demo_pw,
        role="OWNER",
    )
    db.add_all([admin_user, owner_user])
    db.flush()

    owner = VehicleOwner(
        user_id=owner_user.id,
        company_name="DalaLink Operações Piloto Lda",
        tax_id="5417001928",
        payout_iban="AO06004000001234567890123",
    )
    db.add(owner)
    db.flush()

    # 4. Passengers + Wallets + Prepaid QR Cards
    passengers_spec = [
        ("Mateus Domingos", "passageiro@dalalink.ao", "+244923100001", "Gamek", "MOB-000001", Decimal("10000.00"), "ACTIVE"),
        ("Ana Paula Costa", "ana@dalalink.ao", "+244923100002", "Gamek", "MOB-000002", Decimal("5000.00"), "ACTIVE"),
        ("João Manuel", "joao@dalalink.ao", "+244923100003", "Maianga", "MOB-000003", Decimal("400.00"), "ACTIVE"),
        ("Sara Baptista", "sara@dalalink.ao", "+244923100004", "Talatona", "MOB-000004", Decimal("8000.00"), "BLOCKED"),
    ]
    for full_name, email, phone, zone, card_code, balance, card_status in passengers_spec:
        u = User(
            full_name=full_name,
            email=email,
            phone=phone,
            password_hash=demo_pw,
            role="PASSENGER",
        )
        db.add(u)
        db.flush()
        p = Passenger(user_id=u.id, default_zone=zone)
        db.add(p)
        db.flush()
        card = issue_card_for_passenger(
            db,
            passenger=p,
            initial_balance_aoa=balance,
            custom_card_code=card_code,
            actor_user_id=admin_user.id,
        )
        if card_status != "ACTIVE":
            set_card_status(
                db,
                card_code=card.card_code,
                new_status=card_status,
                reason="Cartão de teste bloqueado por segurança",
                actor_user_id=admin_user.id,
            )

    # 5. Drivers & Vehicles (including Hyundai i10 pilot test vehicle near Gamek!)
    drivers_spec = [
        {
            "name": "Carlos Eduardo",
            "email": "motorista@dalalink.ao",
            "phone": "+244923200001",
            "license": "LD-CON-2021-8841",
            "national_id": "004829102LA041",
            "ver_status": "APPROVED",
            "make": "Hyundai",
            "model": "i10",
            "year": 2023,
            "color": "Branco Pérola",
            "plate": "LD-42-18-AB",
            "vtype": "TAXI_SEDAN",
            "cap": 4,
            "avail": "AVAILABLE",
            "lat": -8.8805,
            "lng": 13.2175,
            "zone": "Gamek",
        },
        {
            "name": "Fernando Quiosa",
            "email": "motorista2@dalalink.ao",
            "phone": "+244923200002",
            "license": "LD-CON-2019-4410",
            "national_id": "003190441LA032",
            "ver_status": "APPROVED",
            "make": "Toyota",
            "model": "HiAce",
            "year": 2021,
            "color": "Azul e Branco",
            "plate": "LD-88-90-CD",
            "vtype": "HIACE_VAN",
            "cap": 12,
            "avail": "AVAILABLE",
            "lat": -8.8330,
            "lng": 13.2340,
            "zone": "Maianga",
        },
        {
            "name": "Miguel Teixeira",
            "email": "motorista3@dalalink.ao",
            "phone": "+244923200003",
            "license": "LD-CON-2024-9102",
            "national_id": "007120338LA045",
            "ver_status": "PENDING",
            "make": "Kia",
            "model": "Picanto",
            "year": 2022,
            "color": "Cinzento Metálico",
            "plate": "LD-15-77-EF",
            "vtype": "TAXI_SEDAN",
            "cap": 4,
            "avail": "OFFLINE",
            "lat": -8.9180,
            "lng": 13.1860,
            "zone": "Talatona",
        },
    ]

    for spec in drivers_spec:
        du = User(
            full_name=spec["name"],
            email=spec["email"],
            phone=spec["phone"],
            password_hash=demo_pw,
            role="DRIVER",
        )
        db.add(du)
        db.flush()
        drv = Driver(
            user_id=du.id,
            license_number=spec["license"],
            national_id=spec["national_id"],
            verification_status=spec["ver_status"],
            verified_at=now_luanda() if spec["ver_status"] == "APPROVED" else None,
            verification_notes="Documentação validada para operação piloto em Luanda."
            if spec["ver_status"] == "APPROVED"
            else "Aguarda validação do BI, Carta de Condução e Livrete.",
        )
        db.add(drv)
        db.flush()
        veh = Vehicle(
            owner_id=owner.id,
            driver_id=drv.id,
            make=spec["make"],
            model=spec["model"],
            year=spec["year"],
            color=spec["color"],
            license_plate=spec["plate"],
            vehicle_type=spec["vtype"],
            capacity=spec["cap"],
            is_active=True,
        )
        db.add(veh)
        db.flush()
        db.add(
            DriverAvailability(
                driver_id=drv.id,
                active_vehicle_id=veh.id,
                status=spec["avail"],
                current_lat=spec["lat"],
                current_lng=spec["lng"],
                current_zone=spec["zone"],
            )
        )
        db.add(
            VehicleLocation(
                vehicle_id=veh.id,
                latitude=spec["lat"],
                longitude=spec["lng"],
                speed_kmh=0.0,
                zone_name=spec["zone"],
            )
        )

    # 6. Corporate Account & Routes (Foundation for Phase 2)
    corp_user = User(
        full_name="Sofia Mendes (Gestora Corporativa)",
        email="empresa@dalalink.ao",
        phone="+244923300001",
        password_hash=demo_pw,
        role="COMPANY_ADMIN",
    )
    db.add(corp_user)
    db.flush()

    company = Company(
        name="Atlântico Energia & Serviços, Lda.",
        nif="5000812345",
        contact_email="empresa@dalalink.ao",
        contact_phone="+244923300001",
        headquarters_zone="Talatona",
    )
    db.add(company)
    db.flush()

    today = date.today()
    db.add(
        Subscription(
            company_id=company.id,
            plan_name="Corporativo Luanda 100",
            monthly_fee_aoa=Decimal("450000.00"),
            max_employees=100,
            status="ACTIVE",
            start_date=today - timedelta(days=15),
            end_date=today + timedelta(days=350),
        )
    )

    corp_employees = [
        ("Sofia Mendes", "empresa@dalalink.ao", "Administração", "Talatona", "Maianga", "17:00", corp_user.id),
        ("Pedro Nogueira", "pedro.n@atlantico.ao", "Engenharia", "Talatona", "Aeroporto", "17:00", None),
        ("Beatriz Lopes", "beatriz.l@atlantico.ao", "Finanças", "Talatona", "Mutamba", "17:00", None),
        ("Rui Tavares", "rui.t@atlantico.ao", "Logística", "Talatona", "Kilamba", "17:00", None),
        ("Cláudia Neto", "claudia.n@atlantico.ao", "RH", "Talatona", "Gamek", "17:00", None),
    ]
    for name, email, dept, pzone, dzone, shift, uid in corp_employees:
        db.add(
            Employee(
                company_id=company.id,
                user_id=uid,
                full_name=name,
                email=email,
                department=dept,
                pickup_zone=pzone,
                dropoff_zone=dzone,
                shift_time=shift,
                status="ACTIVE",
            )
        )

    db.add_all(
        [
            Route(
                company_id=company.id,
                name="Rota Corporativa Sul — Talatona → Gamek → Aeroporto",
                origin_zone="Talatona",
                destination_zone="Aeroporto",
                scheduled_time="17:00",
                is_corporate=True,
                notes="Recolha diária de colaboradores do turno das 17h00.",
            ),
            Route(
                company_id=company.id,
                name="Rota Corporativa Centro — Talatona → Maianga → Mutamba",
                origin_zone="Talatona",
                destination_zone="Mutamba",
                scheduled_time="17:00",
                is_corporate=True,
                notes="Ligação empresarial ao centro financeiro de Luanda.",
            ),
        ]
    )

    db.commit()
