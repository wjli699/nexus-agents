# Milestones & Roadmap

> For the current, authoritative plan from Milestone 3 onward — including the
> 2026-09-01 restructure (tasks became a shared capability, not an agent;
> "Home Project Tracker" became a general Project agent) — see
> [`../ROADMAP.md`](../ROADMAP.md). The phase notes below are the original
> framing and design rationale, kept for context.

## Phase 0 — Infrastructure (done)
- [x] Tailscale mesh across all devices (mini PC, MacBook Pro, MacBook Air)
- [x] n8n running on mini PC via Docker Compose
- [x] n8n publicly reachable via Tailscale Funnel (required for Telegram webhooks)
- [x] Telegram bot created, connected to n8n, full round-trip (echo) confirmed
- [x] Local LLM (Ollama, remote host) reachable and returning clean JSON for
      simple classification tasks

## Phase 1 — Stock Agent (in progress)
Scope deliberately kept small and explicit rather than open-ended natural
language — see rationale in journal / design discussion.

- [x] Intent classification: message → `{action, ticker}` via local LLM
- [x] `check <TICKER>` — current price lookup (Alpha Vantage)
- [x] `add <TICKER>` — add to Postgres-backed watchlist
- [x] `remove <TICKER>` — remove from watchlist
- [x] `list` — show current watchlist
- [x] Logic migrated from n8n nodes to the FastAPI backend (`nexus-backend/`);
      n8n reduced to Trigger → HTTP Request → Reply (ROADMAP Milestone 1)
- [ ] Scheduled check (cron trigger) — daily/periodic scan of watchlist
- [ ] Threshold-based alerts (e.g. "notify if drops >5% in a day") —
      keep alert *logic* deterministic/rule-based, use LLM only to explain
      *why* a move happened, not to decide whether to alert

**Explicitly out of scope for this agent:**
- "Why did it drop" / news-driven analysis → belongs to the news agent
- Trade execution of any kind

## Phase 2 — Home / Family Agent
- [ ] Email polling for household-relevant messages (bills, school notices,
      appointment confirmations, etc.)
- [ ] Calendar integration — reminders for recurring dates and events
- [ ] Structured tracking for recurring household items (appointments,
      activities, deadlines) — likely a mix of calendar/email parsing and
      some manual entry, since many sources (schools, local services) don't
      expose an API; evaluate scraping case by case given ToS constraints

## Phase 3 — Task / Goal Tracking Agent
A general-purpose structured tracker for anything with discrete stages and
follow-ups — the shape generalizes across many use cases (applications,
approvals, multi-step processes with a status and a next action).

- [ ] Structured state table: item, status, last-update-date, next-action, notes
- [ ] Source parsing → auto-update tracker (LLM extracts structured fields
      from unstructured input like emails or forwarded messages)
- [ ] Stale-item flagging ("no update in N days")
- [ ] Optional: suggestion feed from an external source (RSS or saved
      search) relevant to whatever the tracker is being used for

## Phase 4 — News Curation Agent
- [ ] RSS ingestion from chosen sources
- [ ] LLM relevance scoring (1-5) per item
- [ ] Feedback loop: thumbs up/down adjusts a per-source weighting table
      (this is a ranking heuristic, not model fine-tuning — cheaper, more
      transparent, easier to debug)

## Phase 5 — Home Project Tracker
A tracker for any ongoing project with periodic check-ins — home
improvement, a personal build, a recurring hobby project, or anything else
worked on incrementally over weeks/months.

- [ ] Weekly cron check-in prompt, logged to a simple progress table
- [ ] Monthly rollup summary
- [ ] **Optional — for software-type projects only**: Claude Code
      integration to assign scoped implementation/test tasks via headless
      mode (`claude -p`) or GitHub Actions (`anthropics/claude-code-action`)
      - Keep tasks narrowly scoped — well-defined units, not open-ended goals
      - Gate to PR-creation, not direct pushes to main
      - Prefer GitHub Actions over SSH-to-laptop where the repo is on GitHub,
        removes laptop-awake as a dependency

## Cross-cutting / later
- [ ] Router/classifier layer once multiple agents share the one Telegram bot
      (single LLM call: "which of these domains does this belong to")
- [ ] Migrate orchestration logic out of n8n into a small Python service,
      if/when n8n's node-canvas approach becomes limiting (see README's
      "why n8n first" rationale) — the plan is for n8n to stay a thin
      trigger layer so this migration doesn't require rewriting agent logic
- [ ] Consider LangGraph only if genuine multi-agent coordination is needed
      (e.g. a reviewer agent critiquing an implementer agent's PR) — not
      needed for simple routing, which a single classify+switch handles fine
