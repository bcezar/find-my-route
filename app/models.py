from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class RouteRequest(BaseModel):
    addresses: list[str] = Field(..., min_length=2, max_length=50)
    origin: Optional[str] = None
    destination: Optional[str] = None


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
