from datetime import timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.core.config import now_luanda
from app.db.seed import seed_database
from app.db.session import Base, get_db
from app.main import app
from app.models import *  # noqa: F401, F403
from app.models.mobility import TransportRequest


@pytest.fixture()
def client(tmp_path):
    db_file = tmp_path / "test_dalalink.db"
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
        c._session_factory = TestingSessionLocal  # type: ignore[attr-defined]
        yield c
    app.dependency_overrides.clear()
    engine.dispose()


def _auth_header(client: TestClient, email: str, password: str = "dalalink123") -> dict:
    resp = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200, resp.text
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_all_25_tables_registered():
    expected_tables = {
        "users",
        "passengers",
        "drivers",
        "vehicles",
        "vehicle_owners",
        "companies",
        "employees",
        "transport_cards",
        "card_transactions",
        "wallets",
        "transport_requests",
        "group_requests",
        "group_passengers",
        "trips",
        "trip_passengers",
        "routes",
        "stops",
        "vehicle_locations",
        "driver_availability",
        "tariffs",
        "commissions",
        "subscriptions",
        "notifications",
        "ratings",
        "audit_logs",
    }
    assert expected_tables.issubset(set(Base.metadata.tables.keys()))


def test_full_e2e_gamek_to_aeroporto_with_atomic_qr_and_anti_duplication(client: TestClient):
    passenger_h = _auth_header(client, "passageiro@dalalink.ao")
    driver_h = _auth_header(client, "motorista@dalalink.ao")
    admin_h = _auth_header(client, "admin@dalalink.ao")

    # 1. Verify initial wallet balance = 10.000 AOA and card MOB-000001
    wallet_before = client.get("/api/v1/mobility/wallet", headers=passenger_h).json()
    assert wallet_before["balance_aoa"] == 10000.0
    card = wallet_before["cards"][0]
    assert card["card_code"] == "MOB-000001"
    qr_token = card["qr_token"]

    # 2. Request quote & create request: Gamek -> Aeroporto
    quote = client.post(
        "/api/v1/mobility/quote",
        json={
            "pickup_lat": -8.8842,
            "pickup_lng": 13.2148,
            "dropoff_lat": -8.8584,
            "dropoff_lng": 13.2312,
            "passenger_count": 1,
        },
    ).json()
    assert quote["fare_per_passenger_aoa"] == 1000.0

    req_resp = client.post(
        "/api/v1/mobility/requests",
        headers=passenger_h,
        json={
            "pickup_label": "Paragem Principal do Gamek",
            "pickup_zone": "Gamek",
            "pickup_lat": -8.8842,
            "pickup_lng": 13.2148,
            "dropoff_label": "Aeroporto Internacional 4 de Fevereiro",
            "dropoff_zone": "Aeroporto",
            "dropoff_lat": -8.8584,
            "dropoff_lng": 13.2312,
            "passenger_count": 1,
            "request_type": "INDIVIDUAL",
        },
    )
    assert req_resp.status_code == 201, req_resp.text
    req_data = req_resp.json()
    assert req_data["matched_driver_found"] is True
    req_id = req_data["request"]["id"]

    # 3. Driver (Hyundai i10 near Gamek) sees the offer and accepts
    drv_dash = client.get("/api/v1/driver/dashboard", headers=driver_h).json()
    assert drv_dash["pending_offer"]["id"] == req_id

    accept_resp = client.post(f"/api/v1/driver/offers/{req_id}/accept", headers=driver_h)
    assert accept_resp.status_code == 200, accept_resp.text
    trip = accept_resp.json()
    trip_id = trip["id"]
    assert trip["vehicle"]["make"] == "Hyundai"
    assert trip["vehicle"]["model"] == "i10"
    assert trip["status"] == "DRIVER_EN_ROUTE"

    # 4. Driver advances GPS and marks arrived
    step = client.post(f"/api/v1/driver/trips/{trip_id}/simulate-step", headers=driver_h)
    assert step.status_code == 200
    arrived = client.post(f"/api/v1/driver/trips/{trip_id}/arrive", headers=driver_h)
    assert arrived.status_code == 200
    assert arrived.json()["status"] == "DRIVER_ARRIVED"

    # 5. Cannot start trip before QR boarding validation
    premature_start = client.post(f"/api/v1/driver/trips/{trip_id}/start", headers=driver_h)
    assert premature_start.status_code == 400

    # 6. Validate QR token atomically (10.000 -> 9.000 AOA)
    val_resp = client.post(
        f"/api/v1/driver/trips/{trip_id}/validate-card",
        headers=driver_h,
        json={"card_identifier": qr_token, "idempotency_key": "SCAN-TEST-001"},
    )
    assert val_resp.status_code == 200, val_resp.text
    val = val_resp.json()["validation"]
    assert val["authorized"] is True
    assert val["amount_debited_aoa"] == 1000.0
    assert val["balance_before_aoa"] == 10000.0
    assert val["balance_after_aoa"] == 9000.0

    # 7. Duplicate debit protection (same idempotency key -> idempotent no-op)
    dup_same = client.post(
        f"/api/v1/driver/trips/{trip_id}/validate-card",
        headers=driver_h,
        json={"card_identifier": qr_token, "idempotency_key": "SCAN-TEST-001"},
    )
    assert dup_same.status_code == 200
    assert dup_same.json()["validation"]["duplicate_prevented"] is True

    # Different idempotency key for same trip + card -> 409 Conflict
    dup_diff = client.post(
        f"/api/v1/driver/trips/{trip_id}/validate-card",
        headers=driver_h,
        json={"card_identifier": qr_token, "idempotency_key": "SCAN-TEST-002"},
    )
    assert dup_diff.status_code == 409

    # Confirm server wallet balance strictly 9.000 AOA
    wallet_after = client.get("/api/v1/mobility/wallet", headers=passenger_h).json()
    assert wallet_after["balance_aoa"] == 9000.0

    # 8. Start and complete trip
    started = client.post(f"/api/v1/driver/trips/{trip_id}/start", headers=driver_h)
    assert started.status_code == 200
    assert started.json()["status"] == "IN_PROGRESS"

    completed = client.post(f"/api/v1/driver/trips/{trip_id}/complete", headers=driver_h)
    assert completed.status_code == 200
    comp_data = completed.json()
    assert comp_data["status"] == "COMPLETED"
    assert comp_data["commission"]["gross_fare_aoa"] == 1000.0
    assert comp_data["commission"]["platform_fee_aoa"] == 150.0
    assert comp_data["commission"]["driver_net_aoa"] == 850.0

    # 9. Passenger rates trip
    rate = client.post(
        f"/api/v1/mobility/trips/{trip_id}/rate",
        headers=passenger_h,
        json={"score": 5, "comment": "Excelente viagem até ao Aeroporto!"},
    )
    assert rate.status_code == 200

    # 10. Admin overview reflects completed trip, revenue, and commission
    admin_ov = client.get("/api/v1/admin/overview", headers=admin_h).json()
    assert admin_ov["kpis"]["completed_trips"] == 1
    assert admin_ov["kpis"]["gross_revenue_aoa"] == 1000.0
    assert admin_ov["kpis"]["platform_commissions_aoa"] == 150.0


def test_card_security_insufficient_blocked_tampered_and_refund(client: TestClient):
    passenger_h = _auth_header(client, "passageiro@dalalink.ao")
    driver_h = _auth_header(client, "motorista@dalalink.ao")
    admin_h = _auth_header(client, "admin@dalalink.ao")

    # Create and accept a trip
    req_id = client.post(
        "/api/v1/mobility/requests",
        headers=passenger_h,
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
    trip_id = client.post(f"/api/v1/driver/offers/{req_id}/accept", headers=driver_h).json()["id"]

    # Insufficient balance card (MOB-000003 has 400 AOA < 1000 AOA)
    low_resp = client.post(
        f"/api/v1/driver/trips/{trip_id}/validate-card",
        headers=driver_h,
        json={"card_identifier": "MOB-000003"},
    )
    assert low_resp.status_code == 402

    # Blocked card (MOB-000004 is BLOCKED)
    blocked_resp = client.post(
        f"/api/v1/driver/trips/{trip_id}/validate-card",
        headers=driver_h,
        json={"card_identifier": "MOB-000004"},
    )
    assert blocked_resp.status_code == 403

    # Tampered QR signature
    tampered_resp = client.post(
        f"/api/v1/driver/trips/{trip_id}/validate-card",
        headers=driver_h,
        json={"card_identifier": "DALALINK:MOB-000001:AAAA:BADSIGNATURE"},
    )
    assert tampered_resp.status_code == 404

    # Valid debit then admin refund
    ok = client.post(
        f"/api/v1/driver/trips/{trip_id}/validate-card",
        headers=driver_h,
        json={"card_identifier": "MOB-000001"},
    )
    assert ok.status_code == 200
    tx_id = ok.json()["validation"]["transaction_id"]

    refund = client.post(
        f"/api/v1/admin/transactions/{tx_id}/refund",
        headers=admin_h,
        json={"reason": "Viagem cancelada por avaria mecânica"},
    )
    assert refund.status_code == 200
    assert refund.json()["balance_after_aoa"] == 10000.0

    # Duplicate refund blocked
    dup_refund = client.post(
        f"/api/v1/admin/transactions/{tx_id}/refund",
        headers=admin_h,
        json={"reason": "Tentativa duplicada"},
    )
    assert dup_refund.status_code == 409


def test_group_request_with_individual_card_validations(client: TestClient):
    passenger_h = _auth_header(client, "passageiro@dalalink.ao")
    driver_h = _auth_header(client, "motorista@dalalink.ao")

    req_resp = client.post(
        "/api/v1/mobility/requests",
        headers=passenger_h,
        json={
            "pickup_label": "Gamek",
            "pickup_zone": "Gamek",
            "pickup_lat": -8.8842,
            "pickup_lng": 13.2148,
            "dropoff_label": "Aeroporto",
            "dropoff_zone": "Aeroporto",
            "dropoff_lat": -8.8584,
            "dropoff_lng": 13.2312,
            "passenger_count": 2,
            "request_type": "GROUP",
            "companion_card_codes": ["MOB-000002"],
        },
    )
    assert req_resp.status_code == 201, req_resp.text
    req_data = req_resp.json()["request"]
    assert req_data["request_type"] == "GROUP"
    assert req_data["passenger_count"] == 2
    assert len(req_data["group_members"]) == 2
    assert req_data["estimated_total_fare_aoa"] == 2000.0

    trip_id = client.post(f"/api/v1/driver/offers/{req_data['id']}/accept", headers=driver_h).json()["id"]

    # Validate each passenger's card independently
    v1 = client.post(
        f"/api/v1/driver/trips/{trip_id}/validate-card",
        headers=driver_h,
        json={"card_identifier": "MOB-000001"},
    )
    v2 = client.post(
        f"/api/v1/driver/trips/{trip_id}/validate-card",
        headers=driver_h,
        json={"card_identifier": "MOB-000002"},
    )
    assert v1.status_code == 200
    assert v2.status_code == 200
    assert v2.json()["trip"]["boarded_count"] == 2
    assert v2.json()["trip"]["paid_total_aoa"] == 2000.0


def test_matching_rejection_and_timeout_redistribution(client: TestClient):
    passenger_h = _auth_header(client, "passageiro@dalalink.ao")
    driver1_h = _auth_header(client, "motorista@dalalink.ao")
    driver2_h = _auth_header(client, "motorista2@dalalink.ao")
    admin_h = _auth_header(client, "admin@dalalink.ao")

    req_id = client.post(
        "/api/v1/mobility/requests",
        headers=passenger_h,
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

    # Driver 1 rejects -> automatically redistributed to Driver 2 (Toyota HiAce)
    rej = client.post(f"/api/v1/driver/offers/{req_id}/reject", headers=driver1_h)
    assert rej.status_code == 200
    assert rej.json()["redistributed_to_driver_id"] is not None

    d2_dash = client.get("/api/v1/driver/dashboard", headers=driver2_h).json()
    assert d2_dash["pending_offer"]["id"] == req_id

    # Force offer expiration and verify timeout redistribution works
    db = client._session_factory()  # type: ignore[attr-defined]
    req_obj = db.get(TransportRequest, req_id)
    req_obj.offer_expires_at = now_luanda() - timedelta(seconds=10)
    db.commit()
    db.close()

    redist = client.post("/api/v1/admin/matching/redistribute-expired", headers=admin_h)
    assert redist.status_code == 200
    assert redist.json()["redistributed_count"] == 1


def test_driver_verification_guard_and_corporate_dispatch(client: TestClient):
    driver3_h = _auth_header(client, "motorista3@dalalink.ao")
    admin_h = _auth_header(client, "admin@dalalink.ao")
    corp_h = _auth_header(client, "empresa@dalalink.ao")

    # Unverified driver cannot go AVAILABLE
    blocked_go_online = client.put(
        "/api/v1/driver/status",
        headers=driver3_h,
        json={"status": "AVAILABLE"},
    )
    assert blocked_go_online.status_code == 403

    # Admin approves driver 3
    drivers = client.get("/api/v1/admin/drivers", headers=admin_h).json()
    pending_drv = next(d for d in drivers if d["email"] == "motorista3@dalalink.ao")
    approve = client.post(
        f"/api/v1/admin/drivers/{pending_drv['id']}/verify",
        headers=admin_h,
        json={"verification_status": "APPROVED", "notes": "Documentos verificados."},
    )
    assert approve.status_code == 200

    # Now driver 3 can go AVAILABLE
    now_online = client.put(
        "/api/v1/driver/status",
        headers=driver3_h,
        json={"status": "AVAILABLE", "zone_name": "Talatona"},
    )
    assert now_online.status_code == 200
    assert now_online.json()["status"] == "AVAILABLE"

    # Corporate shift batch dispatch at 17:00
    corp_dispatch = client.post(
        "/api/v1/corporate/dispatch-shift",
        headers=corp_h,
        json={"origin_zone": "Talatona", "shift_time": "17:00"},
    )
    assert corp_dispatch.status_code == 200, corp_dispatch.text
    assert corp_dispatch.json()["dispatched_groups"] >= 1
    assert corp_dispatch.json()["total_employees_scheduled"] == 5
