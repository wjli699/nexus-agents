# CLAUDE.md — Project Context for Claude Code

This file is read automatically by Claude Code at the start of every
session in this repo. It exists so you don't have to re-explain project
history — everything below is the condensed context from the planning
conversation that led to this codebase.

## What this project is

`nexus-agents` — a self-hosted, mobile-first personal multi-agent system.
One Telegram bot routes messages to small, purpose-built agents that track
different parts of life. Currently: a working stock watchlist agent.
Planned: family/household, task tracking, home projects, news curation.

Full architecture rationale, roadmap, and API spec are in this repo:
- `README.md` — architecture overview, what's built
- `docs/JOURNAL.md` — every infra gotcha hit so far (Tailscale DNS, n8n
  quirks, Docker networking) — check here before re-debugging something
  that was already solved
- `docs/MILESTONES.md` — phased roadmap
- `ROADMAP.md` — GitHub Milestone/Issue-formatted version of the roadmap
- `api-spec-v0.1.md` — the Python backend API endpoints being migrated to

## Current state (as of this handoff)

- Infra: Tailscale mesh (mini PC orchestrator + 2 MacBooks + a relay-based
  Ollama server), n8n running on the mini PC via Docker Compose, Postgres
  alongside it, Telegram bot fully wired and working
- Stock agent is **fully working inside n8n**: Trigger → LLM classify
  (local Ollama, `qwen3.5:9b`, requires `"think": false` in the request
  body or JSON lands in the wrong response field) → parse → Switch →
  4 branches (check/add/remove/list), all tested and working
- **In progress**: migrating this n8n logic into a Python (FastAPI) backend
  so n8n becomes a thin trigger layer (Trigger → HTTP Request → Reply),
  per `api-spec-v0.1.md`. This is Milestone 1 in `ROADMAP.md`.
- Not yet built: heartbeat/proactive alerts, any agent beyond stock

## Key architectural decisions (don't relitigate these without cause)

1. **n8n stays only as a thin trigger/routing layer.** All real logic
   (prompts, SQL, API calls) belongs in the Python backend, callable via
   simple HTTP endpoints. This was a deliberate choice so migrating off
   n8n later doesn't require rewriting agent logic — reasoning documented
   in `README.md` under "why n8n first."

2. **Local LLM (Ollama) for classification, cloud (Claude API) reserved
   for genuine reasoning tasks** (parsing ambiguous input, news relevance
   scoring). Classification is cheap/frequent/low-stakes — doesn't need a
   frontier model. See README's "Local LLM vs Claude API" section.

3. **Each agent has a small, explicit, fixed command set** — not
   open-ended natural language capability. E.g. stock agent only supports
   `check/add/remove/list`. This was a deliberate scope decision, not a
   limitation to "fix" — see the design discussion that led to
   `docs/MILESTONES.md`'s "explicitly out of scope" notes per phase.

4. **Heartbeat pattern borrowed from OpenClaw** (not their codebase, just
   the pattern): a scheduled check that stays silent unless something's
   actually notable, rather than a chatty periodic status message. See
   Milestone 2 in `ROADMAP.md`. Explicitly did **not** adopt OpenClaw's
   Gateway/multi-channel/skill-marketplace architecture — that solves
   problems (20+ channels, device pairing, model failover) this project
   doesn't have. Also explicitly avoided their "tool execution has full
   user permissions" pattern — each agent's action set stays scoped.

5. **LangGraph/multi-step orchestration is intentionally NOT used for the
   core 5 agents** — their logic is simple classify+route+execute, plain
   Python conditionals are sufficient. It's reserved for the separate trip
   planner concept (see Backlog in `ROADMAP.md`), which genuinely needs
   multi-step research + feasibility-checking loops. Don't introduce
   LangGraph/CrewAI into the core agents without a concrete case for why
   plain routing is insufficient.

6. **Postgres for structured state, not vector/embedding search.** Each
   agent's data (watchlist, future task list, etc.) is small and
   explicitly structured — a vector DB would be solving a recall problem
   this project doesn't have.

## Known gotchas (see docs/JOURNAL.md for full detail)

- Local reasoning models (Qwen3) put JSON in the `thinking` field unless
  `"think": false` is explicitly passed
- n8n's HTTP Request node needs raw JSON body mode, not "Body Parameters"
  rows, or booleans get sent as strings
- Postgres `DELETE ... RETURNING` + n8n's "Always Output Data" setting
  interact: check for the actual returned field, not just item count,
  or you get "Removed undefined" on a no-op delete

## What to do first in a new session

1. Read `ROADMAP.md`, find the next unchecked item under the current
   Milestone
2. Check `docs/JOURNAL.md` if you hit an infra issue — it may already be
   solved there
3. Cross-reference `api-spec-v0.1.md` before writing any new endpoint —
   the shape of each endpoint (request/response format) is already decided
