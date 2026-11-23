from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.core.config import now_luanda
from app.db.seed import seed_database
from app.db.seed_info import seed_mobility_info_data
from app.db.session import Base, get_db
from app.main import app
from app.models import *  # noqa: F401, F403
from app.models.intelligence import TransportIntention


@pytest.fixture()
def client(tmp_path):
    db_file = tmp_path / "test_info_mvp.db"
    engine = create_engine(
        f"sqlite:///{db_file}",
        connect_args={"check_same_thread": False},
        future=True,
    )

    @event.listens_for(engine, "connect")
    def _fk(dbapi_conn, _rec):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON;")
        cur.close()

    SessionTesting = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    Base.metadata.create_all(bind=engine)

    db = SessionTesting()
    seed_database(db)
    seed_mobility_info_data(db)
    db.close()

    def override_db():
        s = SessionTesting()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = override_db
    with TestClient(app) as c:
        c._session_factory = SessionTesting  # type: ignore[attr-defined]
        yield c
    app.dependency_overrides.clear()
    engine.dispose()


def _auth(client: TestClient, email: str) -> dict:
    r = client.post("/api/v1/auth/login", json={"email": email, "password": "dalalink123"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_all_22_section11_entities_registered_and_finance_disabled(client: TestClient):
    required = {
        "users", "passengers", "drivers", "driver_availability", "vehicles",
        "municipalities", "neighborhoods", "transport_zones", "taxi_stops",
        "transport_routes", "route_destinations", "transport_intentions",
        "group_intentions", "passenger_confirmations", "driver_reports",
        "supply_observations", "demand_observations", "mobility_indicators",
        "location_updates", "data_validations", "notifications", "audit_logs",
    }
    assert required.issubset(set(Base.metadata.tables.keys()))

    # Legacy finance/wallet routes MUST be disabled in MVP
    health = client.get("/api/v1/health").json()
    assert health["mode"] == "MOBILITY_INFORMATION_MVP"
    assert health["legacy_finance_enabled"] is False
    assert client.get("/api/v1/mobility/wallet").status_code == 404


def test_scenario_1_2_3_4_10_11_passenger_consult_declare_confirm_cancel_and_alternatives(client: TestClient):
    p_headers = _auth(client, "passageiro@dalalink.ao")

    # 1. Consult Gamek -> Maianga + verify alternatives (Rocha Gamek)
    res = client.get("/api/v1/info/corridor?origin_zone=Gamek&destination_zone=Maianga")
    assert res.status_code == 200, res.text
    corridor = res.json()
    assert corridor["has_sufficient_data"] is True
    assert corridor["confirmed_demand"] == 22
    assert corridor["declared_demand"] == 2
    assert corridor["observed_supply"] == 5
    assert corridor["declared_supply"] == 1
    assert corridor["freshness_status"] == "RECENT"
    assert corridor["last_updated_at"] is not None
    assert any(a["origin_zone"] == "Rocha Gamek" for a in corridor["alternatives"])

    # 2. Declare intention on Gamek -> Maianga
    dec = client.post(
        "/api/v1/info/intentions",
        headers=p_headers,
        json={"origin_zone": "Gamek", "destination_zone": "Maianga", "passenger_count": 1},
    )
    assert dec.status_code == 201, dec.text
    int_id = dec.json()["intention"]["id"]
    assert dec.json()["intention"]["status"] == "DECLARED"
    assert dec.json()["corridor"]["declared_demand"] == 3

    # Anti-duplication: second identical declaration must be blocked (409)
    dup = client.post(
        "/api/v1/info/intentions",
        headers=p_headers,
        json={"origin_zone": "Gamek", "destination_zone": "Maianga", "passenger_count": 1},
    )
    assert dup.status_code == 409

    # 3. Distinguish declared vs confirmed at stop
    conf = client.post(
        f"/api/v1/info/intentions/{int_id}/confirm-at-stop",
        headers=p_headers,
        json={"latitude": -8.8841, "longitude": 13.2149},
    )
    assert conf.status_code == 200
    assert conf.json()["intention"]["status"] == "CONFIRMED_AT_STOP"
    assert conf.json()["location_consistent"] is True

    after_confirm = client.get("/api/v1/info/corridor?origin_zone=Gamek&destination_zone=Maianga").json()
    assert after_confirm["confirmed_demand"] == 23
    assert after_confirm["declared_demand"] == 2

    # 4. Cancel intention
    canc = client.post(f"/api/v1/info/intentions/{int_id}/cancel", headers=p_headers)
    assert canc.status_code == 200
    after_cancel = client.get("/api/v1/info/corridor?origin_zone=Gamek&destination_zone=Maianga").json()
    assert after_cancel["confirmed_demand"] == 22

    # 10. Insufficient data corridor (Viana -> Kilamba has 0 valid records)
    empty = client.get("/api/v1/info/corridor?origin_zone=Viana&destination_zone=Kilamba").json()
    assert empty["has_sufficient_data"] is False
    assert empty["status_message"] == "Informação insuficiente para esta via."


def test_scenario_5_driver_availability_update_no_double_counting(client: TestClient):
    d_headers = _auth(client, "motorista@dalalink.ao")

    # Driver updates route from Gamek -> Maianga to Golf 2 -> Maianga
    rep1 = client.post(
        "/api/v1/info/driver/availability",
        headers=d_headers,
        json={
            "origin_zone": "Golf 2",
            "destination_zone": "Maianga",
            "availability_status": "AVAILABLE",
            "estimated_seats": 4,
        },
    )
    assert rep1.status_code == 200, rep1.text
    assert rep1.json()["corridor"]["declared_supply"] == 1

    # Submitting again for same route must NOT double-count the same driver!
    rep2 = client.post(
        "/api/v1/info/driver/availability",
        headers=d_headers,
        json={
            "origin_zone": "Golf 2",
            "destination_zone": "Maianga",
            "availability_status": "AT_STOP",
            "estimated_seats": 4,
        },
    )
    assert rep2.status_code == 200
    assert rep2.json()["corridor"]["declared_supply"] == 1

    ov = client.get("/api/v1/info/driver/overview", headers=d_headers).json()
    assert "veículo imobilizado" in ov["safety_notice"].lower()
    assert ov["my_report"]["origin_zone"] == "Golf 2"


def test_scenario_6_7_8_9_12_field_observations_stale_expiration_and_admin_analytics(client: TestClient):
    admin_h = _auth(client, "admin@dalalink.ao")
    field_h = _auth(client, "campo@dalalink.ao")
    pass_h = _auth(client, "passageiro@dalalink.ao")

    # 8. Stale detection on seeded Talatona -> Maianga (25 min old > 15 min recent threshold)
    stale_corridor = client.get("/api/v1/info/corridor?origin_zone=Talatona&destination_zone=Maianga").json()
    assert stale_corridor["has_sufficient_data"] is True
    assert stale_corridor["freshness_status"] == "STALE"

    # Expiration: create an intention, force expires_at in the past, confirm it stops counting
    dec = client.post(
        "/api/v1/info/intentions",
        headers=pass_h,
        json={"origin_zone": "Viana", "destination_zone": "Kilamba", "passenger_count": 3},
    )
    assert dec.status_code == 201
    int_id = dec.json()["intention"]["id"]
    assert client.get("/api/v1/info/corridor?origin_zone=Viana&destination_zone=Kilamba").json()["estimated_demand"] == 3

    db = client._session_factory()  # type: ignore[attr-defined]
    it = db.get(TransportIntention, int_id)
    it.expires_at = now_luanda() - timedelta(minutes=5)
    db.commit()
    db.close()

    after_exp = client.get("/api/v1/info/corridor?origin_zone=Viana&destination_zone=Kilamba").json()
    assert after_exp["has_sufficient_data"] is False
    assert after_exp["status_message"] == "Informação insuficiente para esta via."

    # 6. Field collector records PENDING observation (15 taxis, 32 passengers on Gamek -> Maianga)
    obs = client.post(
        "/api/v1/info/observations/field",
        headers=field_h,
        json={
            "origin_zone": "Gamek",
            "destination_zone": "Maianga",
            "observed_taxis_count": 15,
            "observed_passengers_count": 32,
            "estimated_wait_min": 12,
            "road_condition": "MODERATE_TRAFFIC",
            "notes": "Recolha presencial 17h30 no Gamek",
        },
    )
    assert obs.status_code == 201, obs.text
    assert obs.json()["validation_status"] == "PENDING"
    d_obs_id = obs.json()["demand_observation_id"]
    s_obs_id = obs.json()["supply_observation_id"]

    # Admin validates both observations
    assert client.post(
        f"/api/v1/info/admin/validations/DEMAND_OBS/{d_obs_id}",
        headers=admin_h,
        json={"decision": "VALIDATED", "reason": "Confirmado em campo"},
    ).status_code == 200
    assert client.post(
        f"/api/v1/info/admin/validations/SUPPLY_OBS/{s_obs_id}",
        headers=admin_h,
        json={"decision": "VALIDATED", "reason": "Confirmado em campo"},
    ).status_code == 200

    # 7. Corridor now reflects latest validated observation (32 confirmed field passengers, 15 observed taxis)
    updated = client.get("/api/v1/info/corridor?origin_zone=Gamek&destination_zone=Maianga").json()
    assert updated["confirmed_demand"] == 32
    assert updated["observed_supply"] == 15
    assert updated["demand_level"] == "PROCURA_ELEVADA"
    assert updated["supply_level"] == "OFERTA_ELEVADA"

    # 12. Admin dashboard & historical analytics + configurable thresholds
    dash = client.get("/api/v1/info/admin/dashboard", headers=admin_h).json()
    assert dash["kpis"]["validated_data_pct"] > 0
    assert len(dash["analytics"]["demand_by_municipality"]) >= 1
    assert len(dash["analytics"]["demand_by_hour"]) == 24

    cfg = client.put(
        "/api/v1/info/admin/config",
        headers=admin_h,
        json={"updates": {"recent_minutes": "20", "demand_high_min": "18"}},
    )
    assert cfg.status_code == 200
    assert cfg.json()["thresholds"]["recent_minutes"] == 20.0

    # Privacy check: map payload contains aggregated stop counts ONLY, never individual passenger coordinates
    map_res = client.get("/api/v1/info/map").json()
    assert "stops" in map_res
    assert "individual_passengers" not in map_res
