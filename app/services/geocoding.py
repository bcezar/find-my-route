from __future__ import annotations

import asyncio
import re

import httpx

from app.config import settings

_cache: dict[str, tuple[float, float] | None] = {}


_STREET_PREFIXES = r"(?:Rua|R\.|Av\.|Avenida|Alameda|Al\.|Travessa|Tv\.|Estrada|Rod\.|Rodovia|Praça|Pça\.)"


def _normalize(address: str) -> str:
    """Normalize Brazilian address format for better Nominatim matching.

    - 'Medkal Pet, 123 Rua X, Cidade/SP' → 'Rua X, 123, Cidade, SP, Brasil'
    - 'Rua X, 123, Cidade/SP'            → 'Rua X, 123, Cidade, SP, Brasil'
    """
    # Strip leading business name: if a street prefix appears after a comma,
    # discard everything before it and move any inline number after the street name.
    # e.g. "Medkal Pet, 446 Rua Bolívia, Americana/SP"
    #   → "Rua Bolívia, 446, Americana/SP"
    business_match = re.search(
        rf",\s*(\d+)?\s*({_STREET_PREFIXES}\b.+)", address, re.IGNORECASE
    )
    if business_match:
        number = business_match.group(1) or ""
        rest = business_match.group(2).strip()
        # Re-attach the number right after the street prefix+name segment
        first_comma = rest.find(",")
        if number:
            if first_comma != -1:
                rest = rest[:first_comma] + f", {number}" + rest[first_comma:]
            else:
                rest = rest + f", {number}"
        address = rest

    # Replace city/state slash separator: Americana/SP → Americana, SP
    normalized = re.sub(r"([A-Za-zÀ-ú\s]+)/([A-Z]{2})\b", r"\1, \2", address)
    # Append Brasil if not already present
    if "brasil" not in normalized.lower() and "brazil" not in normalized.lower():
        normalized = normalized.rstrip(", ") + ", Brasil"
    return normalized


def _parse_structured(address: str) -> dict[str, str] | None:
    """Try to extract street + city + state for structured Nominatim query.

    Expects format: 'Street info, City, SP, Brasil'
    Returns None if pattern doesn't match.
    """
    # Match: anything, City, 2-letter state, Brasil
    match = re.search(r"^(.+),\s*([^,]+),\s*([A-Z]{2}),\s*Brasil\s*$", address)
    if not match:
        return None
    return {
        "street": match.group(1).strip(),
        "city": match.group(2).strip(),
        "state": match.group(3).strip(),
        "country": "Brasil",
        "format": "json",
        "limit": "1",
        "countrycodes": "br",
    }


async def _query_nominatim(
    params: dict, client: httpx.AsyncClient
) -> tuple[float, float] | None:
    headers = {"User-Agent": settings.nominatim_user_agent}
    try:
        response = await client.get(
            f"{settings.nominatim_base_url}/search",
            params=params,
            headers=headers,
            timeout=10.0,
        )
        response.raise_for_status()
        results = response.json()
    except (httpx.HTTPError, ValueError):
        return None

    if not results:
        return None

    return (float(results[0]["lat"]), float(results[0]["lon"]))


async def _geocode_google(address: str, client: httpx.AsyncClient) -> tuple[float, float] | None:
    try:
        response = await client.get(
            "https://maps.googleapis.com/maps/api/geocode/json",
            params={"address": address, "key": settings.google_maps_api_key},
            timeout=10.0,
        )
        response.raise_for_status()
        data = response.json()
    except (httpx.HTTPError, ValueError):
        return None

    if data.get("status") != "OK" or not data.get("results"):
        return None

    loc = data["results"][0]["geometry"]["location"]
    return (loc["lat"], loc["lng"])


async def _geocode_nominatim(address: str, client: httpx.AsyncClient) -> tuple[float, float] | None:
    normalized = _normalize(address)

    coords = await _query_nominatim(
        {"q": normalized, "format": "json", "limit": 1, "countrycodes": "br"},
        client,
    )

    if coords is None:
        await asyncio.sleep(1.0)
        structured = _parse_structured(normalized)
        if structured:
            coords = await _query_nominatim(structured, client)

    return coords


async def geocode(address: str, client: httpx.AsyncClient) -> tuple[float, float] | None:
    if address in _cache:
        return _cache[address]

    if settings.google_maps_api_key:
        coords = await _geocode_google(address, client)
    else:
        coords = await _geocode_nominatim(address, client)

    _cache[address] = coords
    return coords


async def autocomplete_address(query: str) -> list[str]:
    if not settings.google_maps_api_key:
        return []
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(
                "https://maps.googleapis.com/maps/api/place/autocomplete/json",
                params={
                    "input": query,
                    "key": settings.google_maps_api_key,
                    "language": "pt-BR",
                    "components": "country:br",
                },
                timeout=5.0,
            )
            data = resp.json()
        except (httpx.HTTPError, ValueError):
            return []
    if data.get("status") not in ("OK", "ZERO_RESULTS"):
        return []
    return [p["description"] for p in data.get("predictions", [])]


async def reverse_geocode(lat: float, lng: float) -> "str | None":
    async with httpx.AsyncClient() as client:
        if settings.google_maps_api_key:
            try:
                response = await client.get(
                    "https://maps.googleapis.com/maps/api/geocode/json",
                    params={"latlng": f"{lat},{lng}", "key": settings.google_maps_api_key, "language": "pt-BR"},
                    timeout=10.0,
                )
                data = response.json()
            except (httpx.HTTPError, ValueError):
                return None
            if data.get("status") == "OK" and data.get("results"):
                return data["results"][0]["formatted_address"]
        else:
            try:
                response = await client.get(
                    f"{settings.nominatim_base_url}/reverse",
                    params={"lat": lat, "lon": lng, "format": "json"},
                    headers={"User-Agent": settings.nominatim_user_agent},
                    timeout=10.0,
                )
                data = response.json()
            except (httpx.HTTPError, ValueError):
                return None
            if "display_name" in data:
                return data["display_name"]
    return None


async def geocode_all(
    addresses: list[str],
) -> tuple[dict[str, tuple[float, float]], list[str]]:
    """Returns (resolved: {address -> (lat, lng)}, failures: [address])."""
    resolved: dict[str, tuple[float, float]] = {}
    failures: list[str] = []

    async with httpx.AsyncClient() as client:
        if settings.google_maps_api_key:
            # Google Maps has no strict rate limit: geocode all in parallel
            results = await asyncio.gather(*(geocode(a, client) for a in addresses))
            for address, result in zip(addresses, results):
                if result is None:
                    failures.append(address)
                else:
                    resolved[address] = result
        else:
            # Nominatim usage policy: max 1 request/second — must stay sequential
            for address in addresses:
                result = await geocode(address, client)
                if result is None:
                    failures.append(address)
                else:
                    resolved[address] = result
                await asyncio.sleep(1.0)

    return resolved, failures
