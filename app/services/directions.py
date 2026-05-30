from __future__ import annotations

import httpx

from app.config import settings


def _decode_polyline(encoded: str) -> list[tuple[float, float]]:
    points: list[tuple[float, float]] = []
    index = lat = lng = 0
    while index < len(encoded):
        for is_lng in (False, True):
            result = shift = 0
            while True:
                b = ord(encoded[index]) - 63
                index += 1
                result |= (b & 0x1f) << shift
                shift += 5
                if b < 0x20:
                    break
            delta = -(result >> 1) if result & 1 else result >> 1
            if is_lng:
                lng += delta
            else:
                lat += delta
        points.append((lat * 1e-5, lng * 1e-5))
    return points


async def get_route_polyline(
    points: list[tuple[float, float]],
) -> tuple[list[tuple[float, float]] | None, str | None]:
    """Returns (path, error_status). error_status is None on success."""
    if not settings.google_maps_api_key:
        return None, "NO_API_KEY"
    if len(points) < 2:
        return None, "INSUFFICIENT_POINTS"

    origin = f"{points[0][0]},{points[0][1]}"
    destination = f"{points[-1][0]},{points[-1][1]}"
    waypoints = "|".join(f"{p[0]},{p[1]}" for p in points[1:-1][:25])

    params: dict = {
        "origin": origin,
        "destination": destination,
        "key": settings.google_maps_api_key,
    }
    if waypoints:
        params["waypoints"] = waypoints

    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(
                "https://maps.googleapis.com/maps/api/directions/json",
                params=params,
                timeout=10.0,
            )
            data = resp.json()
        except (httpx.HTTPError, ValueError):
            return None, "HTTP_ERROR"

    status = data.get("status", "UNKNOWN")
    if status != "OK" or not data.get("routes"):
        return None, status

    encoded = data["routes"][0].get("overview_polyline", {}).get("points", "")
    if not encoded:
        return None, "EMPTY_POLYLINE"
    return _decode_polyline(encoded), None
