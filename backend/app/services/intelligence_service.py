from collections import Counter, defaultdict
from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import LUANDA_TZ, now_luanda
from app.models.fleet import DriverAvailability
from app.models.identity import Driver
from app.models.mobility import TransportRequest, Trip
from app.services.geo_service import LUANDA_ZONES

MIN_TRIPS_FOR_ML_FORECAST = 500


def _to_luanda_hour(dt: Optional[datetime]) -> int:
    if not dt:
        return now_luanda().hour
    if dt.tzinfo is None:
        return dt.hour
    return dt.astimezone(LUANDA_TZ).hour


def compute_zone_demand_pressure(
    db: Session,
    requests_override: Optional[list[TransportRequest]] = None,
) -> list[dict]:
    """
    Statistical demand vs supply pressure indicators by Luanda zone.
    Uses real operational data (no artificial ML predictions without sufficient data).
    """
    all_requests = (
        requests_override
        if requests_override is not None
        else db.scalars(select(TransportRequest)).all()
    )
    active_requests = [r for r in all_requests if r.status in {"PENDING", "OFFERED"}]

    available_drivers = db.execute(
        select(DriverAvailability)
        .join(Driver, Driver.id == DriverAvailability.driver_id)
        .where(
            Driver.verification_status == "APPROVED",
            DriverAvailability.status == "AVAILABLE",
        )
    ).scalars().all()

    busy_drivers = db.execute(
        select(DriverAvailability)
        .join(Driver, Driver.id == DriverAvailability.driver_id)
        .where(
            Driver.verification_status == "APPROVED",
            DriverAvailability.status == "BUSY",
        )
    ).scalars().all()

    results: list[dict] = []
    for z in LUANDA_ZONES:
        zone_name = z["zone"]
        z_lower = zone_name.lower()
        pending_count = sum(1 for r in active_requests if r.pickup_zone.lower() == z_lower)
        zone_all = [r for r in all_requests if r.pickup_zone.lower() == z_lower]
        total_historical = len(zone_all)
        cancelled_count = sum(1 for r in zone_all if r.status in {"CANCELLED", "EXPIRED"})
        avail_count = sum(1 for d in available_drivers if (d.current_zone or "").lower() == z_lower)
        busy_count = sum(1 for d in busy_drivers if (d.current_zone or "").lower() == z_lower)

        ratio = round(pending_count / max(1, avail_count), 2)
        unmet_rate_pct = (
            round((cancelled_count / total_historical) * 100.0, 1) if total_historical > 0 else 0.0
        )

        # Congestion & wait-time heuristic derived strictly from active load + Luanda peak hours
        cur_hour = now_luanda().hour
        peak_multiplier = 1.35 if cur_hour in {7, 8, 9, 16, 17, 18, 19} else 1.0
        congestion_index = round(min(3.0, (1.0 + pending_count * 0.25 + busy_count * 0.15) * peak_multiplier), 2)
        avg_wait_min = max(3, int(round((5 + pending_count * 3 - min(avail_count, 3) * 1.2) * peak_multiplier)))

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
                "unmet_rate_pct": unmet_rate_pct,
                "available_vehicles": avail_count,
                "busy_vehicles": busy_count,
                "pressure_ratio": ratio,
                "pressure_level": pressure,
                "congestion_index": congestion_index,
                "estimated_wait_min": avg_wait_min,
                "recommendation": recommendation,
            }
        )

    pressure_rank = {"ELEVADA": 0, "MODERADA": 1, "BAIXA": 2}
    results.sort(key=lambda item: (pressure_rank[item["pressure_level"]], -item["active_requests"]))
    return results


def compute_mobility_intelligence(
    db: Session,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    zone: Optional[str] = None,
) -> dict:
    """
    Phase 3 Urban Mobility Intelligence Engine:
      - Real zone demand/supply heatmap & congestion indicators
      - Hourly peak distribution (Africa/Luanda)
      - Top Origin -> Destination corridors
      - Wait-time & unmet demand statistics
      - Actionable driver repositioning recommendations (surplus -> deficit zones)
      - Transparent statistical readiness indicator (no fake ML predictions)
    """
    req_stmt = select(TransportRequest)
    if zone:
        req_stmt = req_stmt.where(TransportRequest.pickup_zone == zone)
    all_reqs = db.scalars(req_stmt).all()

    if date_from:
        df_cmp = date_from.replace(tzinfo=None)
        all_reqs = [r for r in all_reqs if r.created_at and r.created_at.replace(tzinfo=None) >= df_cmp]
    if date_to:
        dt_cmp = date_to.replace(tzinfo=None)
        all_reqs = [r for r in all_reqs if r.created_at and r.created_at.replace(tzinfo=None) <= dt_cmp]

    trips = db.scalars(select(Trip)).all()
    zones = compute_zone_demand_pressure(db, requests_override=all_reqs)

    # Hourly demand curve (0..23 Africa/Luanda)
    hourly_counts: Counter[int] = Counter()
    for r in all_reqs:
        hourly_counts[_to_luanda_hour(r.created_at)] += 1

    hourly_distribution = [
        {"hour": f"{h:02d}h", "requests": hourly_counts.get(h, 0)} for h in range(24)
    ]
    peak_hour_entry = max(hourly_distribution, key=lambda x: x["requests"], default={"hour": "17h", "requests": 0})

    # Top Origin -> Destination corridors
    corridors_map: dict[tuple[str, str], dict] = defaultdict(
        lambda: {"count": 0, "passengers": 0, "total_fare_aoa": 0.0}
    )
    for r in all_reqs:
        key = (r.pickup_zone, r.dropoff_zone)
        corridors_map[key]["count"] += 1
        corridors_map[key]["passengers"] += r.passenger_count
        corridors_map[key]["total_fare_aoa"] += float(r.estimated_total_fare_aoa)

    top_corridors = [
        {
            "origin": k[0],
            "destination": k[1],
            "requests_count": v["count"],
            "total_passengers": v["passengers"],
            "avg_fare_aoa": round(v["total_fare_aoa"] / max(1, v["count"]), 2),
            "total_volume_aoa": round(v["total_fare_aoa"], 2),
        }
        for k, v in corridors_map.items()
    ]
    top_corridors.sort(key=lambda c: (-c["requests_count"], -c["total_volume_aoa"]))

    # Real average acceptance wait time (seconds -> minutes) from accepted trips
    wait_deltas_min: list[float] = []
    for t in trips:
        if t.accepted_at and t.transport_request and t.transport_request.created_at:
            a = t.accepted_at.replace(tzinfo=None)
            c = t.transport_request.created_at.replace(tzinfo=None)
            diff_min = max(0.2, (a - c).total_seconds() / 60.0)
            wait_deltas_min.append(diff_min)

    avg_matching_wait_min = (
        round(sum(wait_deltas_min) / len(wait_deltas_min), 1)
        if wait_deltas_min
        else round(sum(z["estimated_wait_min"] for z in zones) / max(1, len(zones)), 1)
    )

    total_reqs = len(all_reqs)
    cancelled_reqs = sum(1 for r in all_reqs if r.status in {"CANCELLED", "EXPIRED"})
    unmet_rate_pct = round((cancelled_reqs / total_reqs) * 100.0, 1) if total_reqs > 0 else 0.0

    # Operational driver repositioning recommendations: surplus zones -> deficit zones
    deficit_zones = [z for z in zones if z["pressure_level"] in {"ELEVADA", "MODERADA"}]
    surplus_zones = [z for z in zones if z["pressure_level"] == "BAIXA" and z["available_vehicles"] > 0]
    repositioning: list[dict] = []
    for dz in deficit_zones[:4]:
        source = surplus_zones[0]["zone"] if surplus_zones else "Zonas adjacentes"
        repositioning.append(
            {
                "from_zone": source,
                "to_zone": dz["zone"],
                "priority": dz["pressure_level"],
                "reason": (
                    f"{dz['zone']} tem {dz['active_requests']} pedido(s) ativo(s) para "
                    f"{dz['available_vehicles']} veículo(s) livre(s)."
                ),
            }
        )

    sample_size = len(trips)
    return {
        "summary": {
            "total_requests_analyzed": total_reqs,
            "total_trips_completed": sum(1 for t in trips if t.status == "COMPLETED"),
            "avg_wait_time_min": avg_matching_wait_min,
            "unmet_demand_rate_pct": unmet_rate_pct,
            "peak_hour_luanda": peak_hour_entry["hour"],
            "high_pressure_zones": sum(1 for z in zones if z["pressure_level"] == "ELEVADA"),
        },
        "forecast_model_status": {
            "mode": "STATISTICAL_RULES_V1" if sample_size < MIN_TRIPS_FOR_ML_FORECAST else "PREDICTIVE_READY",
            "sample_trips": sample_size,
            "required_trips_for_ml": MIN_TRIPS_FOR_ML_FORECAST,
            "note": (
                f"Modo estatístico transparente ativo ({sample_size}/{MIN_TRIPS_FOR_ML_FORECAST} viagens). "
                "Modelos preditivos ML só serão ativados com volume histórico real suficiente."
            ),
        },
        "zones": zones,
        "hourly_distribution": hourly_distribution,
        "top_corridors": top_corridors[:8],
        "repositioning_recommendations": repositioning,
    }
