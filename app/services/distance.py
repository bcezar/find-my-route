from __future__ import annotations

import asyncio
import logging
import math

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

_CHUNK = 25  # Routes API limit per dimension (25×25 = 625 elements max per request)


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


async def _osrm_matrix(
    coords: list[tuple[float, float]],
) -> tuple[list[list[float]], list[list[float]]] | None:
    if not settings.osrm_base_url:
        return None

    # OSRM expects lon,lat (reversed from our internal lat,lng)
    coord_str = ";".join(f"{lng},{lat}" for lat, lng in coords)

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{settings.osrm_base_url}/table/v1/driving/{coord_str}",
                params={"annotations": "distance,duration"},
                timeout=10.0,
            )
            response.raise_for_status()
            data = response.json()
    except (httpx.HTTPError, ValueError):
        return None

    if data.get("code") != "Ok" or "distances" not in data or "durations" not in data:
        return None

    dist_matrix = [[d / 1000.0 for d in row] for row in data["distances"]]
    dur_matrix  = [[s / 60.0   for s in row] for row in data["durations"]]
    return dist_matrix, dur_matrix


async def _fetch_routes_chunk(
    client: httpx.AsyncClient,
    origins: list[dict],
    destinations: list[dict],
) -> list[dict] | None:
    try:
        resp = await client.post(
            "https://routes.googleapis.com/distanceMatrix/v2:computeRouteMatrix",
            json={
                "origins": origins,
                "destinations": destinations,
                "travelMode": "DRIVE",
                "routingPreference": "TRAFFIC_UNAWARE",
            },
            headers={
                "X-Goog-Api-Key": settings.google_maps_api_key,
                "X-Goog-FieldMask": "originIndex,destinationIndex,distanceMeters,duration",
            },
            timeout=15.0,
        )
        resp.raise_for_status()
        data = resp.json()
    except (httpx.HTTPError, ValueError):
        return None
    return data if isinstance(data, list) else None


async def _routes_api_matrix(
    coords: list[tuple[float, float]],
) -> tuple[list[list[float]], list[list[float]]] | None:
    if not settings.google_maps_api_key:
        return None

    n = len(coords)
    waypoints = [
        {"waypoint": {"location": {"latLng": {"latitude": lat, "longitude": lng}}}}
        for lat, lng in coords
    ]

    chunks = [
        (i0, min(i0 + _CHUNK, n), j0, min(j0 + _CHUNK, n))
        for i0 in range(0, n, _CHUNK)
        for j0 in range(0, n, _CHUNK)
    ]

    async with httpx.AsyncClient() as client:
        results = await asyncio.gather(*[
            _fetch_routes_chunk(client, waypoints[i0:i1], waypoints[j0:j1])
            for i0, i1, j0, j1 in chunks
        ])

    if any(r is None for r in results):
        return None

    dist = [[0.0] * n for _ in range(n)]
    dur  = [[0.0] * n for _ in range(n)]

    for (i0, _, j0, _), elements in zip(chunks, results):
        for elem in elements:  # type: ignore[union-attr]
            if "distanceMeters" not in elem or "duration" not in elem:
                return None
            oi = elem["originIndex"] + i0
            di = elem["destinationIndex"] + j0
            dist[oi][di] = elem["distanceMeters"] / 1000.0
            dur[oi][di]  = int(str(elem["duration"]).rstrip("s")) / 60.0

    return dist, dur


async def build_distance_matrix(
    coords: list[tuple[float, float]],
) -> tuple[list[list[float]], list[list[float]] | None]:
    # Priority: OSRM (self-hosted, free) → Routes API (Google, paid) → Haversine (straight-line)
    result = await _osrm_matrix(coords)
    if result is not None:
        logger.info("distance_provider=osrm n=%d", len(coords))
        return result
    result = await _routes_api_matrix(coords)
    if result is not None:
        logger.info("distance_provider=routes_api n=%d", len(coords))
        return result
    logger.info("distance_provider=haversine n=%d", len(coords))
    return _haversine_matrix(coords), None
