import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.db.seed import seed_database
from app.db.session import Base, get_db
from app.main import app
from app.models import *  # noqa: F401, F403


@pytest.fixture()
def client(tmp_path):
    db_file = tmp_path / "test_dalalink_phases.db"
    engine = create_engine(
        f"sqlite:///{db_file}",
        connect_args={"check_same_thread": False},
        future=True,
    )

    @event.listens_for(engine, "connect")
    def _fk_pragma(dbapi_conn, _rec):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON;")
        cur.close()

    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    Base.metadata.create_all(bind=engine)

    seed_db = TestingSessionLocal()
    seed_database(seed_db)
    seed_db.close()

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
    engine.dispose()


def _auth(client: TestClient, email: str) -> dict:
    r = client.post("/api/v1/auth/login", json={"email": email, "password": "dalalink123"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_phase2_corporate_recurring_capacity_batches_and_cost_reports(client: TestClient):
    corp_h = _auth(client, "empresa@dalalink.ao")

    dash = client.get("/api/v1/corporate/dashboard", headers=corp_h).json()
    assert len(dash["recurring_bookings"]) >= 1
    route_id = dash["routes"][0]["id"]

    # Add 3 more employees going to Aeroporto at 17:00 so Aeroporto has 4 total employees
    for i in range(3):
        add = client.post(
            "/api/v1/corporate/employees",
            headers=corp_h,
            json={
                "full_name": f"Colaborador Aero {i+1}",
                "email": f"aero{i+1}@atlantico.ao",
                "department": "Engenharia",
                "pickup_zone": "Talatona",
                "dropoff_zone": "Aeroporto",
                "shift_time": "17:00",
            },
        )
        assert add.status_code == 201

    # Dispatch only Aeroporto with max_vehicle_capacity=2 -> must split 4 employees into 2 batches!
    disp = client.post(
        "/api/v1/corporate/dispatch-shift",
        headers=corp_h,
        json={
            "origin_zone": "Talatona",
            "destination_zone": "Aeroporto",
            "shift_time": "17:00",
            "max_vehicle_capacity": 2,
        },
    )
    assert disp.status_code == 200, disp.text
    assert disp.json()["total_employees_scheduled"] == 4
    assert disp.json()["dispatched_groups"] == 2

    # Create & trigger a new recurring booking
    rec = client.post(
        "/api/v1/corporate/recurring",
        headers=corp_h,
        json={
            "route_id": route_id,
            "days_of_week": "SEG,QUA,SEX",
            "shift_time": "17:00",
            "vehicle_capacity_hint": 12,
        },
    )
    assert rec.status_code == 201
    trig = client.post(f"/api/v1/corporate/recurring/{rec.json()['id']}/trigger", headers=corp_h)
    assert trig.status_code == 200

    # Cost report + CSV export
    report = client.get("/api/v1/corporate/reports/costs", headers=corp_h).json()
    assert report["total_requests"] >= 2
    assert len(report["by_department"]) >= 1
    assert len(report["by_route"]) >= 1

    csv_resp = client.get("/api/v1/corporate/reports/costs.csv", headers=corp_h)
    assert csv_resp.status_code == 200
    assert "text/csv" in csv_resp.headers["content-type"]
    assert "Talatona" in csv_resp.text


def test_phase3_mobility_intelligence_corridors_and_readiness(client: TestClient):
    pass_h = _auth(client, "passageiro@dalalink.ao")
    admin_h = _auth(client, "admin@dalalink.ao")

    # Generate real demand from Gamek -> Aeroporto
    client.post(
        "/api/v1/mobility/requests",
        headers=pass_h,
        json={
            "pickup_label": "Gamek",
            "pickup_zone": "Gamek",
            "pickup_lat": -8.8842,
            "pickup_lng": 13.2148,
            "dropoff_label": "Aeroporto",
            "dropoff_zone": "Aeroporto",
            "dropoff_lat": -8.8584,
            "dropoff_lng": 13.2312,
            "passenger_count": 1,
        },
    )

    intel = client.get("/api/v1/admin/intelligence", headers=admin_h)
    assert intel.status_code == 200, intel.text
    data = intel.json()
    assert data["forecast_model_status"]["mode"] == "STATISTICAL_RULES_V1"
    assert len(data["hourly_distribution"]) == 24
    assert len(data["top_corridors"]) >= 1
    assert data["top_corridors"][0]["origin"] == "Gamek"
    assert data["top_corridors"][0]["destination"] == "Aeroporto"
    assert len(data["zones"]) == 10


def test_phase4_nfc_tap_validation_fleet_owner_and_integrations(client: TestClient):
    pass_h = _auth(client, "passageiro@dalalink.ao")
    drv_h = _auth(client, "motorista@dalalink.ao")
    owner_h = _auth(client, "frota@dalalink.ao")
    admin_h = _auth(client, "admin@dalalink.ao")

    # 1. Admin binds NFC UID to MOB-000002
    nfc_bind = client.put(
        "/api/v1/admin/cards/MOB-000002/nfc",
        headers=admin_h,
        json={"nfc_uid": "NFC-AO-778899", "card_technology": "QR+NFC"},
    )
    assert nfc_bind.status_code == 200
    assert nfc_bind.json()["nfc_uid"] == "NFC-AO-778899"

    # 2. Request & accept trip, then validate boarding via NFC tap!
    req_id = client.post(
        "/api/v1/mobility/requests",
        headers=pass_h,
        json={
            "pickup_label": "Gamek",
            "pickup_zone": "Gamek",
            "pickup_lat": -8.8842,
            "pickup_lng": 13.2148,
            "dropoff_label": "Aeroporto",
            "dropoff_zone": "Aeroporto",
            "dropoff_lat": -8.8584,
            "dropoff_lng": 13.2312,
            "passenger_count": 1,
        },
    ).json()["request"]["id"]
    trip_id = client.post(f"/api/v1/driver/offers/{req_id}/accept", headers=drv_h).json()["id"]

    nfc_tap = client.post(
        f"/api/v1/driver/trips/{trip_id}/validate-card",
        headers=drv_h,
        json={"card_identifier": "NFC:NFC-AO-000001"},
    )
    assert nfc_tap.status_code == 200, nfc_tap.text
    assert nfc_tap.json()["validation"]["card_code"] == "MOB-000001"
    assert nfc_tap.json()["validation"]["balance_after_aoa"] == 9000.0

    # Complete trip so owner sees vehicle profitability!
    client.post(f"/api/v1/driver/trips/{trip_id}/start", headers=drv_h)
    client.post(f"/api/v1/driver/trips/{trip_id}/complete", headers=drv_h)

    # 3. Fleet Owner dashboard shows Hyundai i10 revenue + allows registering new vehicle
    owner_dash = client.get("/api/v1/owner/dashboard", headers=owner_h).json()
    assert owner_dash["summary"]["total_vehicles"] >= 3
    assert owner_dash["summary"]["gross_revenue_aoa"] == 1000.0
    assert owner_dash["summary"]["net_revenue_aoa"] == 850.0

    new_veh = client.post(
        "/api/v1/owner/vehicles",
        headers=owner_h,
        json={
            "make": "Suzuki",
            "model": "S-Presso",
            "year": 2024,
            "color": "Prata",
            "license_plate": "LD-99-11-ZZ",
            "capacity": 4,
        },
    )
    assert new_veh.status_code == 201

    # 4. Admin integrations registry & new card issuance
    integ = client.get("/api/v1/admin/integrations", headers=admin_h).json()
    codes = {i["provider_code"] for i in integ["integrations"]}
    assert "DALALINK_CORE_LEDGER" in codes
    assert "EMIS_MULTICAIXA_EXPRESS" in codes

    passengers = client.get("/api/v1/admin/passengers", headers=admin_h).json()
    issued = client.post(
        "/api/v1/admin/cards/issue",
        headers=admin_h,
        json={"passenger_id": passengers[0]["id"], "initial_balance_aoa": 2500, "nfc_uid": "NFC-NEW-001"},
    )
    assert issued.status_code == 201
    assert issued.json()["nfc_uid"] == "NFC-NEW-001"
