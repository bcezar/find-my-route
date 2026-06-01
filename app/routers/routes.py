from typing import Optional

from fastapi import APIRouter, Body, HTTPException, Query as QueryParam, Request
from fastapi.responses import Response

from app import storage
from app.limiter import limiter
from app.models import Coordinates, MapImageRequest, OriginInfo, PolylineRequest, RouteRequest, RouteResponse, RouteStop, SaveRouteRequest
from app.services import directions, distance, geocoding, optimizer, static_maps

router = APIRouter()


@router.get("/autocomplete")
@limiter.limit("120/minute")
async def autocomplete(
    request: Request,
    q: str = QueryParam(..., min_length=3),
    lat: Optional[float] = QueryParam(None),
    lng: Optional[float] = QueryParam(None),
):
    suggestions = await geocoding.autocomplete_address(q, lat=lat, lng=lng)
    return {"suggestions": suggestions}


@router.get("/geocode")
@limiter.limit("30/minute")
async def geocode_address(request: Request, q: str = QueryParam(..., min_length=3)):
    coords = await geocoding.geocode(q)
    if coords is None:
        raise HTTPException(status_code=404, detail="Address not found.")
    lat, lng = coords
    return {"lat": lat, "lng": lng}


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


@router.post("/routes/polyline")
@limiter.limit("30/minute")
async def route_polyline(request: Request, body: PolylineRequest = Body(...)):
    pts = [(c.lat, c.lng) for c in body.points]
    path, encoded, error_status = await directions.get_route_polyline(pts)
    if path is None:
        raise HTTPException(status_code=503, detail=f"Could not retrieve road path: {error_status}")
    return {
        "path": [{"lat": lat, "lng": lng} for lat, lng in path],
        "encoded_polyline": encoded,
    }


@router.post("/routes/map-image")
@limiter.limit("20/minute")
async def route_map_image(request: Request, body: MapImageRequest = Body(...)):
    img = await static_maps.fetch_static_map(
        body.encoded_polyline,
        (body.origin.lat, body.origin.lng),
        (body.destination.lat, body.destination.lng),
    )
    if img is None:
        raise HTTPException(status_code=503, detail="Could not generate map image.")
    return Response(content=img, media_type="image/png")


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

    fixed_first = body.fixed_first
    fixed_last  = body.fixed_last

    if fixed_first and fixed_first not in resolved:
        raise HTTPException(status_code=422, detail="O endereço 'visitar primeiro' não pôde ser geocodificado.")
    if fixed_last and fixed_last not in resolved:
        raise HTTPException(status_code=422, detail="O endereço 'visitar por último' não pôde ser geocodificado.")

    # Reorder resolved_addresses: fixed_first leads, fixed_last trails
    _middle = [a for a in resolved_addresses if a != fixed_first and a != fixed_last]
    resolved_addresses = (
        ([fixed_first] if fixed_first else []) +
        _middle +
        ([fixed_last]  if fixed_last  else [])
    )
    coords = [resolved[a] for a in resolved_addresses]

    # Build full coordinate list for the distance matrix
    # [origin?] + [addresses] + [destination?]
    all_coords = (
        ([resolved[body.origin]]      if body.origin      else []) +
        coords +
        ([resolved[body.destination]] if body.destination else [])
    )
    n = len(all_coords)
    origin_offset = 1 if body.origin else 0

    matrix, dur_matrix = await distance.build_distance_matrix(all_coords)

    # When fixed_first + origin both exist: origin→fixed_first is a fixed prefix leg;
    # exclude origin from the optimizer so OR-Tools doesn't freely reorder it.
    # Symmetrically for fixed_last + destination.
    has_fixed_prefix = bool(body.origin and fixed_first)
    has_fixed_suffix = bool(body.destination and fixed_last)

    if has_fixed_prefix and has_fixed_suffix:
        opt_indices = list(range(origin_offset, n - 1))
    elif has_fixed_prefix:
        opt_indices = list(range(origin_offset, n))
    elif has_fixed_suffix:
        opt_indices = list(range(0, n - 1))
    else:
        opt_indices = list(range(n))

    opt_matrix = [[matrix[i][j] for j in opt_indices] for i in opt_indices]
    opt_end    = len(opt_indices) - 1 if (body.destination or fixed_last) else None

    opt_order = optimizer.optimize_route(opt_matrix, start_index=0, end_index=opt_end)

    # Reassemble full_order in all_coords indices, prepending/appending fixed legs
    full_order = (
        ([0] if has_fixed_prefix else []) +
        [opt_indices[i] for i in opt_order] +
        ([n - 1] if has_fixed_suffix else [])
    )

    # Slice the fixed endpoints out of the order to build the middle stops
    first = 1 if body.origin else 0
    last = len(full_order) - 1 if body.destination else len(full_order)
    middle_order = full_order[first:last]

    # Map all_coords indices back to resolved_addresses indices
    order = [i - origin_offset for i in middle_order]

    total_km = sum(matrix[full_order[i]][full_order[i + 1]] for i in range(len(full_order) - 1))
    total_dur = (
        sum(dur_matrix[full_order[i]][full_order[i + 1]] for i in range(len(full_order) - 1))
        if dur_matrix else None
    )

    optimized_route = [
        RouteStop(
            order=i + 1,
            original_address=resolved_addresses[idx],
            coordinates=Coordinates(lat=coords[idx][0], lng=coords[idx][1]),
            leg_distance_km=round(matrix[full_order[first + i]][full_order[first + i + 1]], 2)
                if (first + i + 1) < len(full_order) else None,
            leg_duration_min=round(dur_matrix[full_order[first + i]][full_order[first + i + 1]], 1)
                if dur_matrix and (first + i + 1) < len(full_order) else None,
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
        total_duration_min=round(total_dur, 1) if total_dur is not None else None,
    )


_MAPS_MAX_STOPS = 23  # Google Maps URL limit for intermediate waypoints


def _build_maps_url(
    origin: Optional[OriginInfo],
    destination: Optional[OriginInfo],
    route_stops: list,
) -> Optional[str]:
    if not route_stops:
        return None

    def coord(c: Coordinates) -> str:
        return f"{c.lat},{c.lng}"

    # Path-based format (/dir/LAT,LNG/LAT,LNG/...) shows each stop as an
    # individual field in Google Maps — the ?api=1&waypoints= format collapses
    # them into "N paradas" on mobile.
    points = []
    if origin:
        points.append(coord(origin.coordinates))
    for stop in route_stops[:_MAPS_MAX_STOPS]:
        points.append(coord(stop.coordinates))
    if destination:
        points.append(coord(destination.coordinates))

    return "https://www.google.com/maps/dir/" + "/".join(points) + "/"
