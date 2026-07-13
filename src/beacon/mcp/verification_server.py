"""Beacon Command — Verification MCP Server.

Provides tools for claim verification, source comparison, and entity resolution.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("Beacon Verification Server")


@mcp.tool()
async def verification_verify_claim(claim_id: str) -> str:
    """Verify a claim by checking its supporting evidence freshness and consistency.

    Args:
        claim_id: UUID of the claim to verify
    """
    from beacon.db import get_session
    from beacon.db.models.claims import Claim
    from beacon.db.models.evidence import ClaimEvidenceLink, Evidence
    from sqlalchemy import select

    async with get_session() as session:
        # Get claim
        result = await session.execute(
            select(Claim).where(Claim.id == uuid.UUID(claim_id))
        )
        claim = result.scalar_one_or_none()
        if not claim:
            return json.dumps({"error": "Claim not found"})

        # Get supporting evidence
        links_result = await session.execute(
            select(ClaimEvidenceLink, Evidence)
            .join(Evidence, ClaimEvidenceLink.evidence_id == Evidence.id)
            .where(ClaimEvidenceLink.claim_id == claim.id)
        )
        links = links_result.all()

    now = datetime.now(timezone.utc)
    supporting = []
    contradicting = []

    for link, evidence in links:
        age_minutes = (now - evidence.observed_at).total_seconds() / 60
        is_fresh = age_minutes < 60  # Default freshness window

        entry = {
            "evidence_id": str(evidence.id),
            "source_type": evidence.source_type,
            "reliability_score": evidence.reliability_score,
            "age_minutes": round(age_minutes, 1),
            "is_fresh": is_fresh,
            "relationship": link.relationship_type,
        }

        if link.relationship_type == "supports":
            supporting.append(entry)
        else:
            contradicting.append(entry)

    # Compute verification assessment
    avg_reliability = (
        sum(s["reliability_score"] for s in supporting) / len(supporting)
        if supporting else 0
    )
    all_fresh = all(s["is_fresh"] for s in supporting) if supporting else False

    return json.dumps({
        "claim_id": claim_id,
        "statement": claim.statement,
        "current_status": claim.epistemic_status,
        "supporting_evidence_count": len(supporting),
        "contradicting_evidence_count": len(contradicting),
        "average_reliability": round(avg_reliability, 3),
        "all_evidence_fresh": all_fresh,
        "supporting": supporting,
        "contradicting": contradicting,
        "verification_assessment": (
            "verified" if avg_reliability > 0.7 and all_fresh and not contradicting
            else "contested" if contradicting
            else "stale" if not all_fresh
            else "weak" if avg_reliability < 0.4
            else "supported"
        ),
    }, indent=2)


@mcp.tool()
async def verification_compare_sources(
    evidence_id_a: str,
    evidence_id_b: str,
) -> str:
    """Compare two evidence items for consistency.

    Args:
        evidence_id_a: UUID of first evidence item
        evidence_id_b: UUID of second evidence item
    """
    from beacon.db import get_session
    from beacon.db.models.evidence import Evidence
    from sqlalchemy import select

    async with get_session() as session:
        result_a = await session.execute(
            select(Evidence).where(Evidence.id == uuid.UUID(evidence_id_a))
        )
        ev_a = result_a.scalar_one_or_none()

        result_b = await session.execute(
            select(Evidence).where(Evidence.id == uuid.UUID(evidence_id_b))
        )
        ev_b = result_b.scalar_one_or_none()

    if not ev_a or not ev_b:
        return json.dumps({"error": "One or both evidence items not found"})

    # Compare attributes
    time_delta = None
    if ev_a.observed_at and ev_b.observed_at:
        time_delta = abs((ev_a.observed_at - ev_b.observed_at).total_seconds() / 60)

    return json.dumps({
        "evidence_a": {
            "id": str(ev_a.id),
            "source_type": ev_a.source_type,
            "source_provider": ev_a.source_provider,
            "observed_at": ev_a.observed_at.isoformat() if ev_a.observed_at else None,
            "reliability": ev_a.reliability_score,
            "content_preview": ev_a.normalized_content[:500],
        },
        "evidence_b": {
            "id": str(ev_b.id),
            "source_type": ev_b.source_type,
            "source_provider": ev_b.source_provider,
            "observed_at": ev_b.observed_at.isoformat() if ev_b.observed_at else None,
            "reliability": ev_b.reliability_score,
            "content_preview": ev_b.normalized_content[:500],
        },
        "comparison": {
            "same_source_type": ev_a.source_type == ev_b.source_type,
            "same_provider": ev_a.source_provider == ev_b.source_provider,
            "time_delta_minutes": round(time_delta, 1) if time_delta else None,
            "same_content_hash": ev_a.raw_content_hash == ev_b.raw_content_hash,
        },
    }, indent=2)


@mcp.tool()
async def verification_check_freshness(claim_id: str, max_age_minutes: int = 60) -> str:
    """Check if a claim's evidence is still fresh.

    Args:
        claim_id: UUID of the claim
        max_age_minutes: Maximum age in minutes for evidence to be considered fresh
    """
    from beacon.db import get_session
    from beacon.db.models.claims import Claim
    from beacon.db.models.evidence import ClaimEvidenceLink, Evidence
    from sqlalchemy import select

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(minutes=max_age_minutes)

    async with get_session() as session:
        result = await session.execute(
            select(Evidence)
            .join(ClaimEvidenceLink, ClaimEvidenceLink.evidence_id == Evidence.id)
            .where(ClaimEvidenceLink.claim_id == uuid.UUID(claim_id))
        )
        evidence_items = result.scalars().all()

    fresh = [e for e in evidence_items if e.observed_at >= cutoff]
    stale = [e for e in evidence_items if e.observed_at < cutoff]

    return json.dumps({
        "claim_id": claim_id,
        "max_age_minutes": max_age_minutes,
        "total_evidence": len(evidence_items),
        "fresh_count": len(fresh),
        "stale_count": len(stale),
        "is_fresh": len(stale) == 0 and len(fresh) > 0,
        "oldest_evidence_age_minutes": round(
            max((now - e.observed_at).total_seconds() / 60 for e in evidence_items), 1
        ) if evidence_items else None,
        "newest_evidence_age_minutes": round(
            min((now - e.observed_at).total_seconds() / 60 for e in evidence_items), 1
        ) if evidence_items else None,
    }, indent=2)


@mcp.tool()
async def verification_search_contradictions(crisis_id: str) -> str:
    """Search for contradictions in a crisis's claims.

    Args:
        crisis_id: UUID of the crisis
    """
    from beacon.db import get_session
    from beacon.db.models.claims import Contradiction
    from sqlalchemy import select

    async with get_session() as session:
        result = await session.execute(
            select(Contradiction)
            .where(Contradiction.crisis_id == uuid.UUID(crisis_id))
            .order_by(Contradiction.created_at.desc())
        )
        contradictions = result.scalars().all()

    return json.dumps([
        {
            "id": str(c.id),
            "description": c.description,
            "status": c.status,
            "severity": c.severity,
            "is_decision_critical": c.is_decision_critical,
            "claim_a_id": str(c.claim_a_id) if c.claim_a_id else None,
            "claim_b_id": str(c.claim_b_id) if c.claim_b_id else None,
            "resolution": c.resolution,
        }
        for c in contradictions
    ], indent=2)


@mcp.tool()
async def verification_resolve_entity(name: str, entity_type: str = "any") -> str:
    """Resolve an entity name to known actors, resources, or locations.

    Args:
        name: Entity name to resolve
        entity_type: Type filter (actor, resource, location, any)
    """
    from beacon.db import get_session
    from beacon.db.models.actors import Actor
    from beacon.db.models.resources import Resource
    from beacon.db.models.core import Location
    from sqlalchemy import select, or_

    matches = []

    async with get_session() as session:
        if entity_type in ("actor", "any"):
            result = await session.execute(
                select(Actor).where(
                    Actor.name.ilike(f"%{name}%")
                ).limit(5)
            )
            for actor in result.scalars().all():
                matches.append({
                    "type": "actor",
                    "id": str(actor.id),
                    "name": actor.name,
                    "role": actor.role,
                    "organization": actor.organization_name,
                })

        if entity_type in ("resource", "any"):
            result = await session.execute(
                select(Resource).where(
                    Resource.name.ilike(f"%{name}%")
                ).limit(5)
            )
            for res in result.scalars().all():
                matches.append({
                    "type": "resource",
                    "id": str(res.id),
                    "name": res.name,
                    "resource_type": res.resource_type,
                    "location": res.location_name,
                })

        if entity_type in ("location", "any"):
            result = await session.execute(
                select(Location).where(
                    Location.name.ilike(f"%{name}%")
                ).limit(5)
            )
            for loc in result.scalars().all():
                matches.append({
                    "type": "location",
                    "id": str(loc.id),
                    "name": loc.name,
                    "country": loc.country,
                    "latitude": loc.latitude,
                    "longitude": loc.longitude,
                })

    return json.dumps({"query": name, "matches": matches}, indent=2)


if __name__ == "__main__":
    mcp.run()
