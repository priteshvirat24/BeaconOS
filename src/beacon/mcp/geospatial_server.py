"""Beacon Command — Geospatial MCP Server.

Provides geocoding, distance, and routing tools using free providers.
"""

from __future__ import annotations

import json
import math
from typing import Optional

import httpx
from mcp.server.fastmcp import FastMCP
from tenacity import retry, stop_after_attempt, wait_exponential

mcp = FastMCP("Beacon Geospatial Server")


@mcp.tool()
async def geo_geocode(query: str) -> str:
    """Geocode a location name to coordinates using Nominatim.

    Args:
        query: Location name or address to geocode
    """
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.get(
            "https://nominatim.openstreetmap.org/search",
            params={"q": query, "format": "json", "limit": 5},
            headers={"User-Agent": "BeaconCommand/1.0"},
        )
        response.raise_for_status()
        results = response.json()

    if not results:
        return json.dumps({"error": "No results found", "query": query})

    return json.dumps([
        {
            "name": r.get("display_name"),
            "latitude": float(r.get("lat", 0)),
            "longitude": float(r.get("lon", 0)),
            "type": r.get("type"),
            "importance": r.get("importance"),
            "bounding_box": r.get("boundingbox"),
        }
        for r in results
    ], indent=2)


@mcp.tool()
async def geo_reverse_geocode(latitude: float, longitude: float) -> str:
    """Reverse geocode coordinates to a location name.

    Args:
        latitude: Latitude coordinate
        longitude: Longitude coordinate
    """
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.get(
            "https://nominatim.openstreetmap.org/reverse",
            params={"lat": latitude, "lon": longitude, "format": "json"},
            headers={"User-Agent": "BeaconCommand/1.0"},
        )
        response.raise_for_status()
        result = response.json()

    return json.dumps({
        "name": result.get("display_name"),
        "address": result.get("address", {}),
        "latitude": latitude,
        "longitude": longitude,
    }, indent=2)


@mcp.tool()
async def geo_distance(
    lat1: float, lon1: float,
    lat2: float, lon2: float,
) -> str:
    """Calculate the great-circle distance between two points.

    Args:
        lat1: Latitude of point 1
        lon1: Longitude of point 1
        lat2: Latitude of point 2
        lon2: Longitude of point 2
    """
    # Haversine formula
    R = 6371.0  # Earth radius in km
    lat1_r, lat2_r = math.radians(lat1), math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)

    a = math.sin(dlat / 2) ** 2 + math.cos(lat1_r) * math.cos(lat2_r) * math.sin(dlon / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    distance = R * c

    return json.dumps({
        "distance_km": round(distance, 2),
        "distance_miles": round(distance * 0.621371, 2),
        "from": {"latitude": lat1, "longitude": lon1},
        "to": {"latitude": lat2, "longitude": lon2},
    }, indent=2)


@mcp.tool()
async def geo_route_status(
    start_lat: float, start_lon: float,
    end_lat: float, end_lon: float,
) -> str:
    """Get routing information between two points using OSRM.

    Args:
        start_lat: Start latitude
        start_lon: Start longitude
        end_lat: End latitude
        end_lon: End longitude
    """
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.get(
                f"http://router.project-osrm.org/route/v1/driving/"
                f"{start_lon},{start_lat};{end_lon},{end_lat}",
                params={"overview": "false", "alternatives": "false"},
            )
            response.raise_for_status()
            data = response.json()

        if data.get("code") != "Ok" or not data.get("routes"):
            return json.dumps({"error": "No route found", "code": data.get("code")})

        route = data["routes"][0]
        return json.dumps({
            "distance_km": round(route["distance"] / 1000, 2),
            "duration_minutes": round(route["duration"] / 60, 1),
            "status": "available",
        }, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e), "status": "unavailable"})


@mcp.tool()
async def geo_affected_area(
    latitude: float,
    longitude: float,
    radius_km: float,
) -> str:
    """Estimate the affected area around a point.

    Args:
        latitude: Center latitude
        longitude: Center longitude
        radius_km: Radius in kilometers
    """
    area_km2 = math.pi * radius_km ** 2

    # Simple reverse geocode of the center
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(
                "https://nominatim.openstreetmap.org/reverse",
                params={"lat": latitude, "lon": longitude, "format": "json", "zoom": 8},
                headers={"User-Agent": "BeaconCommand/1.0"},
            )
            center_info = response.json() if response.status_code == 200 else {}
    except Exception:
        center_info = {}

    return json.dumps({
        "center": {"latitude": latitude, "longitude": longitude},
        "radius_km": radius_km,
        "area_km2": round(area_km2, 1),
        "center_location": center_info.get("display_name", "Unknown"),
        "bounding_box": {
            "min_lat": latitude - radius_km / 111.0,
            "max_lat": latitude + radius_km / 111.0,
            "min_lon": longitude - radius_km / (111.0 * math.cos(math.radians(latitude))),
            "max_lon": longitude + radius_km / (111.0 * math.cos(math.radians(latitude))),
        },
    }, indent=2)


if __name__ == "__main__":
    mcp.run()
