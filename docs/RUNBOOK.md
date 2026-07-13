# Beacon Command — Cold-Start Runbook

The single sequence that stands in for "a judge tries this themselves." If it works from a
cold checkout, the submission is safe.

## 0. Prerequisites
- Docker Desktop **running** (the daemon must be up).
- Python 3.12+ (`.venv` here is built with `python3.13`).
- A Slack app (bot + coordinator user token) for the live-Slack beats — optional for the
  offline replay.

## 1. Python environment
```bash
python3.13 -m venv .venv
. .venv/bin/activate
pip install -e ".[dev]"
```

## 2. Environment file
Create `.env` (gitignored) from the template:
```bash
cp .env.example .env
# minimum to boot infra + offline replay:
#   DATABASE_URL / DATABASE_SYNC_URL / REDIS_URL  (defaults target localhost)
# for live Slack + real reasoning also set:
#   SLACK_BOT_TOKEN, SLACK_SIGNING_SECRET, SLACK_COORDINATOR_USER_TOKEN
#   GEMINI_API_KEY (or OPENAI_API_KEY)   <-- needed for synth/plan/critique content
```

## 3. Infrastructure
```bash
docker compose up -d postgres redis
docker compose ps            # both healthy
```

## 4. Migrate
```bash
alembic upgrade head
```

## 5. Verify subsystems (DB + Redis + world model + tasks + approvals)
```bash
python -m scratch.verify_services
# => "ALL INFRASTRUCTURE & SUBSYSTEM VERIFICATIONS PASSED"
```

## 6. Tests
```bash
pytest -q                    # full suite, green
```

## 7. The demo path (no live Slack needed)
```bash
python -m scratch.replay_event                 # list real scenarios
python -m scratch.replay_event ridgecrest      # real M7.1 -> timeline -> brief + footer
python -m scratch.replay_event midland_flood --org local
python -m scratch.security_demo                # injection neutralized + PII redacted
```

## 8. Live Slack (optional, for the video)
```bash
# run the app (serves Slack events / Socket Mode per your app config)
uvicorn beacon.main:app --host 0.0.0.0 --port 8000
# seed a coherent workspace so exploration looks real:
python -m scratch.seed_sandbox --ph-ops C... --volunteers C... --logistics C...
# then in Slack: open App Home -> click "🛰️ Mission Timeline" on a crisis, or
# click "🔍 Investigate" on a hazard alert.
```

## Notes
- `.env` is gitignored; never commit tokens.
- Without an LLM key, Triage still produces a real deterministic severity decision from the
  real event; the Synthesizer/Planner/Critic stages will show zero (no fabrication).
- The replay path uses the **same** normalizer/threshold/pipeline as live polling — there is
  no demo-mode branch (enforced by `tests/test_replay.py`).
