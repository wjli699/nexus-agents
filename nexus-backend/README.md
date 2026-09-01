# nexus-backend

FastAPI service that holds the agent logic being migrated out of n8n nodes
(ROADMAP.md Milestone 1). n8n shrinks to Trigger → HTTP Request → Reply and
calls the endpoints here.

Endpoint shapes are fixed in [`../api-spec-v0.1.md`](../api-spec-v0.1.md) —
check it before adding a route.

## Current state

Scaffold only. `GET /health` works; `POST /agents/stock/handle` is a 501
stub. Each ROADMAP M1 item fills in one port from the n8n workflow.

## Layout

```
app/
├── main.py            FastAPI app + lifespan (DB pool) + /health
├── config.py          env-var settings (mirrors compose Postgres vars)
├── db.py              asyncpg pool lifecycle
└── routers/
    └── stock.py       /agents/stock/* — the stock agent HTTP surface
tests/                 smoke tests (no DB/LLM needed)
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
