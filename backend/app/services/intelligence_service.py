from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.fleet import DriverAvailability
from app.models.identity import Driver
from app.models.mobility import TransportRequest
from app.services.geo_service import LUANDA_ZONES


def compute_zone_demand_pressure(db: Session) -> list[dict]:
    """
    Statistical demand vs supply pressure indicators by Luanda zone.
    Uses real operational data (no artificial ML predictions without sufficient data).
    """
    active_requests = db.scalars(
        select(TransportRequest).where(TransportRequest.status.in_(["PENDING", "OFFERED"]))
    ).all()

    all_requests = db.scalars(select(TransportRequest)).all()

    available_drivers = db.execute(
        select(DriverAvailability)
        .join(Driver, Driver.id == DriverAvailability.driver_id)
        .where(
            Driver.verification_status == "APPROVED",
            DriverAvailability.status == "AVAILABLE",
        )
    ).scalars().all()

    results: list[dict] = []
    for z in LUANDA_ZONES:
        zone_name = z["zone"]
        pending_count = sum(1 for r in active_requests if r.pickup_zone.lower() == zone_name.lower())
        total_historical = sum(1 for r in all_requests if r.pickup_zone.lower() == zone_name.lower())
        cancelled_count = sum(
            1
            for r in all_requests
            if r.pickup_zone.lower() == zone_name.lower() and r.status in {"CANCELLED", "EXPIRED"}
        )
        avail_count = sum(
            1 for d in available_drivers if (d.current_zone or "").lower() == zone_name.lower()
        )

        # Pressure ratio = demand / max(1, available)
        ratio = round(pending_count / max(1, avail_count), 2)
        if pending_count >= 3 and (avail_count == 0 or ratio >= 2.0):
            pressure = "ELEVADA"
            recommendation = f"Deslocar motoristas livres para {zone_name} — alta procura ativa."
        elif pending_count >= 1 and (avail_count <= pending_count):
            pressure = "MODERADA"
            recommendation = f"Monitorizar {zone_name}; equilíbrio apertado entre pedidos e veículos."
        else:
            pressure = "BAIXA"
            recommendation = f"Cobertura estável em {zone_name}."

        results.append(
            {
                "zone": zone_name,
                "latitude": z["lat"],
                "longitude": z["lng"],
                "active_requests": pending_count,
                "historical_requests": total_historical,
                "unmet_or_cancelled": cancelled_count,
                "available_vehicles": avail_count,
                "pressure_ratio": ratio,
                "pressure_level": pressure,
                "recommendation": recommendation,
            }
        )

    pressure_rank = {"ELEVADA": 0, "MODERADA": 1, "BAIXA": 2}
    results.sort(key=lambda item: (pressure_rank[item["pressure_level"]], -item["active_requests"]))
    return results
