from __future__ import annotations

from urllib.parse import urlencode

import httpx

from app.config import settings

_SIZE = "460x180"
_SCALE = "2"
_PATH_COLOR = "0x3b82f6d0"
_PATH_WEIGHT = "3"


async def fetch_static_map(
    encoded_polyline: str | None,
    origin: tuple[float, float],
    destination: tuple[float, float],
) -> bytes | None:
    if not settings.google_maps_api_key:
        return None

    params: list[tuple[str, str]] = [
        ("size", _SIZE),
        ("scale", _SCALE),
        ("maptype", "roadmap"),
        ("key", settings.google_maps_api_key),
    ]

    if encoded_polyline:
        params.append(("path", f"color:{_PATH_COLOR}|weight:{_PATH_WEIGHT}|enc:{encoded_polyline}"))

    params.append(("markers", f"color:green|{origin[0]},{origin[1]}"))

    if destination != origin:
        params.append(("markers", f"color:blue|{destination[0]},{destination[1]}"))

    url = "https://maps.googleapis.com/maps/api/staticmap?" + urlencode(params)

    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(url, timeout=10.0)
            if not resp.is_success:
                return None
            return resp.content
        except httpx.HTTPError:
            return None
