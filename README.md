# Nexus — A Personal Multi-Agent System on Telegram

Nexus is a self-hosted, mobile-first personal automation system. One Telegram bot
routes messages to small, purpose-built agents that track different parts of
life — starting with stock watchlist tracking, and designed to expand into
home/family logistics, general task tracking, news curation, and ongoing
project progress.

Built with n8n as the orchestrator, running on a home mini PC, reachable from
anywhere via Tailscale, with an LLM (local or cloud) doing lightweight
intent classification and summarization.

> This repo doubles as a build log. If you're setting up something similar,
> the [`docs/JOURNAL.md`](docs/JOURNAL.md) walks through what actually broke
> and how it got fixed — most of it wasn't in the docs.

---

## Architecture

```
                     ┌─────────────┐
    Telegram (you)   │             │
    ───────────────► │  Telegram   │
    ◄─────────────── │     Bot     │
                     └──────┬──────┘
                            │ webhook (public HTTPS via Tailscale Funnel)
                            ▼
                  ┌───────────────────┐
                  │   n8n (mini PC)   │  ← orchestrator
                  │  - Telegram node  │
                  │  - LLM classify   │
                  │  - Switch/router  │
                  │  - Postgres state │
                  └─────────┬─────────┘
                            │
              ┌─────────────┼─────────────────┐
              ▼             ▼                 ▼
      ┌──────────────┐ ┌──────────┐   ┌───────────────┐
      │ LLM (classify│ │ Postgres │   │ External APIs │
      │ /summarize)  │ │ (state)  │   │ (stock, news) │
      │ local Ollama │ └──────────┘   └───────────────┘
      │  or Claude   │
      │  API         │
      └──────────────┘
```

**Design principle:** n8n is a thin, disposable trigger/routing layer.
Real logic lives in small, swappable pieces (LLM prompts, SQL, HTTP calls) so
the orchestrator itself can be replaced later (e.g. with a custom Python
service) without rewriting the agent logic.

---

## What's built so far

- [x] Telegram bot ⟷ n8n round trip (echo test)
- [x] n8n reachable publicly via Tailscale Funnel (for Telegram webhooks)
- [x] LLM-based intent classification (local Ollama model, JSON output)
- [x] Stock agent — `check` command (Alpha Vantage price lookup)
- [x] Stock agent — `add` / `remove` / `list` (Postgres-backed watchlist)
- [x] Stock agent logic migrated to a Python (FastAPI) backend; n8n is now
      a 3-node thin layer (Trigger → HTTP Request → Reply). See `nexus-backend/`
- [ ] Stock agent — scheduled/proactive alerts
- [ ] Home/family agent (email + calendar tracking)
- [ ] General task/goal tracking agent
- [ ] News curation agent
- [ ] Home project tracker (+ optional Claude Code headless integration
      for software-type projects)

See [`docs/MILESTONES.md`](docs/MILESTONES.md) for the fuller roadmap.

---

## Repo structure

```
nexus/
├── README.md                          this file
├── .env.example                       template for secrets — copy to .env
├── .gitignore
├── nexus-backend/                     FastAPI service — agent logic migrated out of n8n (Milestone 1)
├── docker/
│   ├── docker-compose.yml             DEFAULT setup: n8n + Postgres + nexus-backend
│   └── optional-ollama-tailscale/
│       ├── docker-compose.ollama-local.yml       Ollama on same host, no Tailscale
│       └── docker-compose.ollama-tailscale.yml   Ollama as Tailscale sidecar (separate host)
├── sql/
│   └── init.sql                       watchlist table + future agent tables
├── workflows/
│   ├── workflows.json                 exported n8n workflow (see docs/EXPORTING.md)
│   ├── stock-agent-slim.json          3-node workflow that calls nexus-backend
│   └── stock-heartbeat.json           Cron → heartbeat endpoint → alert if notable
├── scripts/
│   └── parity_check.py                backend vs n8n behaviour check (Milestone 1)
└── docs/
    ├── JOURNAL.md                     what we actually hit building this, in order
    ├── MILESTONES.md                  roadmap / checklist
    ├── SETUP.md                       clean step-by-step setup from zero
    ├── EXPORTING.md                   how to export/version your n8n workflows
    ├── BACKEND-CUTOVER.md             swapping n8n over to nexus-backend
    └── HEARTBEAT.md                   the scheduled-but-silent alert pattern
```

---

## Quick start

See [`docs/SETUP.md`](docs/SETUP.md) for the full walkthrough. Short version:

```bash
# 1. Network mesh (once, on every device you want connected)
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up

# 2. Clone this repo on your orchestrator host (e.g. a mini PC)
git clone <your-repo-url> nexus
cd nexus/docker

# 3. Configure secrets
cp ../.env.example .env
# edit .env with your actual values

# 4. Bring up n8n + Postgres
docker compose up -d

# 5. Expose it to Telegram's servers (public webhook requirement)
sudo tailscale funnel --bg 5678

# 6. Open the editor
open https://<your-tailnet-hostname>.ts.net
```

Then follow `docs/SETUP.md` from the "Build the Telegram bot" section onward.

---

## Local LLM vs Claude API — why both exist here

Not every task needs a frontier model. This project deliberately splits work:

| Task | Model | Why |
|---|---|---|
| Classify a short command into JSON (`check AAPL` → `{action, ticker}`) | Local (Ollama) | Cheap, frequent, low-stakes, doesn't need deep reasoning |
| Summarize/reason over ambiguous input (parsing an unstructured email, scoring news relevance) | Claude API | Needs actual judgment; local small models are noticeably less reliable at this |

The `docker/optional-ollama-tailscale/` configs are there if you want to run
your own local model server on separate hardware. The default compose file
assumes you already have *some* LLM endpoint reachable (local or cloud) and
just wires n8n to call it — swap the URL/credentials in the workflow's HTTP
Request node.

---

## Cost reality check

For personal-scale usage (a handful of commands a day across 5 agents), Claude
API costs a few dollars a month — not worth over-engineering a local-only
setup purely to save money. Use local models where you want zero cloud
dependency or are already running the hardware for other reasons (e.g. edge
AI development), not as the default cost-optimization move.

---

## License

MIT — do whatever you want with this.
