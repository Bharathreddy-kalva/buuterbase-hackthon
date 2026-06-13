# FleetMind

FleetMind is a multi-agent orchestrator for fleet/operations management. A
**supervisor** agent receives incoming requests and routes them to one of
four domain agents — **finance**, **hr**, **logistics**, and **support** —
each of which can read/write shared data in **Butterbase**, recall and store
long-term memory via **EverMind Cloud**, and trigger **Photon** iMessage
alerts for events that need a human's attention.

This file is the persistent context for Claude Code sessions working on this
repo. Keep it up to date as the architecture solidifies.

## Architecture overview

```
                ┌──────────────┐
  user/channel  │  api/main.py  │  (FastAPI entrypoint)
  ───────────▶  │ api/webhook.py│  (inbound Photon webhooks, etc.)
                └──────┬────────┘
                       │
                       ▼
              ┌───────────────────┐
              │ Supervisor Agent   │  agents/supervisor/supervisor_agent.py
              │ - classifies intent│
              │ - routes to a domain agent
              │ - aggregates/replies
              └──────┬─────────────┘
                      │ routes to one of:
        ┌─────────────┼──────────────┬──────────────┐
        ▼             ▼              ▼              ▼
   ┌─────────┐  ┌──────────┐  ┌─────────────┐  ┌──────────┐
   │ Finance │  │   HR     │  │  Logistics  │  │ Support  │
   │ Agent   │  │  Agent   │  │   Agent     │  │  Agent   │
   └────┬────┘  └────┬─────┘  └──────┬──────┘  └────┬─────┘
        │            │               │              │
        └────────────┴───────┬───────┴──────────────┘
                              ▼
        ┌─────────────────────────────────────────────┐
        │              integrations/                    │
        │  butterbase/  -> DB + RAG knowledge store      │
        │  evermind/    -> EverMind Cloud agent memory   │
        │  photon/      -> iMessage alerts (outbound)    │
        └─────────────────────────────────────────────┘
                              │
                              ▼
                    memory/shared_brain.py
              (cross-agent shared context/state)
```

## Agent roles

### Supervisor (`agents/supervisor/supervisor_agent.py`)
- Entry point for all user requests (via `api/main.py`).
- Classifies the intent of an incoming message and routes it to the
  appropriate domain agent (finance, hr, logistics, support).
- May fan a single request out to multiple agents and combine their
  responses (e.g., "why is this driver's reimbursement late?" touches both
  finance and logistics).
- Reads/writes `memory/shared_brain.py` for context that should be visible
  across agents (e.g., who the current user is, active session state).
- Decides when an event is important enough to trigger a Photon iMessage
  alert (escalations, anomalies, approvals needed).

### Finance (`agents/finance/finance_agent.py`)
- Handles budgets, expenses, invoices, payroll cost questions, and
  reimbursement status.
- Queries Butterbase tables for financial records and uses Butterbase RAG
  for policy documents (expense policy, approval thresholds, etc.).
- Recalls and stores its case history via `integrations/evermind/memory.py`
  (EverMind Cloud, `user_id="finance"`) — past approvals, recurring vendors,
  and contract-impact assessments.

### HR (`agents/hr/hr_agent.py`)
- Handles employee records, leave/PTO requests, onboarding/offboarding
  questions, and policy lookups (handbook, benefits).
- Queries Butterbase for employee data and RAG over HR policy docs.
- Recalls and stores its case history via `integrations/evermind/memory.py`
  (EverMind Cloud, `user_id="hr"`) — e.g., an employee's leave history or
  open HR tickets.

### Logistics (`agents/logistics/logistics_agent.py`)
- Handles fleet/vehicle status, routes, deliveries, maintenance schedules,
  and driver assignments.
- Queries Butterbase for live fleet/vehicle/route data and RAG over
  operations manuals (maintenance SOPs, routing guidelines).
- Recalls and stores its case history via `integrations/evermind/memory.py`
  (EverMind Cloud, `user_id="logistics"`) — e.g., recurring route issues or
  a vehicle's maintenance history.

### Support (`agents/support/support_agent.py`)
- Handles general support tickets and questions that don't cleanly belong
  to finance/hr/logistics — first line of triage, FAQ answers, and
  escalation to a human.
- Queries Butterbase RAG over general knowledge base / FAQ content.
- Recalls and stores its case history via `integrations/evermind/memory.py`
  (EverMind Cloud, `user_id="support"`) — e.g., a customer's open tickets
  and prior interactions.

## Integrations

### Butterbase (`integrations/butterbase/`)
- `client.py` — low-level client for the Butterbase backend: database
  (tables/rows via `select_rows`/`insert_row`), schema/migrations, storage,
  auth, and realtime. This is the system of record for fleet, finance, HR,
  and support data.
- `rag.py` — wrapper around Butterbase's RAG content/query tools. Each
  domain agent retrieves relevant policy/knowledge-base chunks here before
  answering a question (retrieval-augmented generation).
- Auth: `BUTTERBASE_URL`, `BUTTERBASE_API_KEY`, `BUTTERBASE_PROJECT_ID`.

### EverMind Cloud (`integrations/evermind/`)
- `memory.py` — client for EverMind Cloud's hosted agent-memory API
  (`https://api.evermind.ai`). Each of the 4 domain agents has its own
  memory stream, addressed by `user_id=<agent_id>` (`finance`, `hr`,
  `logistics`, `support`). Exposes:
  - `store_memory(agent_id, session_id, content)` — record what an agent
    did/found for an event, via `POST /api/v1/memories/agent`.
  - `search_memory(agent_id, query)` — hybrid retrieval of an agent's past
    episodes/cases relevant to the current task, via
    `POST /api/v1/memories/search`.
  - `flush_session(session_id)` — force EverMind to extract/consolidate
    memories for a finished orchestration run, across all 4 agents, via
    `POST /api/v1/memories/agent/flush`.
  - `get_agent_skills(agent_id)` — fetch the self-evolving "skills" EverMind
    has distilled from an agent's past cases, via
    `POST /api/v1/memories/get` (`memory_type="agent_skill"`).
  - All calls degrade gracefully (return an empty/error result instead of
    raising) so a memory outage never breaks an agent run.
- Auth: `EVERMIND_API_KEY` (Bearer token), `EVERMIND_BASE_URL`
  (`https://api.evermind.ai`). Note: `https://everos.evermind.ai` is the
  EverMind *dashboard* (where API keys are issued), not the API host.
- The supervisor calls `memory.flush_session(event_id)` at the end of
  `run()`, after all dispatched agents have stored their findings for that
  event.
- Separately, the `EVEROS_LLM__*` / `EVEROS_EMBEDDING__*` / `EVEROS_RERANK__*`
  / `EVEROS_MULTIMODAL__*` env vars configure models on the **Butterbase AI
  gateway** used by `integrations/butterbase/client.py` for chat completions
  — unrelated to EverMind Cloud memory.

### Photon (`integrations/photon/`)
- `imessage.py` — sends outbound iMessage alerts via Photon when an agent
  (usually the supervisor) decides a human needs to be notified immediately
  (e.g., budget threshold exceeded, urgent HR escalation, critical vehicle
  issue, unresolved support ticket past SLA).
- `PHOTON_API_KEY` authenticates outbound alert requests.
- `PHOTON_WEBHOOK_SECRET` verifies inbound webhooks from Photon (e.g., a
  user replying to an alert via iMessage), received at `api/webhook.py`.
- `ALERT_IMESSAGE_NUMBER` is the destination phone number/handle for
  alerts.

### Shared memory (`memory/shared_brain.py`)
- Cross-agent shared context that doesn't belong to any single agent's
  EverOS namespace — e.g., active session/user info, the supervisor's
  routing decisions, and any state that multiple agents need to coordinate
  on within a single request lifecycle.

## API (`api/`)
- `main.py` — FastAPI app entrypoint. Exposes the endpoint(s) that accept
  incoming user messages, pass them to the supervisor agent, and return
  responses.
- `webhook.py` — receives inbound webhooks (e.g., from Photon for iMessage
  replies), verifies them, and feeds events back into the supervisor.

## Environment variables (`.env.example`)

| Variable | Purpose |
|---|---|
| `ANTHROPIC_API_KEY` | API key for Claude models used by all agents. |
| `BUTTERBASE_URL` | Base URL of the Butterbase backend. |
| `BUTTERBASE_API_KEY` | API key for Butterbase (DB, storage, RAG, auth). |
| `BUTTERBASE_PROJECT_ID` | Butterbase project identifier. |
| `EVEROS_LLM__API_KEY` | API key for EverOS's internal LLM (memory summarization). |
| `EVEROS_LLM__MODEL` | Model name EverOS uses for memory operations. |
| `EVEROS_LLM__BASE_URL` | Base URL for EverOS's LLM provider. |
| `EVEROS_EMBEDDING__API_KEY` | API key for the Butterbase AI gateway embedding model. |
| `EVEROS_EMBEDDING__MODEL` | Embedding model name (Butterbase AI gateway). |
| `EVERMIND_API_KEY` | API key for EverMind Cloud agent memory. |
| `EVERMIND_BASE_URL` | Base URL for the EverMind Cloud API (`https://api.evermind.ai`). |
| `PHOTON_API_KEY` | API key for sending Photon iMessage alerts. |
| `PHOTON_WEBHOOK_SECRET` | Secret used to verify inbound Photon webhooks. |
| `ALERT_IMESSAGE_NUMBER` | Destination iMessage handle/number for alerts. |
| `PORT` | Port the FastAPI app listens on. |
| `ENV` | Environment name (e.g., `development`, `production`). |

## Running the project

1. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

2. **Configure environment**
   ```bash
   cp .env.example .env
   # fill in ANTHROPIC_API_KEY, BUTTERBASE_*, EVEROS_*, PHOTON_*, etc.
   ```

3. **Run the API server**
   ```bash
   uvicorn api.main:app --reload --port ${PORT:-8000}
   ```

4. **Run the demo**
   ```bash
   python tests/demo.py
   ```
   The demo script exercises the supervisor → domain agent → Butterbase /
   EverMind / Photon flow end-to-end without needing the API server running.

## Conventions for future work
- All agent memory access goes through `integrations/evermind/memory.py` —
  agents should not call the EverMind Cloud API directly.
- All Butterbase access goes through `integrations/butterbase/client.py`
  and `rag.py` — agents should not call Butterbase APIs directly.
- All outbound alerts go through `integrations/photon/imessage.py` — keep
  alert-triggering logic in the supervisor where possible so alert policy
  stays centralized.
- Update this file whenever the routing logic, memory strategy, or
  integration contracts change significantly.
