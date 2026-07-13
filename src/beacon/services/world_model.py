"""Beacon Command — Crisis World Model Service.

Maintains the epistemic state of each crisis with version tracking.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import select, func, update

from beacon.db import get_session
from beacon.db.models.crisis import Crisis
from beacon.db.models.evidence import Evidence
from beacon.db.models.claims import Claim, Contradiction
from beacon.db.models.intelligence import IntelligenceGap, Hypothesis
from beacon.db.models.tasks import Task
from beacon.db.models.plans import ResponsePlan
from beacon.db.models.resources import Resource, Constraint
from beacon.db.models.events import StateRevision
from beacon.events import event_publisher
from beacon.logging import get_logger

logger = get_logger(__name__)


class CrisisWorldModelService:
    """Manages the world model state for a crisis.

    Provides read access to the current state, applies state patches,
    and publishes domain events for state transitions.
    """

    async def get_snapshot(self, crisis_id: uuid.UUID) -> dict[str, Any]:
        """Get a complete world model snapshot for a crisis."""
        async with get_session() as session:
            # Crisis
            crisis_r = await session.execute(
                select(Crisis).where(Crisis.id == crisis_id)
            )
            crisis = crisis_r.scalar_one_or_none()
            if not crisis:
                return {"error": "Crisis not found"}

            # Evidence
            evidence_r = await session.execute(
                select(Evidence)
                .where(Evidence.crisis_id == crisis_id)
                .order_by(Evidence.observed_at.desc())
                .limit(100)
            )
            evidence_items = evidence_r.scalars().all()

            # Claims
            claims_r = await session.execute(
                select(Claim)
                .where(Claim.crisis_id == crisis_id)
                .order_by(Claim.confidence.desc())
            )
            claims = claims_r.scalars().all()

            # Contradictions
            contras_r = await session.execute(
                select(Contradiction)
                .where(Contradiction.crisis_id == crisis_id)
                .where(Contradiction.status.in_(["detected", "investigating"]))
            )
            contradictions = contras_r.scalars().all()

            # Intelligence gaps
            gaps_r = await session.execute(
                select(IntelligenceGap)
                .where(IntelligenceGap.crisis_id == crisis_id)
                .where(IntelligenceGap.status.in_(["identified", "prioritized", "acquiring"]))
                .order_by(IntelligenceGap.priority.desc())
            )
            gaps = gaps_r.scalars().all()

            # Hypotheses
            hypos_r = await session.execute(
                select(Hypothesis)
                .where(Hypothesis.crisis_id == crisis_id)
                .where(Hypothesis.status == "active")
            )
            hypotheses = hypos_r.scalars().all()

            # Tasks
            tasks_r = await session.execute(
                select(Task)
                .where(Task.crisis_id == crisis_id)
                .where(Task.status.in_(["proposed", "confirmed", "assigned", "in_progress", "at_risk", "blocked"]))
                .order_by(Task.priority.desc())
            )
            tasks = tasks_r.scalars().all()

            # Plans
            plans_r = await session.execute(
                select(ResponsePlan)
                .where(ResponsePlan.crisis_id == crisis_id)
                .where(ResponsePlan.status.in_(["draft", "validated", "approved", "executing"]))
            )
            plans = plans_r.scalars().all()

        return {
            "crisis": {
                "id": str(crisis.id),
                "title": crisis.title,
                "status": crisis.status,
                "severity": crisis.severity,
                "severity_score": crisis.severity_score,
                "location": crisis.primary_location_name,
                "version": crisis.version,
            },
            "evidence_count": len(evidence_items),
            "evidence_items": [
                {
                    "id": str(e.id),
                    "source_type": e.source_type,
                    "source_provider": e.source_provider,
                    "normalized_content": e.normalized_content[:500],
                    "reliability_score": e.reliability_score,
                    "observed_at": e.observed_at.isoformat(),
                }
                for e in evidence_items[:50]
            ],
            "claims": [
                {
                    "id": str(c.id),
                    "statement": c.statement,
                    "epistemic_status": c.epistemic_status,
                    "confidence": c.confidence,
                    "freshness": c.freshness,
                }
                for c in claims
            ],
            "contradictions": [
                {
                    "id": str(c.id),
                    "description": c.description,
                    "status": c.status,
                    "severity": c.severity,
                }
                for c in contradictions
            ],
            "intelligence_gaps": [
                {
                    "id": str(g.id),
                    "question": g.question,
                    "priority": g.priority,
                    "status": g.status,
                }
                for g in gaps
            ],
            "hypotheses": [
                {
                    "id": str(h.id),
                    "statement": h.statement,
                    "confidence": h.confidence,
                    "status": h.status,
                }
                for h in hypotheses
            ],
            "active_tasks": [
                {
                    "id": str(t.id),
                    "title": t.title,
                    "status": t.status,
                    "priority": t.priority,
                    "assigned_name": t.assigned_name,
                    "deadline": t.deadline.isoformat() if t.deadline else None,
                }
                for t in tasks
            ],
            "active_plans": [
                {
                    "id": str(p.id),
                    "objective": p.objective,
                    "status": p.status,
                    "version": p.version,
                }
                for p in plans
            ],
        }

    async def create_crisis_from_hazard(
        self,
        title: str,
        hazard_type: str,
        severity: str,
        severity_score: float,
        latitude: Optional[float] = None,
        longitude: Optional[float] = None,
        location_name: Optional[str] = None,
        source_event_id: Optional[str] = None,
        source_type: Optional[str] = None,
    ) -> uuid.UUID:
        """Create a new crisis from a hazard event."""
        async with get_session() as session:
            crisis = Crisis(
                title=title,
                hazard_type=hazard_type,
                severity=severity,
                severity_score=severity_score,
                status="detected",
                primary_latitude=latitude,
                primary_longitude=longitude,
                primary_location_name=location_name,
                primary_source_event_id=source_event_id,
                primary_source_type=source_type,
                started_at=datetime.now(timezone.utc),
            )
            session.add(crisis)
            await session.flush()

            await event_publisher.publish(
                "crisis.created",
                {
                    "crisis_id": str(crisis.id),
                    "title": title,
                    "hazard_type": hazard_type,
                    "severity": severity,
                    "severity_score": severity_score,
                },
                crisis_id=crisis.id,
            )

            return crisis.id

    async def update_crisis_status(
        self,
        crisis_id: uuid.UUID,
        new_status: str,
        *,
        actor_type: str = "system",
        actor_id: str = "beacon",
    ) -> None:
        """Update crisis status with event publishing."""
        async with get_session() as session:
            crisis_r = await session.execute(
                select(Crisis).where(Crisis.id == crisis_id)
            )
            crisis = crisis_r.scalar_one_or_none()
            if not crisis:
                return

            old_status = crisis.status
            crisis.status = new_status
            crisis.version += 1

            if new_status == "resolved":
                crisis.resolved_at = datetime.now(timezone.utc)

            await event_publisher.publish(
                "crisis.status_changed",
                {
                    "crisis_id": str(crisis_id),
                    "old_status": old_status,
                    "new_status": new_status,
                },
                crisis_id=crisis_id,
                actor_type=actor_type,
                actor_id=actor_id,
                state_version_before=crisis.version - 1,
                state_version_after=crisis.version,
            )

    async def apply_agent_result(
        self,
        crisis_id: uuid.UUID,
        agent_result: dict[str, Any],
    ) -> dict[str, int]:
        """Apply an agent result to the world model.

        Returns counts of created entities.
        """
        counts = {"evidence": 0, "claims": 0, "gaps": 0, "contradictions": 0}

        async with get_session() as session:
            # Create evidence
            for ev in agent_result.get("evidence_candidates", []):
                evidence = Evidence(
                    crisis_id=crisis_id,
                    source_type=ev.get("source_type", "system_observation"),
                    source_provider=ev.get("source_provider", "agent"),
                    normalized_content=ev.get("normalized_content", ""),
                    raw_content_hash=ev.get("raw_content_hash", ""),
                    source_uri=ev.get("source_uri"),
                    slack_permalink=ev.get("slack_permalink"),
                    reliability_score=ev.get("reliability_score", 0.5),
                    observed_at=datetime.now(timezone.utc),
                    geographic_scope=ev.get("geographic_scope"),
                    metadata_=ev.get("metadata", {}),
                )
                session.add(evidence)
                counts["evidence"] += 1

            # Create claims
            for cl in agent_result.get("claim_proposals", []):
                claim = Claim(
                    crisis_id=crisis_id,
                    statement=cl.get("statement", ""),
                    normalized_subject=cl.get("normalized_subject"),
                    predicate=cl.get("predicate"),
                    object_=cl.get("object_"),
                    epistemic_status=cl.get("epistemic_status", "unknown"),
                    confidence=cl.get("confidence", 0.0),
                    created_by_agent=agent_result.get("agent_id"),
                )
                session.add(claim)
                counts["claims"] += 1

            # Create gaps
            for gap in agent_result.get("gap_proposals", []):
                ig = IntelligenceGap(
                    crisis_id=crisis_id,
                    question=gap.get("question", ""),
                    uncertainty_score=gap.get("uncertainty_score", 0.5),
                    decision_impact=gap.get("decision_impact", 0.5),
                    urgency=gap.get("urgency", 0.5),
                    candidate_strategies=gap.get("candidate_strategies"),
                    priority=(
                        gap.get("decision_impact", 0.5) * 0.4
                        + gap.get("urgency", 0.5) * 0.3
                        + gap.get("uncertainty_score", 0.5) * 0.3
                    ),
                )
                session.add(ig)
                counts["gaps"] += 1

            # Create contradictions
            for contra in agent_result.get("contradiction_proposals", []):
                c = Contradiction(
                    crisis_id=crisis_id,
                    description=contra.get("description", ""),
                    severity=contra.get("severity", 0.5),
                )
                session.add(c)
                counts["contradictions"] += 1

        logger.info(
            "agent_result_applied",
            crisis_id=str(crisis_id),
            counts=counts,
        )
        return counts


# Singleton
world_model = CrisisWorldModelService()
