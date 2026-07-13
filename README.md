# 🛡️ BEACON COMMAND: Autonomous Crisis Intelligence & Coordination Engine

[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.109+-green.svg)](https://fastapi.tiangolo.com/)
[![LangGraph](https://img.shields.io/badge/LangGraph-Durable_Agents-orange.svg)](https://github.com/langchain-ai/langgraph)
[![Slack App](https://img.shields.io/badge/Slack-App_Home_Ready-pink.svg)](https://api.slack.com/)

**Beacon Command** is a production-grade, multi-agent crisis coordination and hazard intelligence platform. It bridges real-time global disaster alerting networks (USGS Earthquakes, GDACS global crises, NWS severe weather) with internal organizational Slack spaces, executing autonomous investigative missions, synthesizing evidence into epistemically-tracked claims, constructing task DAGs, and coordinating response plans with human-in-the-loop policy gates.

---

## 🛠️ System Architecture

Beacon Command is built as an event-driven, multi-plane architecture. Below is a detailed view of how hazard ingestion, agent execution, world-model checkpointing, and Slack command surfaces interact.

```mermaid
graph TD
    %% Ingestion Plane
    subgraph IngestionPlane ["Ingestion Plane (Real Data Feeds)"]
        USGS["USGS Earthquake Feed (GeoJSON Pollers)"]
        GDACS["GDACS RSS and GeoRSS (RSS Parsers)"]
        NWS["NWS Weather Alerts (Weather API)"]
        Normalizer["Event Normalizer & Deduplicator"]
        Correlator["Spatio-Temporal Correlation Engine"]
        
        USGS --> Normalizer
        GDACS --> Normalizer
        NWS --> Normalizer
        Normalizer --> Correlator
    end

    %% Event Bus & DB
    subgraph CoreTruth ["Core State & Storage"]
        Postgres["PostgreSQL 16 & pgvector Database"]
        Redis["Redis Cache & Pub-Sub"]
        EventBus["Domain Event Publisher"]
    end
    
    Correlator --> Postgres
    Correlator --> EventBus
    EventBus --> Redis

    %% Agent Supervision Plane
    subgraph AgentSupervision ["Agent Control Plane (LangGraph)"]
        Supervisor["Supervisor Orchestrator (LangGraph)"]
        TriageAgent["Triage Agent (Hybrid Heuristics + LLM)"]
        Investigator["Workspace Investigator (Slack Search)"]
        ExtIntel["External Intel Agent (MCP Feed Queries)"]
        Synthesizer["Evidence Synthesizer (Claim Proposal)"]
        Planner["DAG Response Planner (Plan Generation)"]
        Critic["Red-Team Critic and Risk Assessor"]
        Reconciler["State Reconciler and Conflict Resolver"]
        
        PGCheckpointer["PostgreSQL State Checkpointer"]
        
        Supervisor --> PGCheckpointer
        PGCheckpointer --> Supervisor
        
        Supervisor --> TriageAgent
        Supervisor --> Investigator
        Supervisor --> ExtIntel
        Supervisor --> Synthesizer
        Supervisor --> Planner
        Supervisor --> Critic
        Supervisor --> Reconciler
    end
    
    EventBus --> Supervisor

    %% MCP Plane
    subgraph MCPPlane ["Model Context Protocol (MCP) Plane"]
        ClientAdapter["Unified MCP Client Adapter"]
        HazardMCP["Hazard MCP Server (Event History)"]
        GeoMCP["Geospatial MCP Server (Geocoding & Routing)"]
        ResourceMCP["Resource MCP Server (Org Registry)"]
        OpsMCP["Operations MCP Server (Task Management)"]
        VerifyMCP["Verification MCP Server (Claim Verification)"]
        
        ClientAdapter --> HazardMCP
        ClientAdapter --> GeoMCP
        ClientAdapter --> ResourceMCP
        ClientAdapter --> OpsMCP
        ClientAdapter --> VerifyMCP
    end
    
    ExtIntel --> ClientAdapter
    Investigator --> ClientAdapter
    Reconciler --> ClientAdapter
    
    HazardMCP --> Postgres
    Postgres --> HazardMCP
    
    ResourceMCP --> Postgres
    Postgres --> ResourceMCP
    
    OpsMCP --> Postgres
    Postgres --> OpsMCP
    
    VerifyMCP --> Postgres
    Postgres --> VerifyMCP

    %% User Interaction Plane
    subgraph SlackSurface ["Coordinator Interface (Slack)"]
        AppHome["Command Center Home Tab"]
        SlackChannel["Active Crisis Channels"]
        Approvals["Human-in-the-Loop Gates"]
        BoltHandler["FastAPI /slack/events (Bolt Async Handler)"]
        
        BoltHandler --> AppHome
        AppHome --> BoltHandler
        
        BoltHandler --> SlackChannel
        SlackChannel --> BoltHandler
        
        BoltHandler --> Approvals
        Approvals --> BoltHandler
    end

    Supervisor --> Approvals
    BoltHandler --> EventBus
    BoltHandler --> Postgres
    EventBus --> Postgres
```

---

## 🌟 Key Subsystems & Technical Details

### 1. The Multi-Agent Control Plane (LangGraph)
All crisis investigation is coordinated by a stateful supervisor graph built with **LangGraph**.
- **State Checkpointing**: Using `langgraph-checkpoint-postgres` to store durable state checkpoints in the Postgres database. If the server crashes or reboots, agent executions resume exactly where they left off.
- **Hybrid Triage**: The triage agent combines deterministic heuristics (safety overrides, threshold logic for earthquake magnitude and source-reported severity) with semantic intelligence to prevent AI-level bypass of critical alerts.

### 2. Epistemic Claim Synthesis (The World Model)
Beacon operates under a strict **Zero-Hallucination Policy**: agents are forbidden from generating recommendations from raw text. 
- **Evidence-to-Claim Mapping**: All raw source items (Slack search results, API payloads) are parsed into immutable `Evidence` nodes. 
- **Epistemic Tracking**: The `EvidenceSynthesizer` compiles multiple evidence items to propose versioned `Claims` (e.g. `verified_fact`, `supported_inference`, `weak_inference`, or `contested`).
- **DAG Resolution**: Response plans are represented as directed acyclic graphs (DAGs) of tasks, where tasks explicitly declare dependency relationships and success criteria.

### 3. Model Context Protocol (MCP) Integration
All external interaction flows through five dedicated **MCP Servers**:
1. **Hazard Server**: Provides tools for historical query matching and spatio-temporal lookup of global alerts.
2. **Geospatial Server**: Provides Nominatim geocoding, Haversine distance, and OSRM routing calculations.
3. **Resource Server**: Queries personnel registers, equipment inventories, and active constraints.
4. **Operations Server**: Manages task lifecycles, decision ledgers, and action workflows.
5. **Verification Server**: Evaluates claim freshness, flags source inconsistencies, and compares conflicting payloads.

### 4. Interactive Command Surfaces (Slack Block Kit)
Coordination is handled entirely within Slack via 20+ custom Block Kit designs including:
- **App Home Command Center**: Real-time stats dashboard displaying active crises, pending approvals, at-risk tasks, and active coordinator missions.
- **Situation Briefs**: Formatted fields summarizing event impact, evidence, verified facts, and gaps.
- **Approval requests**: Interactive buttons that register human decisions directly in the immutable `DecisionLedger` service.

---

## 💻 Tech Stack

- **Backend Framework**: Python 3.12+, FastAPI
- **Database / Vector Search**: PostgreSQL 16 + pgvector (via SQLAlchemy 2.0 async and Alembic migrations)
- **State Checkpointing / DAGs**: LangGraph, Redis cache, and pub/sub
- **Agent Engines**: Google Gemini (via `google-genai` SDK) & OpenAI GPT-4o (configurable)
- **Collaboration Platform**: Slack Bolt Async SDK
- **Observability**: OpenTelemetry OTLP tracing and JSON structured `structlog`

---

## ⚡ Setup & Installation

### Prerequisites
- Python 3.12+
- PostgreSQL 16 (with the `pgvector` extension)
- Redis 7

### 1. Clone & Set Up Virtual Environment
```bash
git clone https://github.com/priteshvirat24/BeaconOS.git
cd BeaconOS

python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

### 2. Configure Environment Variables
Copy `.env.example` to `.env` and fill in the required API keys:
```bash
cp .env.example .env
```
Key configurations:
- `DATABASE_URL`: `postgresql+asyncpg://beacon:beacon@localhost:5432/beacon`
- `DATABASE_SYNC_URL`: `postgresql+psycopg://beacon:beacon@localhost:5432/beacon`
- `REDIS_URL`: `redis://localhost:6379/0`
- `LLM_PROVIDER`: `gemini` (or `openai`)
- `GEMINI_API_KEY`: Your Google AI Studio API key
- `SLACK_BOT_TOKEN` / `SLACK_SIGNING_SECRET`: Your Slack App credentials

### 3. Apply DB Migrations
Apply the initial table schemas and verify the `vector` extension is enabled:
```bash
alembic upgrade head
```

---

## 🧪 Verification & Testing

### Run the Test Suite
We maintain a comprehensive test suite covering configurations, domain models, Pydantic validations, security guardrails, Block Kit builders, and USGS ingestion engines:
```bash
pytest tests/ -v
```

### Run End-to-End Local System Test
Executes a dry-run simulating database connection, Redis set/get caching, event publishing, hazard ingestion, task assignments, and approval workflows:
```bash
python -m scratch.verify_services
```

### Start the Application
To boot the FastAPI server and launch all periodic pollers (USGS, GDACS, and NWS):
```bash
python -m beacon.main
```

---

## 🛡️ Security & Policy Enforcement
- **Prompt Injection Defense**: Content sanitization filters out instructions attempting role overrides or system instruction bypasses.
- **PII & Token Redaction**: Redacts credit cards, emails, SSNs, phone numbers, and credentials before logging or passing to external model APIs.
- **Authority Levels**: Gated operations mapping (e.g. `L0_OBSERVE` to `L4_EXECUTE_OPERATIONAL`) ensures that agents cannot execute write actions on Slack or change database configurations without proper credentials.

---

## 📄 License
This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
