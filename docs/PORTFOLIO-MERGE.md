# Portfolio merge + leaving n8n — handoff

Written 2026-09-29 as a handoff from a planning conversation in claude.ai.
It records what was built, what was decided and why, and the order to do
the work in. Read it together with `CLAUDE.md` and `ROADMAP.md`.

## Background

A separate project, the **portfolio orchestrator**, was built and tested
outside this repo. It is in `reference/portfolio-orchestrator/` (unzipped
from `portfolio-orchestrator.zip`). It contains:

- `portfolio-tracker/`: a single-user portfolio web app. Standard-library
  Python, `server.py` + `static/index.html`, data in `data/portfolio.json`.
  It has been patched with a **revision check** so two writers can't
  overwrite each other (see "Things to preserve").
- `orchestrator/`: a Mac launchd service. It combines a Telegram bot
  (long polling, owner-only), an app supervisor, a confirm → write → audit
  → undo pipeline, and a `portfolio` plugin that parses free-text edits
  with the Claude API. It has 16 passing end-to-end tests
  (`orchestrator/tests/`).

**Decision:** we will not run it as a second system. Nexus is the one
system and the one Telegram bot. The orchestrator's pieces get ported into
`nexus-backend`, and this work also carries out the long-planned move off
n8n.

Treat `reference/` as source material to port from, not code to import.
Add `reference/` to `.gitignore`.

## Decisions (made in the planning conversation, don't relitigate without cause)

1. **Nexus owns Telegram, through long polling in `nexus-backend`.** A bot
   token has exactly one consumer: either a webhook or `getUpdates`. Moving
   ingress into the backend retires the n8n `agent-slim` workflow, and
   eventually removes the need for Tailscale Funnel.
2. **The mini PC hosts everything,** including the portfolio tracker, which
   moves off the Mac. The mini PC is always on; a Mac that sleeps makes the
   bot go silent.
3. **The Portfolio agent uses the Claude API for parsing free-text edits;
   the top-level router stays on local Ollama.** This matches the existing
   rule in CLAUDE.md: Claude for ambiguous, high-stakes parsing. The model
   is configurable; the default is `claude-haiku-4-5`.
4. **The LLM only proposes.** It returns a fixed set of typed operations
   (see `plugins/portfolio/__init__.py`, `TOOL`). Deterministic code in
   `ops.py` validates and applies them. **Every write needs an explicit
   Confirm button press.** Confirm/Cancel previews expire after 10 minutes.
5. **Chat shows percentages only for the portfolio** (the owner's choice).
   Dollar amounts appear only in the tracker web page, which opens over
   Tailscale, including as a Telegram Mini App. A setting
   (`show_amounts_in_chat`) can turn dollars on in chat.
6. **The app supervisor is not ported for now.** Docker's
   `restart: unless-stopped` covers crashes. Start/stop from Telegram would
   need the Docker socket, which is root-equivalent and breaks the "scoped
   actions" rule. Port only the read-only parts: `/status` (health checks)
   and `/open` (Tailscale Serve links). Revisit later with a narrowly
   scoped helper if start/stop turns out to be needed.
7. **Remote UI goes through `tailscale serve` (tailnet only), never
   Funnel.** Each web app gets its own HTTPS port, because the tracker
   uses absolute `/api/...` paths and can't live under a sub-path.
8. **Secrets go in `.env` / compose environment,** following the existing
   repo pattern. The macOS Keychain code in `orch/secrets.py` is Mac-only;
   don't port it. New variables: `TELEGRAM_BOT_TOKEN` (moves out of the n8n
   credential store), `TELEGRAM_OWNER_ID`, `ANTHROPIC_API_KEY`.

## Step 0 — security fixes (do these first, independently)

Found while reviewing the repo:

- **The bot answers anyone.** `workflows/agent-slim.json`'s Telegram
  Trigger has no user restriction, and `/handle` does no auth. Anyone who
  finds the bot's username can read and change family events and tasks,
  and answer `confirm N` on pending imports.
  - Fix now in n8n: restrict the trigger to the owner's user ID (a node
    option, or an IF node on `message.from.id`).
  - Also enforce `TELEGRAM_OWNER_ID` in the backend (defence in depth).
- **Ports are published on every network interface.** In
  `docker/docker-compose.yml`, `8000:8000` and `5678:5678` expose the
  unauthenticated backend and n8n to the whole LAN. Change them to
  `127.0.0.1:8000:8000` and `127.0.0.1:5678:5678`. n8n reaches the backend
  through the Docker network, and Funnel proxies to localhost, so nothing
  breaks.
- Funnel currently exposes the whole n8n editor publicly. This goes away
  in step 6.

## Migration order (each step leaves the system working)

1. **Telegram ingress in the backend**
   - `app/telegram.py`: an async long-polling task started from FastAPI
     `lifespan`, an owner allowlist (private chats only; log and ignore
     everyone else), a command and callback registry, and HTML message
     helpers.
   - It calls the existing `/handle` routing logic in-process.
   - Port the ideas from `reference/.../orch/bot.py` and `orch/telegram.py`,
     switching from `urllib` to `httpx`.
   - **Cutover gotcha:** deactivate `agent-slim` in n8n *before* starting
     the poller. While a webhook is registered, `getUpdates` fails with
     409 Conflict. Also call `deleteWebhook` once. The heartbeat and Gmail
     workflows only *send* messages, so they keep working.
   - Acceptance: existing stock/family commands work through the poller;
     parity is checked the same way `scripts/parity_check.py` did for M1.
2. **Scheduler.** Replace the three n8n cron workflows (stock heartbeat,
   family heartbeat, calendar import trigger) with a small asyncio
   scheduler in the backend, timezone-aware via `GENERIC_TIMEZONE`. Delete
   those workflows once they're verified.
3. **Shared change pipeline.**
   - Port `orch/changes.py` as `app/changes.py`, with an `audit_log` table
     in Postgres (add it to `sql/init.sql`) instead of JSONL.
   - "Before" copies can be a JSONB column.
   - Keep the semantics: proposal → Confirm/Cancel buttons → re-check the
     data fingerprint at confirm (rebuild the preview if it changed) →
     write → audit.
   - `/undo` restores the before-copy **only if the current fingerprint
     equals the recorded after-fingerprint**; otherwise refuse and explain.
   - Optional later: switch the family "confirm N / skip N" flow to buttons.
4. **Portfolio agent and tracker.**
   - Move `reference/.../portfolio-tracker` into the repo (e.g.
     `apps/portfolio-tracker/`) as a compose service. Mount `data/` as a
     volume, bind to the Docker network or `127.0.0.1`, and publish it with
     `tailscale serve --bg --https=8443 http://127.0.0.1:8765`.
   - The owner copies their real `data/` folder over from the Mac. **It
     must never be committed**; add it to `.gitignore`.
   - Add `app/agents/portfolio.py`, ported from `plugins/portfolio/`
     (`calc.py`, `ops.py`, `views.py` are pure Python and port almost
     unchanged; `client.py` switches to async `httpx`).
   - Add `portfolio` to `AGENTS` in `app/router.py` and to the router
     prompt (holdings, allocation, rebalancing, buys/sells, deposits,
     T-bills).
   - Commands: `/summary`, `/holdings`, `/growth`, `/refresh`, `/snapshot`,
     `/undo`, `/history`, `/open`, `/status`.
   - Port the tests from `reference/.../orchestrator/tests/` to pytest.
5. **Google imports.** Move the Calendar and Gmail imports out of n8n
   (Google API client plus OAuth token storage). This is the hardest part
   to leave n8n, so it's deliberately last.
6. **Decommission.** Turn off Funnel, remove n8n from compose, and update
   README, SETUP and JOURNAL.

Add these as milestones in `ROADMAP.md` (e.g. "M2.5: Leave n8n, part 1"
covering steps 1–3, and "M2.6: Portfolio agent" for step 4).

## Things to preserve when porting (easy to lose)

- **The math must match the tracker UI exactly.** `calc.py` is a port of
  the JavaScript in `static/index.html`:
  - value = qty × price; drift = actual% − target%;
  - rebalance trade = target% × total − sleeve value;
  - growth is a time-weighted index where each snapshot's `deposit` is
    removed from that period's gain.

  Keep a test that runs the UI's JS under node and compares, as was done
  during the original build.
- **Snapshot dates use UTC** (`toISOString()` in the UI). Match it; don't
  use `GENERIC_TIMEZONE` for portfolio snapshot dates.
- **T-bills are manual holdings:** qty = face ÷ 100, price per $100.
- **Buys into an existing holding** add to qty and update the weighted
  average cost. A new symbol requires a sleeve. Sells can be a qty, a
  fraction, or `all`; selling everything removes the holding.
- **Order of operations:** price refresh first, then snapshot and deposit
  last, so they capture the final holdings. A price refresh also records
  today's snapshot, like the UI's Refresh button.
- **What Claude receives:** the owner's message, sleeve ids/names/targets,
  and holding symbols/names/sleeve/manual flag. **No quantities or dollar
  values.**
- **The tracker's revision check** (`rev` field; 409 on a stale save; the
  UI shows a Reload banner and auto-refreshes when the tab regains focus).
  Every backend write must send the `rev` it read.
- **The owner check applies to every message *and* every button press.**
  Ignore group chats. Log rejected attempts without their message content.

## Open questions to confirm with the owner before starting

- The mini PC's OS and whether the tracker runs as a container or on the
  host. Container is the default assumption.
- Which Claude model to use for portfolio parsing. Default:
  `claude-haiku-4-5`.
- Whether to delete the portfolio orchestrator's Mac launchd service once
  step 4 is live. Expected: yes, with `scripts/uninstall_service.sh`.
