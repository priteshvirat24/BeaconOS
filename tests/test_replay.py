"""Tests for the scenario replay harness (scratch/replay_event.py).

Verifies that: (1) real stored fixtures normalize through the production poller
logic into the expected hazard shape, (2) the replay path uses the *identical*
normalizer as live polling (no demo-mode divergence), (3) normalization is
deterministic, and (4) a replay drives the real pipeline + a progressive
timeline and produces a Situation Brief whose numbers reflect real state.
"""

from __future__ import annotations

import json
from pathlib import Path

from scratch.replay_event import (
    FIXTURES,
    SCENARIOS,
    _normalize,
    replay,
)

from beacon.agents.base import (
    AgentBase,
    AgentContext,
    AgentResult,
    ClaimProposal,
    EvidenceCandidate,
)
from beacon.agents.pipeline import STAGE_ORDER
from beacon.ingestion.usgs import USGSPoller


def test_ridgecrest_fixture_exists_and_is_real_geojson():
    payload = json.loads((FIXTURES / SCENARIOS["ridgecrest"].fixture).read_text())
    # Real USGS single-feature GeoJSON shape.
    assert payload["type"] == "Feature"
    assert payload["properties"]["mag"] == 7.1
    assert "geometry" in payload and payload["geometry"]["type"] == "Point"


def test_normalize_ridgecrest_produces_earthquake_hazard():
    n = _normalize(SCENARIOS["ridgecrest"])
    assert n is not None
    assert n["hazard_type"] == "earthquake"
    assert n["magnitude"] == 7.1
    assert n["severity_score"] >= 7.0  # M7.1 shallow => high deterministic score
    assert n["latitude"] is not None and n["longitude"] is not None


def test_normalize_midland_produces_severe_weather_hazard():
    n = _normalize(SCENARIOS["midland_flood"])
    assert n is not None
    assert n["hazard_type"] == "severe_weather"
    assert n["severity"] == "severe"


def test_replay_uses_same_normalizer_as_live_poller():
    """The replay path must not diverge from live ingestion."""
    sc = SCENARIOS["ridgecrest"]
    payload = json.loads((FIXTURES / sc.fixture).read_text())
    via_replay = _normalize(sc)
    via_live = USGSPoller(feed_url="unused", min_magnitude=4.0).normalize_feature(payload)
    assert via_replay == via_live


def test_normalize_is_deterministic():
    for sc in SCENARIOS.values():
        assert _normalize(sc) == _normalize(sc)


class _StubAgent(AgentBase):
    def __init__(self, node_id: str) -> None:
        super().__init__(agent_id=node_id, capabilities=[])
        self.node_id = node_id

    @property
    def system_prompt(self) -> str:
        return "stub"

    async def execute(self, context: AgentContext) -> AgentResult:
        r = self._empty_result(context)
        if self.node_id == "investigate":
            r.evidence_candidates = [
                EvidenceCandidate(
                    source_type="slack_rts",
                    source_provider="slack_search",
                    normalized_content="Two shelters confirmed open downtown.",
                    raw_content_hash="h1",
                )
            ]
        elif self.node_id == "synthesize":
            r.claim_proposals = [
                ClaimProposal(
                    statement="Two shelters are open.",
                    epistemic_status="verified_fact",
                    confidence=0.9,
                )
            ]
        elif self.node_id == "plan":
            r.plan_proposals = [
                {"tasks": [{"objective": "Stock shelters", "dependencies": []}]}
            ]
        return r


class _CapturePublisher:
    def __init__(self) -> None:
        self.frames: list[str | None] = []

    async def __call__(self, node_id, state):
        self.frames.append(node_id)


async def test_replay_drives_pipeline_timeline_and_brief():
    capture = _CapturePublisher()
    agents = {n: _StubAgent(n) for n in STAGE_ORDER}
    state = await replay(
        "ridgecrest",
        org="ingo",
        agents=agents,
        publisher_factory=lambda: capture,
    )
    # Progressive: one START (None) + one per stage.
    assert capture.frames == [None, *STAGE_ORDER]
    # The seed hazard is present as evidence, plus the investigator's finding.
    assert len(state["evidence_items"]) == 2
    # Brief reflects the real synthesized claim.
    brief = state["_brief"]
    brief_text = json.dumps(brief)
    assert "Ridgecrest" in brief_text
    assert '"Verified Claims"' in brief_text or "Verified Claims" in brief_text


def test_scenarios_cover_multiple_sources_and_hazard_types():
    sources = {s.source for s in SCENARIOS.values()}
    assert len(sources) >= 2  # breadth: not one lucky scenario
    hazards = {_normalize(s)["hazard_type"] for s in SCENARIOS.values()}
    assert len(hazards) >= 2


def test_all_fixture_files_present():
    for s in SCENARIOS.values():
        assert (Path(FIXTURES) / s.fixture).exists()
