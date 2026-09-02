# Roadmap — GitHub Project Plan

Format: each `##` is a Milestone (create as a GitHub Milestone), each `- [ ]`
under it is an Issue (create as a GitHub Issue, assign to that Milestone).
Suggested Project board columns: **Backlog → In Progress → Done**.

---

## Milestone 1: Python Backend Migration (Stock Agent) — DONE
Goal: move existing working n8n logic into a real, testable Python service.
No new functionality — this is a straight port, verified against current
n8n behavior at each step.

- [x] Scaffold FastAPI project (`nexus-backend/`), Dockerfile, add to
      docker-compose alongside n8n/Postgres
- [x] Implement `/agents/stock/handle` (combined endpoint — classify +
      route + execute, see api-spec-v0.1.md)
- [x] Port classify prompt from n8n's HTTP Request node
- [x] Port `check` logic (Alpha Vantage call + formatting)
- [x] Port `add` logic (Postgres INSERT, UPPER() normalization)
- [x] Port `remove` logic (Postgres DELETE...RETURNING, the
      optional-chaining fix for "wasn't on your watchlist")
- [x] Port `list` logic (Postgres SELECT + empty-list handling)
- [x] Simplify n8n workflow to 3 nodes: Trigger → HTTP Request → Reply
      (`workflows/stock-agent-slim.json`; steps in `docs/BACKEND-CUTOVER.md`)
- [x] Side-by-side test: `scripts/parity_check.py` (11 cases) + full
      command set re-run end-to-end through Telegram against the backend
- [x] Decommission old n8n branches — done wholesale: the n8n_data volume
      was wiped during setup, so the old fat workflow (Switch, per-branch
      Postgres nodes, etc.) is gone. Only the slim workflow was re-imported.

Notes:
- Bound params (`$1`) replace n8n's `UPPER('...')` string interpolation.
- Unrecognised messages / missing tickers return usage text; the old n8n
  Switch defaulted to `check` and threw on a null ticker.

## Milestone 2: Heartbeat Pattern (borrowed from OpenClaw)
Goal: proactive alerts, not just reactive commands.

- [x] Implement `/agents/stock/heartbeat` endpoint — deterministic
      threshold check (>= `HEARTBEAT_MOVE_THRESHOLD_PCT`, default 5%) across
      watchlist; no LLM. Returns `{alert:false}` or `{alert:true, text}`.
- [x] Add n8n Cron trigger → call heartbeat endpoint → only send Telegram
      message if `alert: true` (`workflows/stock-heartbeat.json`; default
      is one midday run/weekday — Alpha Vantage free tier is 25 req/day and
      each run is one request per ticker, see `docs/HEARTBEAT.md`)
- [ ] Verify "quiet on a normal day" behavior — run for a full day, confirm
      no spam when nothing notable happens (steps in `docs/HEARTBEAT.md`)
- [x] Document the pattern as reusable for future agents — `docs/HEARTBEAT.md`
      (linked from README)

> **Roadmap restructured (2026-09-01) after the M3 planning discussion.**
> Two kinds of "task" fell out of it:
> - **Task** = a small action item that always belongs to a domain
>   ("research NVDA earnings" → stock; "book dentist" → family). Just
>   `done: yes/no` + optional due date. NOT its own agent — a shared
>   capability every agent embeds, backed by one `tasks` table with a
>   `domain` column and an optional `project_id`.
> - **Project** = a big, named, multi-step effort with its own priority,
>   cadence, and progress log (job interview, kitchen remodel). Its own
>   agent (was "Home Project Tracker", now generalized).
>
> So: old M4 "Task agent" is **dissolved**; old M5 "Home Project Tracker"
> becomes the **Project agent** and moves up to M4. Decisions locked:
> M3 is manual-entry only (import is M3.5); Google Calendar sync is
> **read-only** (GCal stays source of truth); **local Ollama for all
> classification/parsing for now** — revisit Claude API only if relative-date
> parsing ("next Friday") proves unreliable in practice.

## Milestone 3: Family / Household Agent + shared task capability
Goal: second agent (proves the router pattern with 2+ agents), and a
central hub for family events + family to-dos. Manual entry only.

- [ ] Design schema: `family_events` (calendar shape) + shared `tasks`
      table (`domain`, `title`, `status`, `due_date?`, `notes`,
      `project_id?`) — added to `sql/init.sql`
- [ ] Implement `/router/classify` — top-level agent dispatch (stock |
      family), local Ollama, called by n8n before the per-agent endpoint
- [ ] Shared `app/tasks.py` — `add` / `list` / `done` / `remove`, scoped
      by `domain`; each agent delegates its task subcommands here
- [ ] Implement `/agents/family/handle` — sub-classify `event` vs `task`,
      then: events `add` / `list` / `remove` / `next`; tasks via `tasks.py`
- [ ] `/agents/family/heartbeat` — morning digest: today's events + tasks
      due/overdue. Quiet if nothing.
- [ ] n8n: router workflow (Trigger → /router/classify → HTTP to the
      chosen agent → Reply) + family heartbeat Cron workflow

## Milestone 3.5: Calendar & email import (family)
- [ ] `/agents/family/import` — accept normalized items, dedupe/upsert by
      (`source`, `external_id`)
- [ ] n8n Google Calendar node (OAuth) → scheduled pull of upcoming events
      → POST to import endpoint (read-only; GCal is source of truth)
- [ ] n8n Gmail node → filter household senders → local-LLM extract
      candidate events → Telegram "add this? y/n" confirm loop → import

## Milestone 4: Project Agent
Generalized from the old "Home Project Tracker" — any big multi-step effort
(job interview, home improvement, personal build), not just home projects.

- [ ] Schema: `projects` (name, `domain?`, status, priority, cadence,
      next_action, notes/log, created_at)
- [ ] `/agents/project/handle` — add / list / update / close, log progress
- [ ] Tasks attach to a project via `tasks.project_id`
- [ ] `/agents/project/heartbeat` — stale-project nudge + cadence-based
      check-in prompt
- [ ] (Optional, later) Claude Code headless integration for
      software-type projects — separate sub-milestone, not required

## Milestone 4.5: Task subcommands in the stock agent
- [ ] `/agents/stock/handle` recognises `task` intents, delegates to
      `tasks.py` with `domain='stock'` ("research NVDA earnings",
      "design trading schedule")

## Milestone 5: News Curation Agent
- [ ] RSS ingestion
- [ ] Relevance scoring + feedback-adjusted source weighting
- [ ] Heartbeat: scheduled digest delivery

## Backlog / Not Scheduled
- [ ] Trip planner (see separate MVP brief — likely needs LangGraph-style
      multi-step research, different shape from the other agents; treat as
      its own track, not a milestone in this sequence)
- [ ] Packaged installer (Windows/Mac) — only after 3+ agents proven, per
      earlier discussion on deployment
- [ ] Multi-user / family-shared permissions
- [ ] "All open tasks across every domain" query (enabled by the shared
      `tasks` table — trivial once >1 domain uses it)

---

## Suggested GitHub setup

```bash
# Create milestones (repeat per milestone above)
gh api repos/:owner/:repo/milestones -f title="M1: Python Backend Migration"

# Create issues under a milestone (repeat per checklist item)
gh issue create --title "Implement /agents/stock/handle" \
  --milestone "M1: Python Backend Migration" \
  --body "See api-spec-v0.1.md section 2"
```

Or simpler: paste each Milestone section directly into GitHub's Projects
UI as a new view, one card per checkbox line — faster than scripting this
for a project this size.
