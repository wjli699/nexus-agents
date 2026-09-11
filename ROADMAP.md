# Roadmap — GitHub Project Plan

Format: each `##` is a Milestone (create as a GitHub Milestone), each `- [ ]`
under it is an Issue (create as a GitHub Issue, assign to that Milestone).
Suggested Project board columns: **Backlog → In Progress → Done**.

---

## 🎯 True North: Alpha-Ready Release

**Alpha means: a stranger clones the repo, runs one setup step, connects
Telegram, and has working stock + calendar/task tracking within a few
minutes — no n8n UI, no Google Cloud Console, no live debugging help
required.** Milestones 4-8 below exist to make that sentence true. M9+
(Project agent, News agent, everything in Backlog) are explicitly
post-alpha — do not pull from them until the true north above is met.

Why this reprioritization (2026-09-11): M3.5 shipped a real,
differentiated feature (Gmail extraction + confirm loop) but getting it
working live surfaced how much of the *setup* friction lives in n8n
itself (OAuth-screen UI drift, stale credential caching, node
field-name/version inconsistency, reverse-proxy header quirks) — none of
which is a Python backend bug (109 tests, zero issues found there beyond
things we could and did unit-test). That's a packaging problem, not a
feature gap, and it's the difference between an alpha someone finishes
setting up and one they abandon in the first 15 minutes.

**Positioning, not just setup ease:** the durable differentiator against
both OpenClaw-style general agents and hosted no-code agent builders
(Zapier, Lindy, etc.) isn't "easier to install" — that's a race we can't
win against companies with a hosted product. It's that every agent has a
**fixed, explicit command set**, never open-ended autonomous tool
execution (`CLAUDE.md` decisions 3 and 4's "avoided their 'tool execution
has full user permissions' pattern"). Lead the alpha's messaging with
that, not with ease-of-setup alone.

**Explicitly out of scope for alpha** (don't let these creep back in):
Project agent, News agent, multi-user/family-shared permissions, trip
planner, packaged Windows/Mac installer, a hosted/managed offering. All
real, all Backlog or M9+, none of them block the true north above.

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
- Date resolution is deterministic (`app/dates.py`), not LLM. The local
  model only extracts the date *phrase* verbatim; Python resolves it. The
  M3 accuracy probe showed qwen3.5 gets weekday math wrong ("by friday" →
  Saturday); phrase-extract + deterministic-resolve scored 11/11.

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

## Milestone 3: Family / Household Agent + shared task capability — DONE
Goal: second agent (proves the router pattern with 2+ agents), and a
central hub for family events + family to-dos. Manual entry only.

- [x] Design schema: `family_events` (calendar shape) + shared `tasks`
      table (`domain`, `title`, `status`, `due_date?`, `notes`,
      `project_id?`) — added to `sql/init.sql`
- [x] Implement `/router/classify` — top-level agent dispatch (stock |
      family), local Ollama, called by n8n before the per-agent endpoint.
      Router picks the agent only; each `/handle` sub-classifies.
- [x] Shared `app/tasks.py` — `add` / `list` / `done` / `remove`, scoped
      by `domain`; each agent delegates its task subcommands here
- [x] Implement `/agents/family/handle` — sub-classify `event` vs `task`,
      then: events `add` / `list` / `remove` / `next`; tasks via `tasks.py`.
      Also `POST /handle` (top-level): router.classify → dispatch → reply,
      so n8n is one call.
- [x] `/agents/family/heartbeat` — morning digest: events through
      today+`FAMILY_DIGEST_LOOKAHEAD_DAYS` + tasks due/overdue. Quiet if
      nothing. Deterministic.
- [x] n8n workflows: `agent-slim.json` (Trigger → POST /handle → reply —
      routing is server-side now, so n8n stays one call) + `family-
      heartbeat.json` (Cron → digest). Stock command workflow re-pointed
      from `/agents/stock/handle` to `/handle`.

## Milestone 3.5: Calendar & email import (family) — DONE
- [x] `/agents/family/import` — accept normalized items, dedupe/upsert by
      (`source`, `external_id`)
- [x] n8n Google Calendar node (OAuth) → scheduled pull of upcoming events
      → POST to import endpoint (read-only; GCal is source of truth)
- [x] n8n Gmail node → filter household senders → local-LLM extract
      candidate events → Telegram "add this? y/n" confirm loop → import

## Milestone 4: Replace n8n with a native gateway
Goal: eliminate n8n as a dependency entirely. Every real bug this whole
project has had lived in the Python backend and got caught by tests;
every hour of live-debugging pain in M3.5 was n8n's UI/version drift.
`CLAUDE.md` decision 1 already anticipated this — "migrating off n8n
later doesn't require rewriting agent logic" — this is that migration,
not a reversal.

- [ ] `app/gateway/telegram.py` — polling or webhook listener calling the
      same `/handle` the router already exposes; replaces `agent-slim.json`
- [ ] `app/gateway/scheduler.py` — in-process scheduler (e.g. APScheduler)
      replacing n8n's Cron triggers for the stock/family heartbeats
- [ ] Decommission `workflows/agent-slim.json`, `stock-heartbeat.json`,
      `family-heartbeat.json` once the gateway covers them 1:1
- [ ] Drop the `n8n` service from the default `docker-compose.yml`
      entirely (keep `docker/optional-n8n/` for anyone who still wants
      the visual builder for their *own* custom workflows on top)
- [ ] Rewrite `docs/SETUP.md` for the n8n-free path

## Milestone 5: Bundled small local LLM (CPU / small GPU)
Goal: "connect LLM" means "already there," not "separately install Ollama
and pick a model."

- [ ] Add an `ollama` service to `docker-compose.yml`, auto-pulling a
      default model on first start
- [ ] Default model: CPU-friendly, not the current `qwen3.5:9b` — 2026
      landscape points at a Qwen3.5/Qwen2.5-class 3-4B model at Q4
      quantization as the sweet spot (verify against current options
      before locking this in, this space moves fast)
- [ ] Document a lighter fallback (~1.5B class) for genuinely constrained
      hardware
- [ ] Re-run the M3 date-accuracy probe (11/11 on qwen3.5:9b) against
      whatever ships as the new default — don't assume it holds

## Milestone 6: Harden core agents for the smaller default model
Goal: stock/calendar/tasks must work solidly on the bundled model, not
just the larger one M1-M3.5 happened to be built against.

- [ ] Re-run classify/extract accuracy checks against the new default
- [ ] `temperature: 0` (done) + few-shot examples (done for email
      extraction, M3.5) — extend few-shot examples to the other classify
      prompts if the smaller model needs them
- [ ] Gmail import stays *out* of the alpha happy path — it's the most
      setup-heavy feature built so far (Google Cloud project, OAuth
      consent screen, restricted scopes). Keep it working and documented,
      but as an advanced/optional add-on, not part of guided setup

## Milestone 7: Guided setup, no Cloud Console required
Goal: "connect Telegram" is paste-a-token-and-go. "Connect Google" is
explicitly deferred out of the alpha critical path, not half-solved.

- [ ] A short guided first-run flow (CLI prompt or minimal local web
      page) for: Postgres password, Telegram bot token (link to
      @BotFather), local model choice — no `.env` hand-editing for the
      core path
- [ ] `docs/SETUP.md` rewritten around this flow
- [ ] Document Google Calendar/Gmail import explicitly as an advanced,
      optional add-on requiring the user's own Google Cloud project — not
      part of the "few minutes" guided path
- [ ] (Backlog, not alpha) a shared/managed OAuth client so "Connect
      Google Calendar" becomes one click, like Zapier/IFTTT — needs
      Google app verification and someone to own the shared client; a
      real product decision, not a code task

## Milestone 8: The multi-agent payoff
Goal: one simple, cheap feature that makes "this is one system, not five
separate single-purpose bots" tangible from day one.

- [ ] Top-level `/heartbeat` combining every agent's heartbeat into one
      daily digest instead of separate per-agent pings — still silent
      when nothing anywhere is notable
- [ ] First-message onboarding: a brand-new chat's first reply explains
      what the bot can do and prompts a first action (add a ticker / add
      an event) — zero new integrations, pure UX polish
- [ ] `/help` prints each agent's fixed command set explicitly —
      reinforces the "scoped, not open-ended" safety story in-product,
      not just in docs

---

## Post-alpha (do not pull from these until Milestones 4-8 are done)

## Milestone 9: Project Agent
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

## Milestone 9.5: Task subcommands in the stock agent
- [ ] `/agents/stock/handle` recognises `task` intents, delegates to
      `tasks.py` with `domain='stock'` ("research NVDA earnings",
      "design trading schedule")

## Milestone 10: News Curation Agent
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
- [ ] Shared/managed Google OAuth client + app verification (see M7) —
      commercial/hosted-tier territory, not core open-source scope
- [ ] Custom mobile/desktop client apps — post-alpha commercial track
      (Home Assistant / Plex / Nextcloud style: free self-hosted core
      stays fully capable forever, paid tier is convenience — a polished
      client, optional hosted relay — never a gate on core functionality)

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
