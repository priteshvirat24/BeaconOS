"""Beacon Command — Hazard MCP Server.

Real MCP server using the official SDK with FastMCP.
Provides tools for querying hazard events from the database.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from mcp.server.fastmcp import FastMCP

# Initialize the MCP server
mcp = FastMCP("Beacon Hazard Server")


@mcp.tool()
async def hazard_list_active_events(
    hazard_type: str | None = None,
    min_severity: float = 0.0,
    limit: int = 20,
) -> str:
    """List active hazard events from the database.

    Args:
        hazard_type: Filter by hazard type (earthquake, flood, cyclone, etc.)
        min_severity: Minimum severity score (0-10)
        limit: Maximum number of events to return
    """
    from beacon.db import get_session
    from beacon.db.models.crisis import HazardEvent
    from sqlalchemy import select

    async with get_session() as session:
        query = (
            select(HazardEvent)
            .where(HazardEvent.severity_score >= min_severity)
            .order_by(HazardEvent.created_at.desc())
            .limit(limit)
        )
        if hazard_type:
            query = query.where(HazardEvent.hazard_type == hazard_type)

        result = await session.execute(query)
        events = result.scalars().all()

    return json.dumps([
        {
            "event_id": str(e.id),
            "source_type": e.source_type,
            "source_event_id": e.source_event_id,
            "hazard_type": e.hazard_type,
            "title": e.title,
            "location": e.location_name,
            "latitude": e.latitude,
            "longitude": e.longitude,
            "magnitude": e.magnitude,
            "severity": e.severity,
            "severity_score": e.severity_score,
            "event_time": e.event_time.isoformat() if e.event_time else None,
            "tsunami_flag": e.tsunami_flag,
            "crisis_id": str(e.crisis_id) if e.crisis_id else None,
        }
        for e in events
    ], indent=2)


@mcp.tool()
async def hazard_get_event(event_id: str) -> str:
    """Get detailed information about a specific hazard event.

    Args:
        event_id: UUID of the hazard event
    """
    from beacon.db import get_session
    from beacon.db.models.crisis import HazardEvent
    from sqlalchemy import select

    async with get_session() as session:
        result = await session.execute(
            select(HazardEvent).where(HazardEvent.id == uuid.UUID(event_id))
        )
        event = result.scalar_one_or_none()

    if not event:
        return json.dumps({"error": "Event not found"})

    return json.dumps({
        "event_id": str(event.id),
        "source_type": event.source_type,
        "source_event_id": event.source_event_id,
        "hazard_type": event.hazard_type,
        "title": event.title,
        "description": event.description,
        "location": event.location_name,
        "latitude": event.latitude,
        "longitude": event.longitude,
        "depth_km": event.depth_km,
        "magnitude": event.magnitude,
        "severity": event.severity,
        "severity_score": event.severity_score,
        "alert_level": event.alert_level,
        "event_time": event.event_time.isoformat() if event.event_time else None,
        "tsunami_flag": event.tsunami_flag,
        "source_url": event.source_url,
        "crisis_id": str(event.crisis_id) if event.crisis_id else None,
        "raw_metadata": event.raw_metadata,
    }, indent=2, default=str)


@mcp.tool()
async def hazard_get_event_updates(source_event_id: str) -> str:
    """Get all updates for a hazard event by source event ID.

    Args:
        source_event_id: The source system's event identifier
    """
    from beacon.db import get_session
    from beacon.db.models.crisis import HazardEvent
    from sqlalchemy import select

    async with get_session() as session:
        result = await session.execute(
            select(HazardEvent)
            .where(HazardEvent.source_event_id == source_event_id)
            .order_by(HazardEvent.created_at.asc())
        )
        events = result.scalars().all()

    return json.dumps([
        {
            "event_id": str(e.id),
            "is_update": e.is_update,
            "magnitude": e.magnitude,
            "severity_score": e.severity_score,
            "updated_at": e.updated_at_source.isoformat() if e.updated_at_source else None,
        }
        for e in events
    ], indent=2)


@mcp.tool()
async def hazard_get_timeline(crisis_id: str) -> str:
    """Get a timeline of hazard events for a crisis.

    Args:
        crisis_id: UUID of the crisis
    """
    from beacon.db import get_session
    from beacon.db.models.crisis import HazardEvent
    from sqlalchemy import select

    async with get_session() as session:
        result = await session.execute(
            select(HazardEvent)
            .where(HazardEvent.crisis_id == uuid.UUID(crisis_id))
            .order_by(HazardEvent.event_time.asc())
        )
        events = result.scalars().all()

    return json.dumps([
        {
            "event_id": str(e.id),
            "title": e.title,
            "event_time": e.event_time.isoformat() if e.event_time else None,
            "magnitude": e.magnitude,
            "severity_score": e.severity_score,
        }
        for e in events
    ], indent=2)


@mcp.tool()
async def hazard_get_related_events(
    latitude: float,
    longitude: float,
    radius_km: float = 500,
    hours: int = 72,
) -> str:
    """Find hazard events near a geographic location within a time window.

    Args:
        latitude: Center latitude
        longitude: Center longitude
        radius_km: Search radius in kilometers
        hours: Time window in hours
    """
    from beacon.db import get_session
    from beacon.db.models.crisis import HazardEvent
    from sqlalchemy import select, and_
    from datetime import timedelta

    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

    async with get_session() as session:
        # Simple bounding box approximation (1 degree ≈ 111 km)
        delta = radius_km / 111.0
        result = await session.execute(
            select(HazardEvent)
            .where(
                and_(
                    HazardEvent.latitude.between(latitude - delta, latitude + delta),
                    HazardEvent.longitude.between(longitude - delta, longitude + delta),
                    HazardEvent.event_time >= cutoff,
                )
            )
            .order_by(HazardEvent.event_time.desc())
            .limit(50)
        )
        events = result.scalars().all()

    return json.dumps([
        {
            "event_id": str(e.id),
            "hazard_type": e.hazard_type,
            "title": e.title,
            "distance_approx_km": round(
                ((e.latitude - latitude) ** 2 + (e.longitude - longitude) ** 2) ** 0.5 * 111, 1
            ) if e.latitude and e.longitude else None,
            "event_time": e.event_time.isoformat() if e.event_time else None,
            "severity_score": e.severity_score,
        }
        for e in events
    ], indent=2)


if __name__ == "__main__":
    mcp.run()
