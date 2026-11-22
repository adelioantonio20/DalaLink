import math
from typing import Optional

# Key Luanda urban mobility zones and hubs (real coordinates in Luanda, Angola)
LUANDA_ZONES: list[dict] = [
    {
        "zone": "Gamek",
        "name": "Paragem Principal do Gamek (Avenida Deolinda Rodrigues / Rocha Pinto)",
        "lat": -8.8842,
        "lng": 13.2148,
    },
    {
        "zone": "Aeroporto",
        "name": "Aeroporto Internacional 4 de Fevereiro",
        "lat": -8.8584,
        "lng": 13.2312,
    },
    {
        "zone": "Maianga",
        "name": "Largo da Maianga",
        "lat": -8.8318,
        "lng": 13.2345,
    },
    {
        "zone": "Mutamba",
        "name": "Largo da Mutamba (Centro de Luanda)",
        "lat": -8.8147,
        "lng": 13.2302,
    },
    {
        "zone": "Ingombota",
        "name": "Marginal de Luanda / Ingombota",
        "lat": -8.8095,
        "lng": 13.2358,
    },
    {
        "zone": "Talatona",
        "name": "Centro de Convenções de Talatona / Belas Shopping",
        "lat": -8.9186,
        "lng": 13.1846,
    },
    {
        "zone": "Benfica",
        "name": "Rotunda do Benfica (Estrada da Samba)",
        "lat": -8.9475,
        "lng": 13.1652,
    },
    {
        "zone": "Kilamba",
        "name": "Centralidade do Kilamba (Entrada Principal)",
        "lat": -9.0008,
        "lng": 13.2683,
    },
    {
        "zone": "Viana",
        "name": "Ponte Partida / Centro de Viana",
        "lat": -8.9036,
        "lng": 13.3745,
    },
    {
        "zone": "Samba",
        "name": "Praia da Samba / Corimba",
        "lat": -8.8672,
        "lng": 13.1975,
    },
]


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Calculate great-circle distance in kilometers between two WGS84 coordinates."""
    r = 6371.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2.0) ** 2
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return round(r * c, 2)


def road_distance_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Apply Luanda urban road winding factor (~1.28x straight line)."""
    straight = haversine_km(lat1, lng1, lat2, lng2)
    return round(max(0.8, straight * 1.28), 2)


def estimate_duration_minutes(distance_km: float, traffic_factor: float = 1.25) -> int:
    """Estimate travel duration in minutes for Luanda urban speed (~28 km/h base)."""
    avg_speed_kmh = 28.0 / max(1.0, traffic_factor)
    minutes = (distance_km / avg_speed_kmh) * 60.0
    return max(3, int(round(minutes)))


def detect_nearest_zone(lat: float, lng: float) -> str:
    """Identify the closest Luanda operational zone for a given GPS coordinate."""
    best_zone = "Luanda Centro"
    best_dist = float("inf")
    for z in LUANDA_ZONES:
        d = haversine_km(lat, lng, z["lat"], z["lng"])
        if d < best_dist:
            best_dist = d
            best_zone = z["zone"]
    return best_zone


def interpolate_position(
    cur_lat: float,
    cur_lng: float,
    target_lat: float,
    target_lng: float,
    step_fraction: float = 0.35,
) -> tuple[float, float, Optional[float]]:
    """Move a simulated vehicle fractionally toward target and return (lat, lng, heading_deg)."""
    dlat = target_lat - cur_lat
    dlng = target_lng - cur_lng
    if abs(dlat) < 0.0005 and abs(dlng) < 0.0005:
        return target_lat, target_lng, 0.0
    new_lat = cur_lat + dlat * step_fraction
    new_lng = cur_lng + dlng * step_fraction
    heading = (math.degrees(math.atan2(dlng, dlat)) + 360.0) % 360.0
    return round(new_lat, 6), round(new_lng, 6), round(heading, 1)
