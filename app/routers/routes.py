from typing import Optional

from fastapi import APIRouter, Body, HTTPException, Query as QueryParam, Request

from app import storage
from app.limiter import limiter
from app.models import Coordinates, OriginInfo, RouteRequest, RouteResponse, RouteStop, SaveRouteRequest
from app.services import distance, geocoding, optimizer

router = APIRouter()


@router.get("/autocomplete")
@limiter.limit("120/minute")
async def autocomplete(request: Request, q: str = QueryParam(..., min_length=3)):
    suggestions = await geocoding.autocomplete_address(q)
    return {"suggestions": suggestions}


@router.post("/shorten")
@limiter.limit("20/minute")
async def shorten_route(request: Request, body: RouteRequest = Body(...)):
    state = {"addresses": body.addresses}
    if body.origin:      state["origin"]      = body.origin
    if body.destination: state["destination"] = body.destination
    code = await storage.save_route(state)
    return {"path": f"/r/{code}"}


@router.post("/routes/save")
@limiter.limit("20/minute")
async def save_route(request: Request, body: SaveRouteRequest = Body(...)):
    code = await storage.save_result(
        body.name,
        body.result.model_dump(),
        body.inputs.model_dump(),
    )
    return {"code": code, "path": f"/s/{code}"}


@router.get("/routes/saved/{code}")
async def get_saved_route(code: str):
    result = await storage.get_result(code)
    if result is None:
        raise HTTPException(status_code=404, detail="Rota não encontrada.")
    return result


@router.get("/reverse")
@limiter.limit("30/minute")
async def reverse_geocode(request: Request, lat: float = QueryParam(...), lng: float = QueryParam(...)):
    address = await geocoding.reverse_geocode(lat, lng)
    if address is None:
        raise HTTPException(status_code=404, detail="Could not reverse geocode coordinates.")
    return {"address": address}


@router.post("/routes/optimize", response_model=RouteResponse)
@limiter.limit("20/minute")
async def optimize_route(request: Request, body: RouteRequest = Body(...)):
    # Collect all addresses that need geocoding (no duplicates)
    to_geocode = list(dict.fromkeys(
        ([body.origin] if body.origin else [])
        + body.addresses
        + ([body.destination] if body.destination else [])
    ))
    resolved, failures = await geocoding.geocode_all(to_geocode)

    if body.origin and body.origin not in resolved:
        raise HTTPException(status_code=422, detail="Origin address could not be geocoded.")

    if body.destination and body.destination not in resolved:
        raise HTTPException(status_code=422, detail="Destination address could not be geocoded.")

    resolved_addresses = [a for a in body.addresses if a in resolved]

    if len(resolved_addresses) < 2:
        raise HTTPException(
            status_code=400,
            detail="At least 2 addresses must be successfully geocoded to optimize a route.",
        )

    coords = [resolved[a] for a in resolved_addresses]

    # Build coordinate list for the matrix:
    # [origin?] + addresses + [destination?]
    # When origin == destination (return to start), we duplicate the node so
    # OR-Tools can treat start and end as distinct indices.
    all_coords = (
        ([resolved[body.origin]] if body.origin else [])
        + coords
        + ([resolved[body.destination]] if body.destination else [])
    )

    n = len(all_coords)
    start_idx = 0 if body.origin else None
    end_idx = n - 1 if body.destination else None

    matrix = await distance.build_distance_matrix(all_coords)

    full_order = optimizer.optimize_route(
        matrix,
        start_index=start_idx or 0,
        end_index=end_idx,
    )

    # Slice the fixed endpoints out of the order to build the middle stops
    first = 1 if body.origin else 0
    last = len(full_order) - 1 if body.destination else len(full_order)
    middle_order = full_order[first:last]

    # Map matrix indices back to resolved_addresses indices
    origin_offset = 1 if body.origin else 0
    order = [i - origin_offset for i in middle_order]

    total_km = sum(matrix[full_order[i]][full_order[i + 1]] for i in range(len(full_order) - 1))

    optimized_route = [
        RouteStop(
            order=i + 1,
            original_address=resolved_addresses[idx],
            coordinates=Coordinates(lat=coords[idx][0], lng=coords[idx][1]),
            leg_distance_km=round(matrix[full_order[first + i]][full_order[first + i + 1]], 2)
                if (first + i + 1) < len(full_order) else None,
        )
        for i, idx in enumerate(order)
    ]

    def _make_endpoint_info(address: str) -> OriginInfo:
        lat, lng = resolved[address]
        return OriginInfo(address=address, coordinates=Coordinates(lat=lat, lng=lng))

    origin_info = _make_endpoint_info(body.origin) if body.origin else None
    destination_info = _make_endpoint_info(body.destination) if body.destination else None

    return RouteResponse(
        optimized_route=optimized_route,
        total_distance_km=round(total_km, 2),
        geocoding_failures=failures,
        origin=origin_info,
        destination=destination_info,
        maps_url=_build_maps_url(origin_info, destination_info, optimized_route),
    )


def _build_maps_url(
    origin: Optional[OriginInfo],
    destination: Optional[OriginInfo],
    route_stops: list,
) -> Optional[str]:
    if not route_stops:
        return None

    def coord(c: Coordinates) -> str:
        return f"{c.lat},{c.lng}"

    if origin:
        url_origin = coord(origin.coordinates)
        if destination:
            url_destination = coord(destination.coordinates)
            waypoint_stops = route_stops
        else:
            url_destination = coord(route_stops[-1].coordinates)
            waypoint_stops = route_stops[:-1]
    else:
        url_origin = coord(route_stops[0].coordinates)
        if destination:
            url_destination = coord(destination.coordinates)
            waypoint_stops = route_stops[1:]
        else:
            url_destination = coord(route_stops[-1].coordinates)
            waypoint_stops = route_stops[1:-1]

    base = (
        f"https://www.google.com/maps/dir/?api=1"
        f"&origin={url_origin}"
        f"&destination={url_destination}"
        f"&travelmode=driving"
    )

    # Google Maps URL supports up to 23 waypoints
    if waypoint_stops:
        wps = waypoint_stops[:23]
        base += "&waypoints=" + "|".join(coord(s.coordinates) for s in wps)

    return base
