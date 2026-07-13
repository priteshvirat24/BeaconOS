"""Beacon Command — Resource MCP Server.

Provides tools for querying resources, volunteers, and capabilities.
"""

from __future__ import annotations

import json
import uuid
from typing import Optional

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("Beacon Resource Server")


@mcp.tool()
async def resource_list(
    resource_type: str | None = None,
    status: str = "available",
    limit: int = 20,
) -> str:
    """List operational resources.

    Args:
        resource_type: Filter by type (supply, vehicle, facility, personnel)
        status: Filter by status (available, deployed, unavailable)
        limit: Maximum results
    """
    from beacon.db import get_session
    from beacon.db.models.resources import Resource
    from sqlalchemy import select

    async with get_session() as session:
        query = select(Resource).where(Resource.status == status).limit(limit)
        if resource_type:
            query = query.where(Resource.resource_type == resource_type)
        result = await session.execute(query)
        resources = result.scalars().all()

    return json.dumps([
        {
            "id": str(r.id),
            "name": r.name,
            "type": r.resource_type,
            "category": r.category,
            "location": r.location_name,
            "latitude": r.latitude,
            "longitude": r.longitude,
            "total_capacity": r.total_capacity,
            "available_capacity": r.available_capacity,
            "unit": r.unit,
            "status": r.status,
            "is_verified": r.is_verified,
            "owner": r.organization_name,
        }
        for r in resources
    ], indent=2)


@mcp.tool()
async def resource_find_nearby(
    latitude: float,
    longitude: float,
    radius_km: float = 100,
    resource_type: str | None = None,
) -> str:
    """Find resources near a location.

    Args:
        latitude: Center latitude
        longitude: Center longitude
        radius_km: Search radius in km
        resource_type: Optional type filter
    """
    from beacon.db import get_session
    from beacon.db.models.resources import Resource
    from sqlalchemy import select, and_

    delta = radius_km / 111.0

    async with get_session() as session:
        query = select(Resource).where(
            and_(
                Resource.latitude.between(latitude - delta, latitude + delta),
                Resource.longitude.between(longitude - delta, longitude + delta),
                Resource.status == "available",
            )
        ).limit(50)
        if resource_type:
            query = query.where(Resource.resource_type == resource_type)
        result = await session.execute(query)
        resources = result.scalars().all()

    return json.dumps([
        {
            "id": str(r.id),
            "name": r.name,
            "type": r.resource_type,
            "location": r.location_name,
            "available_capacity": r.available_capacity,
            "distance_approx_km": round(
                ((r.latitude - latitude) ** 2 + (r.longitude - longitude) ** 2) ** 0.5 * 111, 1
            ) if r.latitude and r.longitude else None,
        }
        for r in resources
    ], indent=2)


@mcp.tool()
async def resource_list_volunteers(
    status: str = "available",
    skill: str | None = None,
    limit: int = 20,
) -> str:
    """List volunteers with optional skill filter.

    Args:
        status: Availability status
        skill: Skill to filter by
        limit: Maximum results
    """
    from beacon.db import get_session
    from beacon.db.models.actors import Volunteer
    from sqlalchemy import select

    async with get_session() as session:
        query = (
            select(Volunteer)
            .where(Volunteer.availability_status == status)
            .limit(limit)
        )
        result = await session.execute(query)
        volunteers = result.scalars().all()

    vols = []
    for v in volunteers:
        if skill and v.skills and skill.lower() not in [s.lower() for s in (v.skills or [])]:
            continue
        vols.append({
            "id": str(v.id),
            "name": v.display_name,
            "slack_user_id": v.slack_user_id,
            "status": v.availability_status,
            "skills": v.skills,
            "location": v.location,
        })

    return json.dumps(vols, indent=2)


@mcp.tool()
async def resource_check_constraints(crisis_id: str) -> str:
    """Check active constraints for a crisis.

    Args:
        crisis_id: UUID of the crisis
    """
    from beacon.db import get_session
    from beacon.db.models.resources import Constraint
    from sqlalchemy import select

    async with get_session() as session:
        result = await session.execute(
            select(Constraint)
            .where(Constraint.crisis_id == uuid.UUID(crisis_id))
            .order_by(Constraint.severity.desc())
        )
        constraints = result.scalars().all()

    return json.dumps([
        {
            "id": str(c.id),
            "name": c.name,
            "type": c.constraint_type,
            "description": c.description,
            "severity": c.severity,
            "is_hard": c.is_hard,
            "affects_resources": c.affects_resources,
            "affects_locations": c.affects_locations,
        }
        for c in constraints
    ], indent=2)


if __name__ == "__main__":
    mcp.run()
