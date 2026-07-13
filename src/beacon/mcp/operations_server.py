"""Beacon Command — Operations MCP Server.

Provides tools for crisis operations, task management, and decision tracking.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Optional

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("Beacon Operations Server")


@mcp.tool()
async def ops_get_crisis_status(crisis_id: str) -> str:
    """Get comprehensive crisis status.

    Args:
        crisis_id: UUID of the crisis
    """
    from beacon.db import get_session
    from beacon.db.models.crisis import Crisis
    from beacon.db.models.evidence import Evidence
    from beacon.db.models.claims import Claim
    from beacon.db.models.tasks import Task
    from beacon.db.models.missions import Mission
    from sqlalchemy import select, func

    cid = uuid.UUID(crisis_id)

    async with get_session() as session:
        crisis_r = await session.execute(select(Crisis).where(Crisis.id == cid))
        crisis = crisis_r.scalar_one_or_none()
        if not crisis:
            return json.dumps({"error": "Crisis not found"})

        ev_count = (await session.execute(
            select(func.count()).select_from(Evidence).where(Evidence.crisis_id == cid)
        )).scalar() or 0

        claim_count = (await session.execute(
            select(func.count()).select_from(Claim).where(Claim.crisis_id == cid)
        )).scalar() or 0

        active_tasks = (await session.execute(
            select(func.count()).select_from(Task).where(
                Task.crisis_id == cid,
                Task.status.in_(["assigned", "in_progress", "at_risk"]),
            )
        )).scalar() or 0

        running_missions = (await session.execute(
            select(func.count()).select_from(Mission).where(
                Mission.crisis_id == cid,
                Mission.status.in_(["running", "scheduled"]),
            )
        )).scalar() or 0

    return json.dumps({
        "crisis_id": crisis_id,
        "title": crisis.title,
        "status": crisis.status,
        "severity": crisis.severity,
        "severity_score": crisis.severity_score,
        "location": crisis.primary_location_name,
        "slack_channel": crisis.slack_channel_id,
        "evidence_count": ev_count,
        "claim_count": claim_count,
        "active_tasks": active_tasks,
        "running_missions": running_missions,
        "started_at": crisis.started_at.isoformat() if crisis.started_at else None,
    }, indent=2)


@mcp.tool()
async def ops_list_tasks(
    crisis_id: str,
    status: str | None = None,
    limit: int = 20,
) -> str:
    """List operational tasks for a crisis.

    Args:
        crisis_id: UUID of the crisis
        status: Optional status filter
        limit: Maximum results
    """
    from beacon.db import get_session
    from beacon.db.models.tasks import Task
    from sqlalchemy import select

    async with get_session() as session:
        query = (
            select(Task)
            .where(Task.crisis_id == uuid.UUID(crisis_id))
            .order_by(Task.priority.desc())
            .limit(limit)
        )
        if status:
            query = query.where(Task.status == status)
        result = await session.execute(query)
        tasks = result.scalars().all()

    return json.dumps([
        {
            "id": str(t.id),
            "title": t.title,
            "status": t.status,
            "priority": t.priority,
            "assigned_to": t.assigned_name,
            "deadline": t.deadline.isoformat() if t.deadline else None,
            "is_blocked": bool(t.is_blocked_reason),
            "blocked_reason": t.is_blocked_reason,
        }
        for t in tasks
    ], indent=2)


@mcp.tool()
async def ops_list_decisions(crisis_id: str) -> str:
    """List decisions made for a crisis.

    Args:
        crisis_id: UUID of the crisis
    """
    from beacon.db import get_session
    from beacon.db.models.decisions import Decision
    from sqlalchemy import select

    async with get_session() as session:
        result = await session.execute(
            select(Decision)
            .where(Decision.crisis_id == uuid.UUID(crisis_id))
            .order_by(Decision.created_at.desc())
        )
        decisions = result.scalars().all()

    return json.dumps([
        {
            "id": str(d.id),
            "decision": d.decision[:500],
            "rationale": d.rationale[:500],
            "status": d.status,
            "approved_by": d.approved_by,
        }
        for d in decisions
    ], indent=2)


@mcp.tool()
async def ops_list_commitments(crisis_id: str) -> str:
    """List detected commitments for a crisis.

    Args:
        crisis_id: UUID of the crisis
    """
    from beacon.db import get_session
    from beacon.db.models.decisions import Commitment
    from sqlalchemy import select

    async with get_session() as session:
        result = await session.execute(
            select(Commitment)
            .where(Commitment.crisis_id == uuid.UUID(crisis_id))
            .order_by(Commitment.created_at.desc())
        )
        commitments = result.scalars().all()

    return json.dumps([
        {
            "id": str(c.id),
            "statement": c.statement,
            "committer": c.committer_name,
            "type": c.commitment_type,
            "status": c.status,
            "deadline": c.deadline.isoformat() if c.deadline else None,
            "task_id": str(c.task_id) if c.task_id else None,
            "slack_permalink": c.slack_permalink,
        }
        for c in commitments
    ], indent=2)


@mcp.tool()
async def ops_get_pending_approvals(crisis_id: str | None = None) -> str:
    """Get pending approval requests.

    Args:
        crisis_id: Optional crisis filter
    """
    from beacon.db import get_session
    from beacon.db.models.decisions import Approval
    from sqlalchemy import select

    async with get_session() as session:
        query = (
            select(Approval)
            .where(Approval.decision == "pending")
            .order_by(Approval.created_at.desc())
        )
        if crisis_id:
            query = query.where(Approval.crisis_id == uuid.UUID(crisis_id))
        result = await session.execute(query)
        approvals = result.scalars().all()

    return json.dumps([
        {
            "id": str(a.id),
            "action": a.action[:500],
            "target_type": a.target_object_type,
            "authority_required": a.authority_required,
            "created_at": a.created_at.isoformat() if hasattr(a, "created_at") else None,
        }
        for a in approvals
    ], indent=2)


if __name__ == "__main__":
    mcp.run()
