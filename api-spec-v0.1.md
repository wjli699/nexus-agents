# Python Backend API Spec — v0.1

Purpose: replace n8n's in-node logic (HTTP Request bodies, Code node JS,
inline SQL) with a small set of real, testable Python endpoints. n8n's job
shrinks to: receive Telegram message → POST to one endpoint → send back
whatever text comes back.

Each endpoint below corresponds to logic that currently lives inside an
n8n node. Build in the order listed — this order matches what's already
working in n8n, so each migration step is a direct, verifiable port, not a
redesign.

Stack assumption: FastAPI + the existing Postgres instance + your existing
LLM endpoint (local Ollama or Claude API) + Alpha Vantage.

---

## 0. Router (build last, once 2+ agents exist)

Not needed for v0.1 with only the stock agent live — but specced now so
the shape is known in advance.

```
POST /router/classify
  body: { "message": "what is AAPL trading at" }
  returns: { "agent": "stock", "raw_action": "check", "ticker": "AAPL" }
```
Wraps the LLM classification call. Once agent #2 exists, this becomes the
single entry point n8n calls first, before dispatching to a per-agent
endpoint below.

---

## 1. Stock Agent — v0.1 required endpoints

This is the actual v0.1 scope. Everything else in this doc is roadmap
context, not required to ship.

### 1.1 Classify
```
POST /agents/stock/classify
  body: { "message": "what is AAPL trading at" }
  returns: { "action": "check", "ticker": "AAPL" }
```
Direct port of: HTTP Request (Ollama) node + Code (parse) node.

### 1.2 Check price
```
POST /agents/stock/check
  body: { "ticker": "AAPL" }
  returns: { "text": "AAPL: $227.14 (+0.8%)" }
  errors: { "text": "Couldn't find data for that ticker." }
```
Direct port of: HTTP Request (Alpha Vantage) node + formatting Code node.

### 1.3 Add to watchlist
```
POST /agents/stock/add
  body: { "ticker": "AAPL" }
  returns: { "text": "Added AAPL to your watchlist." }
```
Direct port of: Postgres INSERT node (`ON CONFLICT DO NOTHING`, `UPPER()`).

### 1.4 Remove from watchlist
```
POST /agents/stock/remove
  body: { "ticker": "AAPL" }
  returns: { "text": "Removed AAPL from your watchlist." }
  or:     { "text": "AAPL wasn't on your watchlist." }
```
Direct port of: Postgres DELETE...RETURNING node + Code node (the
`removedTicker` optional-chaining fix).

### 1.5 List watchlist
```
GET /agents/stock/list
  returns: { "text": "Your watchlist:\nAAPL\nTSLA" }
  or:      { "text": "Your watchlist is empty." }
```
Direct port of: Postgres SELECT node + formatting Code node.

### 1.6 Heartbeat (new — not yet built in n8n, see roadmap)
```
POST /agents/stock/heartbeat
  body: {}  (no input — reads full watchlist itself)
  returns: { "alert": false }
  or:      { "alert": true, "text": "TSLA down 6.2% today — biggest mover on your list." }
```
This is the OpenClaw-pattern addition: called on a schedule (n8n Cron
node), checks all watchlist tickers against a threshold rule, returns
`alert: false` (nothing sent to Telegram) on a normal day, or `alert: true`
with text on a notable move. Deterministic threshold logic + one LLM call
only to phrase the "why," not to decide whether to alert.

---

## 2. One combined endpoint (alternative to 1.1–1.5, pick one style)

Instead of 5 separate endpoints, you could expose one:
```
POST /agents/stock/handle
  body: { "message": "what is AAPL trading at" }
  returns: { "text": "AAPL: $227.14 (+0.8%)" }
```
This does classify + route + execute internally and n8n only ever calls
this one endpoint. **Recommended** — matches the "thin n8n" goal most
directly: n8n workflow becomes Trigger → HTTP Request → Telegram reply,
three nodes total, regardless of how many commands the agent supports
internally.

---

## 3. Future agents (stubbed shape only — not part of v0.1)

Not to be built yet. Listed so the pattern is visible in advance and each
future agent's endpoint count doesn't come as a surprise.

```
POST /agents/family/handle       — calendar/reminder/school-activity commands
POST /agents/family/heartbeat    — daily digest of upcoming dates

POST /agents/task/handle         — add/update/list/close tracked items
POST /agents/task/heartbeat      — stale-item nudges

POST /agents/home-project/handle — log progress, list projects
POST /agents/home-project/heartbeat — weekly check-in prompt

POST /agents/news/handle         — on-demand digest request
POST /agents/news/heartbeat      — scheduled digest delivery
```

---

## Progress checklist (update as you build)

- [ ] `/agents/stock/handle` (combined, recommended) — or 1.1–1.5 separately
- [ ] `/agents/stock/heartbeat`
- [ ] n8n workflow simplified to Trigger → HTTP Request → Telegram reply
- [ ] `/router/classify` (only once agent #2 starts)
