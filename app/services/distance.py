from __future__ import annotations

import math

import httpx

from app.config import settings


def haversine_km(point_a: tuple[float, float], point_b: tuple[float, float]) -> float:
    lat1, lon1 = math.radians(point_a[0]), math.radians(point_a[1])
    lat2, lon2 = math.radians(point_b[0]), math.radians(point_b[1])

    dlat = lat2 - lat1
    dlon = lon2 - lon1

    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 6371.0 * 2 * math.asin(math.sqrt(a))


def _haversine_matrix(coords: list[tuple[float, float]]) -> list[list[float]]:
    n = len(coords)
    return [[haversine_km(coords[i], coords[j]) for j in range(n)] for i in range(n)]


async def _osrm_matrix(coords: list[tuple[float, float]]) -> list[list[float]] | None:
    if not settings.osrm_base_url:
        return None

    # OSRM expects lon,lat (reversed from our internal lat,lng)
    coord_str = ";".join(f"{lng},{lat}" for lat, lng in coords)

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{settings.osrm_base_url}/table/v1/driving/{coord_str}",
                params={"annotations": "distance"},
                timeout=10.0,
            )
            response.raise_for_status()
            data = response.json()
    except (httpx.HTTPError, ValueError):
        return None

    if data.get("code") != "Ok" or "distances" not in data:
        return None

    # Convert meters → km
    return [[d / 1000.0 for d in row] for row in data["distances"]]


async def build_distance_matrix(coords: list[tuple[float, float]]) -> list[list[float]]:
    matrix = await _osrm_matrix(coords)
    if matrix is not None:
        return matrix
    return _haversine_matrix(coords)
