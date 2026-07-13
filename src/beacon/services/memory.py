"""Beacon Command — Decision Ledger & Memory Services."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import select

from beacon.db import get_session
from beacon.db.models.decisions import Decision
from beacon.db.models.memory import IncidentEpisode, LessonProposal, Procedure, ProcedureVersion
from beacon.events import event_publisher
from beacon.logging import get_logger

logger = get_logger(__name__)


class DecisionLedger:
    """Immutable decision record management."""

    async def record_decision(
        self,
        crisis_id: uuid.UUID,
        decision_text: str,
        rationale: str,
        *,
        alternatives: Optional[list[dict]] = None,
        supporting_claim_ids: Optional[list[str]] = None,
        evidence_ids: Optional[list[str]] = None,
        risks: Optional[list[str]] = None,
        approved_by: Optional[str] = None,
        supersedes_id: Optional[uuid.UUID] = None,
    ) -> uuid.UUID:
        """Record a decision with full evidence chain."""
        async with get_session() as session:
            decision = Decision(
                crisis_id=crisis_id,
                decision=decision_text,
                rationale=rationale,
                alternatives=alternatives,
                supporting_claim_ids=supporting_claim_ids,
                evidence_ids=evidence_ids,
                risks=risks,
                approved_by=approved_by,
                approved_at=datetime.now(timezone.utc) if approved_by else None,
                supersedes_id=supersedes_id,
                status="active",
            )
            session.add(decision)
            await session.flush()

            # Supersede old decision if applicable
            if supersedes_id:
                old = await session.execute(
                    select(Decision).where(Decision.id == supersedes_id)
                )
                old_decision = old.scalar_one_or_none()
                if old_decision:
                    old_decision.status = "superseded"

            await event_publisher.publish(
                "decision.created",
                {
                    "decision_id": str(decision.id),
                    "decision": decision_text[:500],
                    "supersedes": str(supersedes_id) if supersedes_id else None,
                },
                crisis_id=crisis_id,
            )
            return decision.id

    async def get_decision_chain(self, crisis_id: uuid.UUID) -> list[dict[str, Any]]:
        """Get the full decision chain for a crisis."""
        async with get_session() as session:
            result = await session.execute(
                select(Decision)
                .where(Decision.crisis_id == crisis_id)
                .order_by(Decision.created_at.asc())
            )
            decisions = result.scalars().all()

        return [
            {
                "id": str(d.id),
                "decision": d.decision,
                "rationale": d.rationale,
                "status": d.status,
                "approved_by": d.approved_by,
                "supersedes": str(d.supersedes_id) if d.supersedes_id else None,
                "created_at": d.created_at.isoformat() if hasattr(d, 'created_at') else None,
            }
            for d in decisions
        ]


decision_ledger = DecisionLedger()


class EpisodicMemory:
    """Manages incident episodes for organizational learning."""

    async def create_episode(
        self,
        crisis_id: uuid.UUID,
        event_summary: str,
        hazard_type: str,
    ) -> uuid.UUID:
        """Create an incident episode record."""
        async with get_session() as session:
            episode = IncidentEpisode(
                crisis_id=crisis_id,
                event_summary=event_summary,
                hazard_type=hazard_type,
                status="draft",
            )
            session.add(episode)
            await session.flush()
            return episode.id

    async def search_similar(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
        """Search for similar past incidents (placeholder for vector search)."""
        async with get_session() as session:
            result = await session.execute(
                select(IncidentEpisode)
                .where(IncidentEpisode.status == "finalized")
                .order_by(IncidentEpisode.created_at.desc())
                .limit(limit)
            )
            episodes = result.scalars().all()

        return [
            {
                "id": str(e.id),
                "crisis_id": str(e.crisis_id),
                "summary": e.event_summary[:500],
                "hazard_type": e.hazard_type,
                "lessons": e.lessons or [],
            }
            for e in episodes
        ]


class ProceduralMemory:
    """Manages standard operating procedures."""

    async def get_procedures(self, category: Optional[str] = None) -> list[dict[str, Any]]:
        """Get active procedures."""
        async with get_session() as session:
            query = select(Procedure).where(Procedure.is_active == True)
            if category:
                query = query.where(Procedure.category == category)
            result = await session.execute(query)
            procedures = result.scalars().all()

        return [
            {
                "id": str(p.id),
                "name": p.name,
                "category": p.category,
                "description": p.description,
                "version": p.current_version,
            }
            for p in procedures
        ]

    async def propose_lesson(
        self,
        crisis_id: uuid.UUID,
        lesson: str,
        category: str,
        evidence_ids: Optional[list[str]] = None,
    ) -> uuid.UUID:
        """Propose a lesson from after-action analysis."""
        async with get_session() as session:
            proposal = LessonProposal(
                crisis_id=crisis_id,
                lesson=lesson,
                category=category,
                evidence_ids=evidence_ids,
                status="proposed",
            )
            session.add(proposal)
            await session.flush()

            await event_publisher.publish(
                "lesson.proposed",
                {"lesson_id": str(proposal.id), "lesson": lesson[:500]},
                crisis_id=crisis_id,
            )
            return proposal.id


episodic_memory = EpisodicMemory()
procedural_memory = ProceduralMemory()
