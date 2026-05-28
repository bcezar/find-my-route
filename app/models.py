from __future__ import annotations

from typing import Annotated, Optional

from pydantic import BaseModel, Field

Address = Annotated[str, Field(min_length=1, max_length=200)]


class RouteRequest(BaseModel):
    addresses: list[Address] = Field(..., min_length=2, max_length=50)
    origin: Optional[Address] = None
    destination: Optional[Address] = None


class Coordinates(BaseModel):
    lat: float
    lng: float


class OriginInfo(BaseModel):
    address: str
    coordinates: Coordinates


class RouteStop(BaseModel):
    order: int
    original_address: str
    coordinates: Coordinates


class RouteResponse(BaseModel):
    optimized_route: list[RouteStop]
    total_distance_km: float
    geocoding_failures: list[str]
    origin: Optional[OriginInfo] = None
    destination: Optional[OriginInfo] = None
    maps_url: Optional[str] = None
