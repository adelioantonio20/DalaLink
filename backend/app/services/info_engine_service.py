from collections import Counter, defaultdict
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.core.config import LUANDA_TZ, now_luanda
from app.models.intelligence import (
    DataValidation,
    DemandObservation,
    DriverReport,
    MobilityIndicator,
    Municipality,
    Neighborhood,
    PlatformConfig,
    SupplyObservation,
    TaxiStop,
    TransportIntention,
    TransportRoute,
    TransportZone,
)
from app.services.geo_service import haversine_km

DEFAULT_THRESHOLDS: dict[str, tuple[str, str]] = {
    "recent_minutes": ("15", "Minutos em que um registo é considerado recente."),
    "stale_minutes": ("45", "Minutos após os quais um registo é sinalizado como desactualizado antes de expirar."),
    "intention_ttl_minutes": ("60", "Validade máxima (min) de uma intenção de viagem de passageiro."),
    "driver_report_ttl_minutes": ("60", "Validade máxima (min) de uma declaração de disponibilidade de motorista."),
    "observation_ttl_minutes": ("45", "Validade máxima (min) de uma observação presencial de campo."),
    "demand_moderate_min": ("5", "Mínimo de passageiros estimados para classificar Procura Moderada."),
    "demand_high_min": ("15", "Mínimo de passageiros estimados para classificar Procura Elevada."),
    "supply_moderate_min": ("3", "Mínimo de táxis estimados para classificar Oferta Moderada."),
    "supply_high_min": ("8", "Mínimo de táxis estimados para classificar Oferta Elevada."),
    "imbalance_ratio_threshold": ("3.0", "Rácio passageiros/táxi a partir do qual é sinalizado desequilíbrio."),
}


def get_thresholds(db: Session) -> dict[str, float]:
    rows = db.scalars(select(PlatformConfig)).all()
    raw = {k: v[0] for k, v in DEFAULT_THRESHOLDS.items()}
    for r in rows:
        raw[r.key] = r.value
    out: dict[str, float] = {}
    for k, v in raw.items():
        try:
            out[k] = float(v)
        except ValueError:
            out[k] = float(DEFAULT_THRESHOLDS[k][0])
    return out


def _as_naive_luanda(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    if dt.tzinfo is not None:
        return dt.astimezone(LUANDA_TZ).replace(tzinfo=None)
    return dt


def _now_naive() -> datetime:
    return now_luanda().replace(tzinfo=None)


def classify_freshness(
    recorded_at: Optional[datetime],
    expires_at: Optional[datetime],
    thresholds: dict[str, float],
) -> tuple[str, float]:
    """Return (RECENT | STALE | EXPIRED, age_minutes)."""
    now = _now_naive()
    rec = _as_naive_luanda(recorded_at)
    exp = _as_naive_luanda(expires_at)
    if rec is None:
        return "EXPIRED", 9999.0
    age_min = max(0.0, (now - rec).total_seconds() / 60.0)
    if exp is not None and exp <= now:
        return "EXPIRED", round(age_min, 1)
    if age_min > thresholds["stale_minutes"]:
        return "EXPIRED", round(age_min, 1)
    if age_min > thresholds["recent_minutes"]:
        return "STALE", round(age_min, 1)
    return "RECENT", round(age_min, 1)


def expire_stale_records(db: Session) -> dict[str, int]:
    """Mark expired intentions and driver reports so old data is never treated as active supply/demand."""
    now = _now_naive()
    expired_intentions = 0
    expired_drivers = 0

    active_ints = db.scalars(
        select(TransportIntention).where(TransportIntention.status.in_(["DECLARED", "CONFIRMED_AT_STOP"]))
    ).all()
    for it in active_ints:
        exp = _as_naive_luanda(it.expires_at)
        if exp and exp <= now:
            it.status = "EXPIRED"
            expired_intentions += 1

    active_drvs = db.scalars(select(DriverReport).where(DriverReport.is_active == True)).all()  # noqa: E712
    for dr in active_drvs:
        exp = _as_naive_luanda(dr.expires_at)
        if exp and exp <= now:
            dr.is_active = False
            dr.availability_status = "UNAVAILABLE"
            expired_drivers += 1

    return {"expired_intentions": expired_intentions, "expired_driver_reports": expired_drivers}


def evaluate_corridor_status(
    db: Session,
    origin_zone: str,
    destination_zone: str,
    route: Optional[TransportRoute] = None,
    include_alternatives: bool = True,
) -> dict:
    """
    Core Intelligence Engine for a given Origin -> Destination corridor.
    Strictly separates declared vs confirmed/observed data, enforces expiration windows,
    and returns 'Informação insuficiente para esta via.' when no valid data exists.
    """
    thresholds = get_thresholds(db)
    o_low = origin_zone.strip().lower()
    d_low = destination_zone.strip().lower()

    if route is None:
        origin_z_obj = db.scalar(select(TransportZone).where(TransportZone.name.ilike(origin_zone.strip())))
        dest_z_obj = db.scalar(select(TransportZone).where(TransportZone.name.ilike(destination_zone.strip())))
        if origin_z_obj and dest_z_obj:
            route = db.scalar(
                select(TransportRoute).where(
                    TransportRoute.origin_zone_id == origin_z_obj.id,
                    TransportRoute.destination_zone_id == dest_z_obj.id,
                    TransportRoute.is_active == True,  # noqa: E712
                )
            )

    # 1. Passenger Intentions (declared vs confirmed at stop)
    intentions = db.scalars(
        select(TransportIntention).where(
            TransportIntention.status.in_(["DECLARED", "CONFIRMED_AT_STOP"]),
            TransportIntention.validation_status != "FLAGGED_SUSPICIOUS",
        )
    ).all()

    matched_intentions = [
        i
        for i in intentions
        if i.origin_zone_name.lower() == o_low and i.destination_zone_name.lower() == d_low
    ]

    declared_demand = 0
    confirmed_passenger_demand = 0
    latest_ts: Optional[datetime] = None
    freshness_ranks: list[str] = []
    sources_used: set[str] = set()
    has_demo_data = False

    for i in matched_intentions:
        fr, _ = classify_freshness(i.last_confirmed_at, i.expires_at, thresholds)
        if fr == "EXPIRED":
            continue
        freshness_ranks.append(fr)
        if i.is_demo_data:
            has_demo_data = True
        ts = _as_naive_luanda(i.last_confirmed_at)
        if ts and (latest_ts is None or ts > latest_ts):
            latest_ts = ts
        if i.status == "CONFIRMED_AT_STOP":
            confirmed_passenger_demand += i.passenger_count
            sources_used.add("CONFIRMADO_PARAGEM")
        else:
            declared_demand += i.passenger_count
            sources_used.add("DECLARADO_PASSAGEIRO")

    # 2. Validated Field Demand Observations (latest non-expired observation per stop)
    demand_obs_rows = db.scalars(
        select(DemandObservation)
        .where(DemandObservation.validation_status == "VALIDATED")
        .order_by(desc(DemandObservation.observed_at))
    ).all()
    field_demand_total = 0
    field_wait_estimates: list[int] = []
    seen_demand_stops: set[int] = set()
    for obs in demand_obs_rows:
        if obs.origin_zone_name.lower() != o_low or obs.destination_zone_name.lower() != d_low:
            continue
        if obs.taxi_stop_id in seen_demand_stops:
            continue
        fr, _ = classify_freshness(obs.observed_at, obs.expires_at, thresholds)
        if fr == "EXPIRED":
            continue
        seen_demand_stops.add(obs.taxi_stop_id)
        freshness_ranks.append(fr)
        field_demand_total += obs.observed_passengers_count
        if obs.estimated_wait_min is not None:
            field_wait_estimates.append(obs.estimated_wait_min)
        if obs.is_demo_data:
            has_demo_data = True
        sources_used.add("OBSERVADO_CAMPO")
        ts = _as_naive_luanda(obs.observed_at)
        if ts and (latest_ts is None or ts > latest_ts):
            latest_ts = ts

    # 3. Driver Availability Reports (deduplicated per driver_id)
    driver_rows = db.scalars(
        select(DriverReport)
        .where(
            DriverReport.is_active == True,  # noqa: E712
            DriverReport.availability_status.in_(["AVAILABLE", "AT_STOP"]),
        )
        .order_by(desc(DriverReport.last_confirmed_at))
    ).all()
    declared_supply = 0
    seen_drivers: set[int] = set()
    for dr in driver_rows:
        if dr.origin_zone_name.lower() != o_low or dr.destination_zone_name.lower() != d_low:
            continue
        if dr.driver_id in seen_drivers:
            continue
        fr, _ = classify_freshness(dr.last_confirmed_at, dr.expires_at, thresholds)
        if fr == "EXPIRED":
            continue
        seen_drivers.add(dr.driver_id)
        declared_supply += 1
        freshness_ranks.append(fr)
        if dr.is_demo_data:
            has_demo_data = True
        sources_used.add("DECLARADO_MOTORISTA")
        ts = _as_naive_luanda(dr.last_confirmed_at)
        if ts and (latest_ts is None or ts > latest_ts):
            latest_ts = ts

    # 4. Validated Field Supply Observations (latest non-expired observation per stop)
    supply_obs_rows = db.scalars(
        select(SupplyObservation)
        .where(SupplyObservation.validation_status == "VALIDATED")
        .order_by(desc(SupplyObservation.observed_at))
    ).all()
    observed_supply = 0
    road_condition = route.road_condition if route else "NORMAL"
    seen_supply_stops: set[int] = set()
    for obs in supply_obs_rows:
        if obs.origin_zone_name.lower() != o_low or obs.destination_zone_name.lower() != d_low:
            continue
        if obs.taxi_stop_id in seen_supply_stops:
            continue
        fr, _ = classify_freshness(obs.observed_at, obs.expires_at, thresholds)
        if fr == "EXPIRED":
            continue
        seen_supply_stops.add(obs.taxi_stop_id)
        observed_supply += obs.observed_taxis_count
        road_condition = obs.road_condition or road_condition
        freshness_ranks.append(fr)
        if obs.is_demo_data:
            has_demo_data = True
        sources_used.add("OBSERVADO_CAMPO")
        ts = _as_naive_luanda(obs.observed_at)
        if ts and (latest_ts is None or ts > latest_ts):
            latest_ts = ts

    confirmed_demand = confirmed_passenger_demand + field_demand_total
    estimated_demand_total = declared_demand + confirmed_demand
    total_supply = declared_supply + observed_supply

    has_sufficient_data = len(freshness_ranks) > 0 and (estimated_demand_total > 0 or total_supply > 0)

    if not has_sufficient_data:
        result = {
            "route_id": route.id if route else None,
            "route_name": route.name if route else f"Via {origin_zone} → {destination_zone}",
            "origin_zone": origin_zone,
            "destination_zone": destination_zone,
            "has_sufficient_data": False,
            "status_message": "Informação insuficiente para esta via.",
            "estimated_demand": 0,
            "declared_demand": 0,
            "confirmed_demand": 0,
            "declared_supply": 0,
            "observed_supply": 0,
            "total_supply": 0,
            "demand_supply_ratio": None,
            "ratio_disclaimer": "Sem registos válidos recentes suficientes para calcular o rácio.",
            "demand_level": "INSUFFICIENT_DATA",
            "supply_level": "INSUFFICIENT_DATA",
            "balance_label": "Informação insuficiente",
            "driver_advisory": "Informação insuficiente para esta via.",
            "passenger_advisory": "Informação insuficiente para esta via. Seja o primeiro a declarar a sua intenção.",
            "estimated_wait_min": None,
            "road_condition": road_condition,
            "freshness_status": "EXPIRED",
            "confidence_level": "LOW",
            "validation_state": "SEM_DADOS",
            "sources": [],
            "contains_demo_data": False,
            "last_updated_at": None,
            "trend": "SEM_TENDENCIA",
        }
    else:
        # Freshness overall: RECENT if at least one RECENT record, else STALE
        overall_freshness = "RECENT" if "RECENT" in freshness_ranks else "STALE"

        # Classification using configurable admin thresholds
        if estimated_demand_total >= thresholds["demand_high_min"]:
            demand_level = "PROCURA_ELEVADA"
        elif estimated_demand_total >= thresholds["demand_moderate_min"]:
            demand_level = "PROCURA_MODERADA"
        else:
            demand_level = "PROCURA_BAIXA"

        if total_supply >= thresholds["supply_high_min"]:
            supply_level = "OFERTA_ELEVADA"
        elif total_supply >= thresholds["supply_moderate_min"]:
            supply_level = "OFERTA_MODERADA"
        else:
            supply_level = "OFERTA_REDUZIDA"

        ratio = round(estimated_demand_total / total_supply, 2) if total_supply > 0 else None
        imbalanced = (ratio is not None and ratio >= thresholds["imbalance_ratio_threshold"]) or (
            estimated_demand_total >= thresholds["demand_moderate_min"] and total_supply == 0
        )

        if imbalanced:
            balance_label = "Desequilíbrio (Procura acima da oferta)"
            driver_advisory = "Possível oportunidade de procura elevada nesta via."
            passenger_advisory = "Procura estimada elevada face aos táxis sinalizados. Considere aguardar ou comparar paragens próximas."
        elif demand_level == "PROCURA_ELEVADA":
            balance_label = "Movimento intenso com oferta activa"
            driver_advisory = "Procura estimada elevada com movimento activo."
            passenger_advisory = "Movimento elevado de passageiros, mas com oferta de táxis sinalizada."
        elif supply_level == "OFERTA_ELEVADA":
            balance_label = "Oferta favorável para passageiros"
            driver_advisory = "Oferta elevada de táxis face à procura estimada."
            passenger_advisory = "Boa disponibilidade estimada de táxis nesta via."
        else:
            balance_label = "Equilíbrio moderado"
            driver_advisory = "Procura estimada moderada nesta via."
            passenger_advisory = "Fluxo moderado estimado nesta via."

        if overall_freshness == "STALE":
            passenger_advisory = f"[Dados desactualizados] {passenger_advisory}"
            driver_advisory = f"[Dados desactualizados] {driver_advisory}"

        # Confidence level strictly reflects source quality
        if "OBSERVADO_CAMPO" in sources_used and overall_freshness == "RECENT":
            confidence = "HIGH"
            val_state = "VALIDADO_CAMPO"
        elif ("CONFIRMADO_PARAGEM" in sources_used or len(sources_used) >= 2) and overall_freshness == "RECENT":
            confidence = "MEDIUM"
            val_state = "PARCIALMENTE_CONFIRMADO"
        else:
            confidence = "LOW"
            val_state = "DECLARADO_UTILIZADORES"

        # Wait time only when field wait observation exists or both supply & demand exist
        if field_wait_estimates:
            est_wait = int(round(sum(field_wait_estimates) / len(field_wait_estimates)))
        elif ratio is not None:
            est_wait = max(4, min(45, int(round(ratio * 4.5))))
        else:
            est_wait = None

        # Compare against historical MobilityIndicator average for trend
        hist = db.scalars(
            select(MobilityIndicator)
            .where(
                MobilityIndicator.origin_zone_name.ilike(origin_zone),
                MobilityIndicator.destination_zone_name.ilike(destination_zone),
            )
            .order_by(desc(MobilityIndicator.captured_at))
            .limit(5)
        ).all()
        if hist:
            avg_prev = sum(h.estimated_demand for h in hist) / len(hist)
            if estimated_demand_total > avg_prev * 1.15:
                trend = "A_SUBIR"
            elif estimated_demand_total < avg_prev * 0.85:
                trend = "A_DESCER"
            else:
                trend = "ESTAVEL"
        else:
            trend = "ESTAVEL"

        result = {
            "route_id": route.id if route else None,
            "route_name": route.name if route else f"Via {origin_zone} → {destination_zone}",
            "origin_zone": origin_zone,
            "destination_zone": destination_zone,
            "has_sufficient_data": True,
            "status_message": None,
            "estimated_demand": estimated_demand_total,
            "declared_demand": declared_demand,
            "confirmed_demand": confirmed_demand,
            "declared_supply": declared_supply,
            "observed_supply": observed_supply,
            "total_supply": total_supply,
            "demand_supply_ratio": ratio,
            "ratio_disclaimer": (
                f"Indicador ilustrativo ({ratio} passageiros interessados por táxi sinalizado). "
                "Não assume capacidades idênticas entre veículos."
                if ratio is not None
                else "Sem táxis sinalizados para calcular o rácio."
            ),
            "demand_level": demand_level,
            "supply_level": supply_level,
            "imbalance": imbalanced,
            "balance_label": balance_label,
            "driver_advisory": driver_advisory,
            "passenger_advisory": passenger_advisory,
            "estimated_wait_min": est_wait,
            "road_condition": road_condition,
            "freshness_status": overall_freshness,
            "confidence_level": confidence,
            "validation_state": val_state,
            "sources": sorted(sources_used),
            "contains_demo_data": has_demo_data,
            "last_updated_at": latest_ts.isoformat() if latest_ts else None,
            "trend": trend,
        }

    # Add alternative nearby stops/routes for the same destination
    if include_alternatives:
        alternatives = []
        origin_z = db.scalar(select(TransportZone).where(TransportZone.name.ilike(origin_zone)))
        all_routes = db.scalars(select(TransportRoute).where(TransportRoute.is_active == True)).all()  # noqa: E712
        zones_by_id = {z.id: z for z in db.scalars(select(TransportZone)).all()}

        for r in all_routes:
            oz = zones_by_id.get(r.origin_zone_id)
            dz = zones_by_id.get(r.destination_zone_id)
            if not oz or not dz:
                continue
            if dz.name.lower() != d_low or oz.name.lower() == o_low:
                continue
            dist_km = (
                haversine_km(origin_z.center_lat, origin_z.center_lng, oz.center_lat, oz.center_lng)
                if origin_z
                else 99.0
            )
            if dist_km <= 8.0:
                alt_eval = evaluate_corridor_status(
                    db, oz.name, dz.name, route=r, include_alternatives=False
                )
                alt_eval["distance_from_origin_km"] = dist_km
                alternatives.append(alt_eval)
        alternatives.sort(key=lambda a: (not a["has_sufficient_data"], a.get("distance_from_origin_km", 99)))
        result["alternatives"] = alternatives[:4]

    return result


def compute_all_routes_overview(
    db: Session,
    zone: Optional[str] = None,
    municipality: Optional[str] = None,
    destination: Optional[str] = None,
    demand_level_filter: Optional[str] = None,
    supply_level_filter: Optional[str] = None,
) -> list[dict]:
    expire_stale_records(db)
    routes = db.scalars(select(TransportRoute).where(TransportRoute.is_active == True)).all()  # noqa: E712
    zones = {z.id: z for z in db.scalars(select(TransportZone)).all()}
    neighs = {n.id: n for n in db.scalars(select(Neighborhood)).all()}
    munis = {m.id: m for m in db.scalars(select(Municipality)).all()}

    items = []
    for r in routes:
        oz = zones.get(r.origin_zone_id)
        dz = zones.get(r.destination_zone_id)
        if not oz or not dz:
            continue
        nb = neighs.get(oz.neighborhood_id)
        muni = munis.get(nb.municipality_id) if nb else None

        if zone and oz.name.lower() != zone.lower() and dz.name.lower() != zone.lower():
            continue
        if destination and dz.name.lower() != destination.lower():
            continue
        if municipality and (not muni or muni.name.lower() != municipality.lower()):
            continue

        ev = evaluate_corridor_status(db, oz.name, dz.name, route=r, include_alternatives=False)
        ev["route_code"] = r.code
        ev["corridor_description"] = r.corridor_description
        ev["origin_lat"] = oz.center_lat
        ev["origin_lng"] = oz.center_lng
        ev["destination_lat"] = dz.center_lat
        ev["destination_lng"] = dz.center_lng
        ev["municipality"] = muni.name if muni else "Luanda"
        ev["neighborhood"] = nb.name if nb else oz.name

        if demand_level_filter and ev["demand_level"] != demand_level_filter:
            continue
        if supply_level_filter and ev["supply_level"] != supply_level_filter:
            continue
        items.append(ev)

    rank = {"PROCURA_ELEVADA": 0, "PROCURA_MODERADA": 1, "PROCURA_BAIXA": 2, "INSUFFICIENT_DATA": 3}
    items.sort(key=lambda x: (rank.get(x["demand_level"], 9), -x["estimated_demand"]))
    return items


def record_indicator_snapshot(db: Session, eval_data: dict, taxi_stop_id: Optional[int] = None) -> MobilityIndicator:
    snap = MobilityIndicator(
        route_id=eval_data.get("route_id"),
        taxi_stop_id=taxi_stop_id,
        origin_zone_name=eval_data["origin_zone"],
        destination_zone_name=eval_data["destination_zone"],
        estimated_demand=eval_data["estimated_demand"],
        confirmed_demand=eval_data["confirmed_demand"],
        declared_supply=eval_data["declared_supply"],
        observed_supply=eval_data["observed_supply"],
        demand_supply_ratio=eval_data.get("demand_supply_ratio"),
        demand_level=eval_data["demand_level"],
        supply_level=eval_data["supply_level"],
        estimated_wait_min=eval_data.get("estimated_wait_min"),
        freshness_status=eval_data["freshness_status"],
    )
    db.add(snap)
    return snap


def compute_historical_analytics(db: Session) -> dict:
    """Section 9: Descriptive historical analytics from real stored records & snapshots."""
    thresholds = get_thresholds(db)
    intentions = db.scalars(select(TransportIntention)).all()
    demand_obs = db.scalars(select(DemandObservation)).all()
    supply_obs = db.scalars(select(SupplyObservation)).all()
    driver_reports = db.scalars(select(DriverReport)).all()
    snapshots = db.scalars(select(MobilityIndicator).order_by(desc(MobilityIndicator.captured_at)).limit(200)).all()

    zones = {z.name.lower(): z for z in db.scalars(select(TransportZone)).all()}
    neighs = {n.id: n for n in db.scalars(select(Neighborhood)).all()}
    munis = {m.id: m for m in db.scalars(select(Municipality)).all()}
    stops_by_id = {s.id: s for s in db.scalars(select(TaxiStop)).all()}

    by_municipality: Counter[str] = Counter()
    by_neighborhood: Counter[str] = Counter()
    by_stop: Counter[str] = Counter()
    by_destination: Counter[str] = Counter()
    by_weekday: Counter[str] = Counter()
    by_hour: Counter[int] = Counter()
    unmet_count = 0

    weekday_names = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"]

    for i in intentions:
        z = zones.get(i.origin_zone_name.lower())
        nb = neighs.get(z.neighborhood_id) if z else None
        mu = munis.get(nb.municipality_id) if nb else None
        st = stops_by_id.get(i.origin_stop_id)
        by_municipality[mu.name if mu else "Luanda"] += i.passenger_count
        by_neighborhood[nb.name if nb else i.origin_zone_name] += i.passenger_count
        if st:
            by_stop[st.name] += i.passenger_count
        by_destination[i.destination_zone_name] += i.passenger_count
        dt = _as_naive_luanda(i.created_at) or _now_naive()
        by_weekday[weekday_names[dt.weekday()]] += i.passenger_count
        by_hour[dt.hour] += i.passenger_count
        if i.status in {"CANCELLED", "EXPIRED"}:
            unmet_count += 1

    for obs in demand_obs:
        if obs.validation_status != "VALIDATED":
            continue
        z = zones.get(obs.origin_zone_name.lower())
        nb = neighs.get(z.neighborhood_id) if z else None
        mu = munis.get(nb.municipality_id) if nb else None
        st = stops_by_id.get(obs.taxi_stop_id)
        by_municipality[mu.name if mu else "Luanda"] += obs.observed_passengers_count
        by_neighborhood[nb.name if nb else obs.origin_zone_name] += obs.observed_passengers_count
        if st:
            by_stop[st.name] += obs.observed_passengers_count
        by_destination[obs.destination_zone_name] += obs.observed_passengers_count
        dt = _as_naive_luanda(obs.observed_at) or _now_naive()
        by_weekday[weekday_names[dt.weekday()]] += obs.observed_passengers_count
        by_hour[dt.hour] += obs.observed_passengers_count

    # Data quality percentages
    total_records = len(intentions) + len(driver_reports) + len(demand_obs) + len(supply_obs)
    validated_records = (
        sum(1 for i in intentions if i.status == "CONFIRMED_AT_STOP")
        + sum(1 for o in demand_obs if o.validation_status == "VALIDATED")
        + sum(1 for o in supply_obs if o.validation_status == "VALIDATED")
    )
    stale_or_expired = 0
    for i in intentions:
        fr, _ = classify_freshness(i.last_confirmed_at, i.expires_at, thresholds)
        if fr in {"STALE", "EXPIRED"} or i.status == "EXPIRED":
            stale_or_expired += 1
    for dr in driver_reports:
        fr, _ = classify_freshness(dr.last_confirmed_at, dr.expires_at, thresholds)
        if fr in {"STALE", "EXPIRED"} or not dr.is_active:
            stale_or_expired += 1

    wait_vals = [o.estimated_wait_min for o in demand_obs if o.estimated_wait_min is not None]
    avg_wait = round(sum(wait_vals) / len(wait_vals), 1) if wait_vals else None

    return {
        "demand_by_municipality": [{"name": k, "passengers": v} for k, v in by_municipality.most_common(10)],
        "demand_by_neighborhood": [{"name": k, "passengers": v} for k, v in by_neighborhood.most_common(10)],
        "demand_by_stop": [{"name": k, "passengers": v} for k, v in by_stop.most_common(10)],
        "demand_by_destination": [{"name": k, "passengers": v} for k, v in by_destination.most_common(10)],
        "demand_by_weekday": [{"day": d, "passengers": by_weekday.get(d, 0)} for d in weekday_names],
        "demand_by_hour": [{"hour": f"{h:02d}h", "passengers": by_hour.get(h, 0)} for h in range(24)],
        "avg_wait_min": avg_wait,
        "unmet_or_cancelled_intentions": unmet_count,
        "data_quality": {
            "total_records": total_records,
            "validated_pct": round((validated_records / max(1, total_records)) * 100.0, 1),
            "stale_or_expired_pct": round((stale_or_expired / max(1, total_records)) * 100.0, 1),
            "pending_validations": (
                sum(1 for o in demand_obs if o.validation_status == "PENDING")
                + sum(1 for o in supply_obs if o.validation_status == "PENDING")
            ),
            "suspicious_records": sum(1 for i in intentions if i.validation_status == "FLAGGED_SUSPICIOUS"),
        },
        "snapshots_count": len(snapshots),
        "predictive_model_note": (
            "Análise descritiva baseada em registos reais. "
            "Previsões por Machine Learning só serão activadas quando existir histórico suficiente."
        ),
    }
