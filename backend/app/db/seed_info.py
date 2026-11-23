from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import now_luanda
from app.core.security import hash_password
from app.models.identity import Driver, Passenger, User
from app.models.intelligence import (
    DemandObservation,
    DriverReport,
    MobilityIndicator,
    Municipality,
    Neighborhood,
    PlatformConfig,
    RouteDestination,
    SupplyObservation,
    TaxiStop,
    TransportIntention,
    TransportRoute,
    TransportZone,
)
from app.services.info_engine_service import DEFAULT_THRESHOLDS


def seed_mobility_info_data(db: Session) -> None:
    """
    Idempotently seed Luanda's geographic hierarchy (Municipalities -> Neighborhoods -> Zones -> Stops -> Routes),
    configurable thresholds, a FIELD_COLLECTOR account, and clearly labeled demo observations (is_demo_data=True).
    """
    if db.scalar(select(Municipality).limit(1)):
        return

    # 1. Configurable Thresholds
    for k, (val, desc_txt) in DEFAULT_THRESHOLDS.items():
        if not db.scalar(select(PlatformConfig).where(PlatformConfig.key == k)):
            db.add(PlatformConfig(key=k, value=val, description=desc_txt))

    # 2. Municipalities of Luanda
    muni_names = ["Luanda", "Kilamba Kiaxi", "Talatona", "Belas", "Viana"]
    munis: dict[str, Municipality] = {}
    for name in muni_names:
        m = Municipality(name=name, province="Luanda")
        db.add(m)
        db.flush()
        munis[name] = m

    # 3. Neighborhoods -> Zones -> Validated Taxi Stops
    # Includes every zone mentioned in the strategic prompt (Gamek, Rocha Gamek, Golf 2, Maianga, Alvalade, Mutamba, Aeroporto, Talatona, Kilamba, Viana, Samba, Ingombota)
    geo_specs = [
        ("Luanda", "Maianga", "Maianga", -8.8318, 13.2345, "Paragem Largo da Maianga", "Junto à Praça da Maianga"),
        ("Luanda", "Alvalade", "Alvalade", -8.8265, 13.2415, "Paragem de Alvalade", "Avenida Comandante Gika / Alvalade"),
        ("Luanda", "Ingombota", "Mutamba", -8.8147, 13.2302, "Terminal Largo da Mutamba", "Centro financeiro de Luanda"),
        ("Luanda", "Samba", "Gamek", -8.8842, 13.2148, "Paragem Principal do Gamek", "Av. Deolinda Rodrigues / Gamek"),
        ("Luanda", "Rocha Pinto", "Rocha Gamek", -8.8788, 13.2082, "Paragem Rocha Gamek", "Ligação Rocha Pinto / Gamek"),
        ("Kilamba Kiaxi", "Golf 2", "Golf 2", -8.8895, 13.2490, "Paragem do Golf 2", "Estrada do Golf 2 / Desvio"),
        ("Luanda", "Cassenda", "Aeroporto", -8.8584, 13.2312, "Paragem Aeroporto 4 de Fevereiro", "Entrada Terminal Internacional"),
        ("Talatona", "Talatona", "Talatona", -8.9186, 13.1846, "Paragem Belas / Talatona", "Via S8 / Centro de Convenções"),
        ("Belas", "Kilamba", "Kilamba", -9.0008, 13.2683, "Paragem Centralidade do Kilamba", "Entrada Principal do Kilamba"),
        ("Viana", "Viana Sede", "Viana", -8.9036, 13.3745, "Paragem Ponte Partida / Viana", "Estrada de Catete / Viana"),
    ]

    zones: dict[str, TransportZone] = {}
    stops: dict[str, TaxiStop] = {}
    neighs: dict[str, Neighborhood] = {}

    for muni_name, nb_name, z_name, lat, lng, stop_name, landmark in geo_specs:
        if nb_name not in neighs:
            nb = Neighborhood(municipality_id=munis[muni_name].id, name=nb_name)
            db.add(nb)
            db.flush()
            neighs[nb_name] = nb
        tz = TransportZone(
            neighborhood_id=neighs[nb_name].id,
            name=z_name,
            center_lat=lat,
            center_lng=lng,
        )
        db.add(tz)
        db.flush()
        zones[z_name] = tz

        ts = TaxiStop(
            zone_id=tz.id,
            name=stop_name,
            landmark=landmark,
            latitude=lat,
            longitude=lng,
            is_validated=True,
        )
        db.add(ts)
        db.flush()
        stops[z_name] = ts

    # 4. Real Luanda Transport Routes
    routes_spec = [
        ("VIA-GMK-MAI", "Via Gamek → Maianga", "Gamek", "Maianga", "Corredor Gamek / Cassenda / Maianga", "MODERATE_TRAFFIC"),
        ("VIA-RGM-MAI", "Via Rocha Gamek → Maianga", "Rocha Gamek", "Maianga", "Alternativa via Rocha Pinto / Samba / Maianga", "NORMAL"),
        ("VIA-GLF-MAI", "Via Golf 2 → Maianga", "Golf 2", "Maianga", "Corredor Golf 2 / Martíres / Maianga", "HEAVY_TRAFFIC"),
        ("VIA-GMK-AER", "Via Gamek → Aeroporto", "Gamek", "Aeroporto", "Ligação directa Gamek → Aeroporto 4 de Fevereiro", "NORMAL"),
        ("VIA-ALV-MUT", "Via Alvalade → Mutamba", "Alvalade", "Mutamba", "Corredor urbano Alvalade / Mutamba", "NORMAL"),
        ("VIA-TAL-MAI", "Via Talatona → Maianga", "Talatona", "Maianga", "Via Expressa / Samba / Maianga", "MODERATE_TRAFFIC"),
        ("VIA-VIA-MUT", "Via Viana → Mutamba", "Viana", "Mutamba", "Av. Deolinda Rodrigues / Viana → Centro", "HEAVY_TRAFFIC"),
        ("VIA-KIL-TAL", "Via Kilamba → Talatona", "Kilamba", "Talatona", "Corredor Sul Kilamba → Talatona", "NORMAL"),
        # Intentionally left with NO active records so users can verify "Informação insuficiente para esta via."
        ("VIA-VIA-KIL", "Via Viana → Kilamba", "Viana", "Kilamba", "Ligação periférica Viana → Kilamba (sem recolha activa)", "NORMAL"),
    ]

    routes: dict[str, TransportRoute] = {}
    for code, name, oz, dz, desc_txt, road in routes_spec:
        r = TransportRoute(
            code=code,
            name=name,
            origin_zone_id=zones[oz].id,
            destination_zone_id=zones[dz].id,
            corridor_description=desc_txt,
            road_condition=road,
        )
        db.add(r)
        db.flush()
        routes[code] = r
        db.add(RouteDestination(route_id=r.id, taxi_stop_id=stops[oz].id, sequence_order=1, is_primary_destination=False))
        db.add(RouteDestination(route_id=r.id, taxi_stop_id=stops[dz].id, sequence_order=2, is_primary_destination=True))

    # 5. Field Collector Account (Recolha Operacional de Campo)
    collector = db.scalar(select(User).where(User.email == "campo@dalalink.ao"))
    if not collector:
        collector = User(
            full_name="Nelson Quissanga (Recolha de Campo)",
            email="campo@dalalink.ao",
            phone="+244923400001",
            password_hash=hash_password("dalalink123"),
            role="FIELD_COLLECTOR",
        )
        db.add(collector)
        db.flush()

    # 6. Clearly marked DEMO records (is_demo_data=True) mirroring the prompt examples:
    # - Gamek -> Maianga: high demand (field observation: 22 waiting + 8 taxis observed, plus driver declarations)
    # - Rocha Gamek -> Maianga: moderate demand & favorable supply (alternative stop!)
    # - Golf 2 -> Maianga: moderate-high demand
    # - Alvalade -> Mutamba: low demand, high supply
    # - Viana -> Kilamba: 0 records -> "Informação insuficiente para esta via."
    now = now_luanda()
    drivers = db.scalars(select(Driver).order_by(Driver.id)).all()
    passengers = db.scalars(select(Passenger).order_by(Passenger.id)).all()

    # Field observations (VALIDATED, RECENT, is_demo_data=True)
    db.add_all(
        [
            DemandObservation(
                observer_user_id=collector.id,
                taxi_stop_id=stops["Gamek"].id,
                route_id=routes["VIA-GMK-MAI"].id,
                origin_zone_name="Gamek",
                destination_zone_name="Maianga",
                observed_passengers_count=22,
                estimated_wait_min=14,
                notes="[DEMO] Concentração elevada na paragem do Gamek sentido Maianga.",
                validation_status="VALIDATED",
                confidence_level="HIGH",
                is_demo_data=True,
                observed_at=now - timedelta(minutes=4),
                expires_at=now + timedelta(minutes=41),
            ),
            SupplyObservation(
                observer_user_id=collector.id,
                taxi_stop_id=stops["Gamek"].id,
                route_id=routes["VIA-GMK-MAI"].id,
                origin_zone_name="Gamek",
                destination_zone_name="Maianga",
                observed_taxis_count=5,
                road_condition="MODERATE_TRAFFIC",
                notes="[DEMO] 5 táxis azuis e brancos observados a embarcar no Gamek.",
                validation_status="VALIDATED",
                confidence_level="HIGH",
                is_demo_data=True,
                observed_at=now - timedelta(minutes=4),
                expires_at=now + timedelta(minutes=41),
            ),
            DemandObservation(
                observer_user_id=collector.id,
                taxi_stop_id=stops["Rocha Gamek"].id,
                route_id=routes["VIA-RGM-MAI"].id,
                origin_zone_name="Rocha Gamek",
                destination_zone_name="Maianga",
                observed_passengers_count=8,
                estimated_wait_min=6,
                notes="[DEMO] Paragem alternativa Rocha Gamek com fila moderada.",
                validation_status="VALIDATED",
                confidence_level="HIGH",
                is_demo_data=True,
                observed_at=now - timedelta(minutes=6),
                expires_at=now + timedelta(minutes=39),
            ),
            SupplyObservation(
                observer_user_id=collector.id,
                taxi_stop_id=stops["Rocha Gamek"].id,
                route_id=routes["VIA-RGM-MAI"].id,
                origin_zone_name="Rocha Gamek",
                destination_zone_name="Maianga",
                observed_taxis_count=6,
                road_condition="NORMAL",
                notes="[DEMO] Boa disponibilidade na Rocha Gamek.",
                validation_status="VALIDATED",
                confidence_level="HIGH",
                is_demo_data=True,
                observed_at=now - timedelta(minutes=6),
                expires_at=now + timedelta(minutes=39),
            ),
            # Stale demo observation on Talatona -> Maianga (25 min old -> STALE!)
            DemandObservation(
                observer_user_id=collector.id,
                taxi_stop_id=stops["Talatona"].id,
                route_id=routes["VIA-TAL-MAI"].id,
                origin_zone_name="Talatona",
                destination_zone_name="Maianga",
                observed_passengers_count=11,
                estimated_wait_min=10,
                notes="[DEMO] Observação com mais de 20 minutos para demonstrar aviso de dado desactualizado.",
                validation_status="VALIDATED",
                confidence_level="MEDIUM",
                is_demo_data=True,
                observed_at=now - timedelta(minutes=25),
                expires_at=now + timedelta(minutes=20),
            ),
            # Pending validation observation (for Admin review queue!)
            DemandObservation(
                observer_user_id=collector.id,
                taxi_stop_id=stops["Golf 2"].id,
                route_id=routes["VIA-GLF-MAI"].id,
                origin_zone_name="Golf 2",
                destination_zone_name="Maianga",
                observed_passengers_count=18,
                estimated_wait_min=16,
                notes="[DEMO] Registo pendente de validação administrativa no Golf 2.",
                validation_status="PENDING",
                confidence_level="MEDIUM",
                is_demo_data=True,
                observed_at=now - timedelta(minutes=3),
                expires_at=now + timedelta(minutes=42),
            ),
        ]
    )

    # Demo Driver availability reports
    if len(drivers) >= 2:
        db.add_all(
            [
                DriverReport(
                    driver_id=drivers[0].id,
                    route_id=routes["VIA-GMK-MAI"].id,
                    taxi_stop_id=stops["Gamek"].id,
                    origin_zone_name="Gamek",
                    destination_zone_name="Maianga",
                    availability_status="AVAILABLE",
                    estimated_seats=4,
                    is_active=True,
                    is_demo_data=True,
                    reported_at=now - timedelta(minutes=5),
                    last_confirmed_at=now - timedelta(minutes=5),
                    expires_at=now + timedelta(minutes=55),
                ),
                DriverReport(
                    driver_id=drivers[1].id,
                    route_id=routes["VIA-ALV-MUT"].id,
                    taxi_stop_id=stops["Alvalade"].id,
                    origin_zone_name="Alvalade",
                    destination_zone_name="Mutamba",
                    availability_status="AT_STOP",
                    estimated_seats=12,
                    is_active=True,
                    is_demo_data=True,
                    reported_at=now - timedelta(minutes=3),
                    last_confirmed_at=now - timedelta(minutes=3),
                    expires_at=now + timedelta(minutes=57),
                ),
            ]
        )

    # Demo Passenger intentions (on secondary accounts so Mateus Domingos starts clean to test declaring & cancelling!)
    if len(passengers) >= 3:
        db.add_all(
            [
                TransportIntention(
                    passenger_id=passengers[1].id,
                    route_id=routes["VIA-GMK-MAI"].id,
                    origin_stop_id=stops["Gamek"].id,
                    destination_stop_id=stops["Maianga"].id,
                    origin_zone_name="Gamek",
                    destination_zone_name="Maianga",
                    passenger_count=2,
                    status="DECLARED",
                    is_demo_data=True,
                    last_confirmed_at=now - timedelta(minutes=5),
                    expires_at=now + timedelta(minutes=55),
                ),
                TransportIntention(
                    passenger_id=passengers[2].id,
                    route_id=routes["VIA-ALV-MUT"].id,
                    origin_stop_id=stops["Alvalade"].id,
                    destination_stop_id=stops["Mutamba"].id,
                    origin_zone_name="Alvalade",
                    destination_zone_name="Mutamba",
                    passenger_count=1,
                    status="DECLARED",
                    is_demo_data=True,
                    last_confirmed_at=now - timedelta(minutes=7),
                    expires_at=now + timedelta(minutes=53),
                ),
            ]
        )

    # Historical snapshot for trend comparison
    db.add(
        MobilityIndicator(
            route_id=routes["VIA-GMK-MAI"].id,
            taxi_stop_id=stops["Gamek"].id,
            origin_zone_name="Gamek",
            destination_zone_name="Maianga",
            estimated_demand=16,
            confirmed_demand=14,
            declared_supply=2,
            observed_supply=4,
            demand_supply_ratio=2.67,
            demand_level="PROCURA_ELEVADA",
            supply_level="OFERTA_MODERADA",
            estimated_wait_min=11,
            freshness_status="RECENT",
            captured_at=now - timedelta(hours=1),
        )
    )

    db.commit()
