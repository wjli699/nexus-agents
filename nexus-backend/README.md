# nexus-backend

FastAPI service that holds the agent logic being migrated out of n8n nodes
(ROADMAP.md Milestone 1). n8n shrinks to Trigger → HTTP Request → Reply and
calls the endpoints here.

Endpoint shapes are fixed in [`../api-spec-v0.1.md`](../api-spec-v0.1.md) —
check it before adding a route.

## Current state

`POST /handle` — **what n8n calls.** Runs the top-level router, dispatches
to the chosen agent's `handle()`, returns `{text}`. n8n stays one HTTP call.

`POST /router/classify` — just the routing step (`stock` | `family` |
`unknown`), exposed for debugging. Local Ollama, one call.

`POST /agents/family/handle` — family hub: sub-classifies `event` vs
`task`, then events `add`/`list`/`remove`/`next` (table `family_events`) or
tasks via the shared `app/tasks.py` (`domain='family'`). Manual entry only
in M3; calendar/email import is M3.5. Recurring events (yearly birthdays
etc.) roll their next occurrence forward.

Dates: the local model extracts the date *phrase* verbatim
(`"by friday"`, `"end of next week"`); `app/dates.py` resolves it
deterministically. Local models get weekday math wrong, so it never does
the arithmetic. Unresolvable phrase → the agent asks for `YYYY-MM-DD`.

`POST /agents/stock/handle` — command path: classify → route → dispatch to
`check` (Alpha Vantage GLOBAL_QUOTE) / `add` (INSERT) / `remove`
(DELETE … RETURNING) / `list` (SELECT). n8n is a 3-node workflow
(`workflows/stock-agent-slim.json`) that POSTs here and replies.

`POST /agents/stock/heartbeat` — proactive path (M2): scans the watchlist,
returns `{"alert": false}` on a normal day or
`{"alert": true, "text": "..."}` when a ticker moved at least
`HEARTBEAT_MOVE_THRESHOLD_PCT` (default 5%) on the day. Detection and
phrasing are both deterministic — no LLM. Optional `{"threshold_pct": N}`
body overrides the default. n8n calls this on a Cron schedule and only
messages Telegram when `alert` is true.

DB-backed executors use bound params (`$1`), not the string-interpolated
`UPPER('...')` SQL the n8n nodes used.

## Layout

```
app/
├── main.py            FastAPI app + lifespan (DB pool) + /health
├── config.py          env-var settings (mirrors compose Postgres vars)
├── db.py              asyncpg pool lifecycle
├── llm.py             intent classification (Ollama call + defensive parse)
├── agents/
│   └── stock.py       classify + route + execute; per-action executors
└── routers/
    └── stock.py       /agents/stock/* — the stock agent HTTP surface
tests/                 routing + parse tests (LLM call stubbed, no network)
```

## Run locally

```bash
cd nexus-backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
# point at a reachable Postgres + LLM (defaults assume the compose network)
export POSTGRES_HOST=localhost POSTGRES_PASSWORD=... LLM_BASE_URL=http://...
uvicorn app.main:app --reload --port 8000
```

Or via Docker Compose (from `docker/`): `docker compose up -d nexus-backend`.
Inside that network other services reach it at `http://nexus-backend:8000`.

## Tests

```bash
pip install pytest
python -m pytest
```
