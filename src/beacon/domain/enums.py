"""Beacon Command — Domain Enumerations.

All domain enums used across ORM models, Pydantic schemas, and business logic.
"""

from __future__ import annotations

from enum import Enum


# --- Crisis & Hazard ---

class CrisisStatus(str, Enum):
    DETECTED = "detected"
    TRIAGING = "triaging"
    ACTIVE = "active"
    MONITORING = "monitoring"
    STABILIZING = "stabilizing"
    RESOLVED = "resolved"
    ARCHIVED = "archived"


class HazardType(str, Enum):
    EARTHQUAKE = "earthquake"
    FLOOD = "flood"
    CYCLONE = "cyclone"
    TSUNAMI = "tsunami"
    VOLCANO = "volcano"
    WILDFIRE = "wildfire"
    DROUGHT = "drought"
    SEVERE_WEATHER = "severe_weather"
    LANDSLIDE = "landslide"
    INDUSTRIAL = "industrial"
    EPIDEMIC = "epidemic"
    OTHER = "other"


class HazardSeverity(str, Enum):
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    SEVERE = "severe"
    EXTREME = "extreme"


class EventSourceType(str, Enum):
    USGS = "usgs"
    GDACS = "gdacs"
    NWS = "nws"
    WEATHER = "weather"
    MANUAL = "manual"
    OTHER = "other"


# --- Evidence ---

class EvidenceSourceType(str, Enum):
    SLACK_RTS = "slack_rts"
    HAZARD_API = "hazard_api"
    WEATHER_API = "weather_api"
    GEOSPATIAL_API = "geospatial_api"
    RESOURCE_API = "resource_api"
    HUMAN_REPORT = "human_report"
    MCP_TOOL = "mcp_tool"
    SYSTEM_OBSERVATION = "system_observation"


# --- Claims ---

class ClaimEpistemicStatus(str, Enum):
    VERIFIED_FACT = "verified_fact"
    SUPPORTED_INFERENCE = "supported_inference"
    WEAK_INFERENCE = "weak_inference"
    CONTESTED = "contested"
    UNKNOWN = "unknown"
    STALE = "stale"
    INVALIDATED = "invalidated"


# --- Contradictions ---

class ContradictionStatus(str, Enum):
    DETECTED = "detected"
    INVESTIGATING = "investigating"
    CONFIRMED = "confirmed"
    RESOLVED = "resolved"
    DISMISSED = "dismissed"


# --- Intelligence Gaps ---

class GapStatus(str, Enum):
    IDENTIFIED = "identified"
    PRIORITIZED = "prioritized"
    ACQUIRING = "acquiring"
    RESOLVED = "resolved"
    EXPIRED = "expired"
    ABANDONED = "abandoned"


class AcquisitionStrategy(str, Enum):
    SLACK_RTS_SEARCH = "slack_rts_search"
    EXTERNAL_MCP_TOOL = "external_mcp_tool"
    TARGETED_HUMAN_REQUEST = "targeted_human_request"
    CHANNEL_REQUEST = "channel_request"
    SCHEDULED_RECHECK = "scheduled_recheck"
    COORDINATOR_ESCALATION = "coordinator_escalation"


# --- Hypotheses ---

class HypothesisStatus(str, Enum):
    ACTIVE = "active"
    SUPPORTED = "supported"
    WEAKENED = "weakened"
    REFUTED = "refuted"
    SUPERSEDED = "superseded"


# --- Missions ---

class MissionType(str, Enum):
    TRIAGE = "triage"
    WORKSPACE_INVESTIGATION = "workspace_investigation"
    EXTERNAL_INVESTIGATION = "external_investigation"
    EVIDENCE_SYNTHESIS = "evidence_synthesis"
    CLAIM_VERIFICATION = "claim_verification"
    CONTRADICTION_RESOLUTION = "contradiction_resolution"
    GAP_ANALYSIS = "gap_analysis"
    INTELLIGENCE_ACQUISITION = "intelligence_acquisition"
    HYPOTHESIS_ANALYSIS = "hypothesis_analysis"
    PLAN_GENERATION = "plan_generation"
    PLAN_VALIDATION = "plan_validation"
    PLAN_SIMULATION = "plan_simulation"
    PLAN_CRITIQUE = "plan_critique"
    RISK_ASSESSMENT = "risk_assessment"
    RECOMMENDATION = "recommendation"
    CHANGE_ANALYSIS = "change_analysis"
    RECONCILIATION = "reconciliation"
    COMMITMENT_PROCESSING = "commitment_processing"
    REPLANNING = "replanning"
    AFTER_ACTION_ANALYSIS = "after_action_analysis"
    MEMORY_EXTRACTION = "memory_extraction"


class MissionStatus(str, Enum):
    CREATED = "created"
    QUEUED = "queued"
    SCHEDULED = "scheduled"
    RUNNING = "running"
    PAUSED = "paused"
    AWAITING_APPROVAL = "awaiting_approval"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"


# --- Tasks ---

class TaskStatus(str, Enum):
    PROPOSED = "proposed"
    CONFIRMED = "confirmed"
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    AT_RISK = "at_risk"
    OVERDUE = "overdue"
    ESCALATED = "escalated"
    COMPLETED = "completed"
    VERIFIED = "verified"
    CANCELLED = "cancelled"


# --- Plans ---

class PlanStatus(str, Enum):
    DRAFT = "draft"
    VALIDATED = "validated"
    SIMULATED = "simulated"
    CRITIQUED = "critiqued"
    RECOMMENDED = "recommended"
    APPROVED = "approved"
    EXECUTING = "executing"
    COMPLETED = "completed"
    INVALIDATED = "invalidated"
    SUPERSEDED = "superseded"


# --- Commitments ---

class CommitmentStatus(str, Enum):
    DETECTED = "detected"
    CONFIRMED = "confirmed"
    EDITED = "edited"
    IGNORED = "ignored"
    CONVERTED_TO_TASK = "converted_to_task"


# --- Approvals ---

class ApprovalDecision(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"
    SUPERSEDED = "superseded"


# --- Authority Levels ---

class AuthorityLevel(str, Enum):
    L0_OBSERVE = "L0_OBSERVE"
    L1_RECOMMEND = "L1_RECOMMEND"
    L2_PREPARE = "L2_PREPARE"
    L3_EXECUTE_REVERSIBLE = "L3_EXECUTE_REVERSIBLE"
    L4_EXECUTE_OPERATIONAL = "L4_EXECUTE_OPERATIONAL"
    L5_PROHIBITED = "L5_PROHIBITED"


# --- Tool Side Effects ---

class SideEffectClass(str, Enum):
    NONE = "none"
    REVERSIBLE = "reversible"
    OPERATIONAL = "operational"
    HIGH_CONSEQUENCE = "high_consequence"


# --- Materiality ---

class MaterialityLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


# --- Attention Actions ---

class AttentionAction(str, Enum):
    IGNORE = "ignore"
    STORE_ONLY = "store_only"
    UPDATE_STATE = "update_state"
    UPDATE_TASKS = "update_tasks"
    REQUEST_VERIFICATION = "request_verification"
    NOTIFY_OWNER = "notify_owner"
    NOTIFY_COORDINATOR = "notify_coordinator"
    ESCALATE = "escalate"
    LAUNCH_REPLANNING = "launch_replanning"


# --- Risk Dimensions ---

class RiskDimension(str, Enum):
    HUMAN_SAFETY = "human_safety"
    OPERATIONAL = "operational"
    EVIDENCE = "evidence"
    EXECUTION = "execution"
    COORDINATION = "coordination"
    DEPENDENCY = "dependency"
    UNCERTAINTY = "uncertainty"


# --- Decision Status ---

class DecisionStatus(str, Enum):
    PROPOSED = "proposed"
    ACTIVE = "active"
    SUPERSEDED = "superseded"
    REVERSED = "reversed"


# --- Incident Episode ---

class EpisodeStatus(str, Enum):
    DRAFT = "draft"
    FINALIZED = "finalized"


# --- Actor Types ---

class ActorType(str, Enum):
    SYSTEM = "system"
    AGENT = "agent"
    HUMAN = "human"
    COORDINATOR = "coordinator"
    EXTERNAL_SERVICE = "external_service"


# --- Domain Event Types ---

class DomainEventType(str, Enum):
    # Hazard
    HAZARD_OBSERVED = "hazard.observed"
    HAZARD_NORMALIZED = "hazard.normalized"
    HAZARD_CORRELATED = "hazard.correlated"
    # Crisis
    CRISIS_CREATED = "crisis.created"
    CRISIS_STATUS_CHANGED = "crisis.status_changed"
    CRISIS_RESOLVED = "crisis.resolved"
    # Mission
    MISSION_CREATED = "mission.created"
    MISSION_SCHEDULED = "mission.scheduled"
    MISSION_STARTED = "mission.started"
    MISSION_PAUSED = "mission.paused"
    MISSION_COMPLETED = "mission.completed"
    MISSION_FAILED = "mission.failed"
    # Tool
    TOOL_REQUESTED = "tool.requested"
    TOOL_AUTHORIZED = "tool.authorized"
    TOOL_REJECTED = "tool.rejected"
    TOOL_SUCCEEDED = "tool.succeeded"
    TOOL_FAILED = "tool.failed"
    # RTS
    RTS_SEARCH_STARTED = "rts.search_started"
    RTS_SEARCH_COMPLETED = "rts.search_completed"
    # Evidence
    EVIDENCE_OBSERVED = "evidence.observed"
    EVIDENCE_VERIFIED = "evidence.verified"
    EVIDENCE_LINKED = "evidence.linked"
    # Claim
    CLAIM_CREATED = "claim.created"
    CLAIM_UPDATED = "claim.updated"
    CLAIM_CONTESTED = "claim.contested"
    CLAIM_INVALIDATED = "claim.invalidated"
    # Contradiction
    CONTRADICTION_DETECTED = "contradiction.detected"
    CONTRADICTION_RESOLVED = "contradiction.resolved"
    # Uncertainty
    UNCERTAINTY_CREATED = "uncertainty.created"
    # Intelligence Gap
    INTELLIGENCE_GAP_CREATED = "intelligence_gap.created"
    INTELLIGENCE_GAP_PRIORITIZED = "intelligence_gap.prioritized"
    INTELLIGENCE_REQUEST_CREATED = "intelligence_request.created"
    HUMAN_EVIDENCE_RECEIVED = "human_evidence.received"
    # Hypothesis
    HYPOTHESIS_CREATED = "hypothesis.created"
    HYPOTHESIS_UPDATED = "hypothesis.updated"
    # Plan
    PLAN_GENERATED = "plan.generated"
    PLAN_VALIDATED = "plan.validated"
    PLAN_SIMULATED = "plan.simulated"
    PLAN_CRITIQUED = "plan.critiqued"
    PLAN_UPDATED = "plan.updated"
    # Risk & Recommendation
    RISK_ASSESSED = "risk.assessed"
    RECOMMENDATION_CREATED = "recommendation.created"
    # Approval
    APPROVAL_REQUESTED = "approval.requested"
    APPROVAL_GRANTED = "approval.granted"
    APPROVAL_REJECTED = "approval.rejected"
    # Action
    ACTION_PREPARED = "action.prepared"
    ACTION_EXECUTED = "action.executed"
    ACTION_FAILED = "action.failed"
    # Commitment
    COMMITMENT_DETECTED = "commitment.detected"
    COMMITMENT_CONFIRMED = "commitment.confirmed"
    COMMITMENT_REJECTED = "commitment.rejected"
    # Task
    TASK_CREATED = "task.created"
    TASK_ASSIGNED = "task.assigned"
    TASK_STARTED = "task.started"
    TASK_BLOCKED = "task.blocked"
    TASK_AT_RISK = "task.at_risk"
    TASK_OVERDUE = "task.overdue"
    TASK_COMPLETED = "task.completed"
    TASK_VERIFIED = "task.verified"
    # Material Change
    MATERIAL_CHANGE_DETECTED = "material_change.detected"
    IMPACT_PROPAGATION_COMPLETED = "impact_propagation.completed"
    REPLANNING_STARTED = "replanning.started"
    # Decision
    DECISION_CREATED = "decision.created"
    DECISION_SUPERSEDED = "decision.superseded"
    # Reconciliation
    RECONCILIATION_CONFLICT_DETECTED = "reconciliation.conflict_detected"
    RECONCILIATION_CONFLICT_RESOLVED = "reconciliation.conflict_resolved"
    # After-Action
    AFTER_ACTION_REPORT_GENERATED = "after_action.report_generated"
    INCIDENT_EPISODE_CREATED = "incident_episode.created"
    LESSON_PROPOSED = "lesson.proposed"
    PROCEDURE_VERSION_APPROVED = "procedure.version_approved"
