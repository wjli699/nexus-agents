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
- [ ] Add n8n Cron trigger (e.g. every 30–60 min during market hours) →
      call heartbeat endpoint → only send Telegram message if
      `alert: true`
- [ ] Verify "quiet on a normal day" behavior — run for a full day, confirm
      no spam when nothing notable happens
- [ ] Document the pattern in README as reusable for future agents
      (family digest, task nudges, etc.)

## Milestone 3: Family / Household Agent
Goal: second agent, proves the router pattern works with 2+ agents.

- [ ] Design schema: what does "family" need to track first? (start
      narrow — e.g. just important dates, not full calendar sync)
- [ ] Implement `/router/classify` — top-level agent dispatch, now that
      there's more than one agent to route to
- [ ] Implement `/agents/family/handle` with a small fixed command set
      (mirror the stock agent's `check/add/remove/list` shape)
- [ ] Sub-router if needed (e.g. family → school vs family → dates) —
      only add this layer if the flat command set actually gets crowded,
      don't add it preemptively
- [ ] Heartbeat: daily/weekly digest of upcoming dates

## Milestone 4: Task / Goal Tracking Agent
- [ ] Schema: item, status, last-update, next-action, notes
- [ ] `/agents/task/handle` — add/update/list/close
- [ ] Heartbeat: stale-item nudge ("no update in N days")

## Milestone 5: Home Project Tracker
- [ ] Schema: project, week-of, summary
- [ ] `/agents/home-project/handle` — log progress, list projects
- [ ] Heartbeat: weekly check-in prompt
- [ ] (Optional, later) Claude Code headless integration for
      software-type projects specifically — separate sub-milestone, not
      required for this agent to be useful

## Milestone 6: News Curation Agent
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
- [ ] Deeper OAuth integrations (Gmail, Calendar) for family agent

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
