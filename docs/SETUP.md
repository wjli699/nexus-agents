# Setup Guide

Clean walkthrough from zero. If something breaks, check
[`JOURNAL.md`](JOURNAL.md) first — most likely it's already been hit and
documented there.

## Prerequisites

- A machine to act as the always-on orchestrator (a mini PC, home server, or
  cheap VPS — doesn't need much power, this is I/O-bound work)
- Docker + Docker Compose installed on it
- A [Tailscale](https://tailscale.com) account (free for personal use)
- A Telegram account

---

## 1. Network mesh (Tailscale)

Install on every device you want connected (orchestrator, laptops, any
additional servers):

```bash
curl -fsSL https://tailscale.com/install.sh | sh   # Linux
# or: brew install tailscale                        # macOS
sudo tailscale up
```

First run opens a browser URL — log in with the same account on every
device so they land in the same tailnet. Verify:

```bash
tailscale status
```

Recommended: in the [admin console](https://login.tailscale.com/admin),
disable key expiry for always-on boxes (orchestrator, any dedicated servers)
so they don't drop off the tailnet after the default 90-day expiry.

---

## 2. Clone this repo on the orchestrator

```bash
git clone <your-repo-url> nexus
cd nexus
cp .env.example .env
```

Edit `.env` with real values — see comments in the file for what each one
means. At minimum you need:
- `N8N_ENCRYPTION_KEY` — generate with `openssl rand -base64 32`
- `POSTGRES_PASSWORD` — anything reasonably strong
- Your Tailscale hostname (see step 3 for how to find it)

---

## 3. Bring up n8n + Postgres

```bash
cd docker
docker compose up -d
docker compose logs n8n --tail 20   # confirm clean startup, no crash loop
```

Find your orchestrator's Tailscale hostname:
```bash
tailscale status   # your own device's name is shown, or check the admin console
```

---

## 4. Expose n8n publicly (required for Telegram webhooks)

Telegram's servers need to reach your webhook from the public internet —
Tailscale's tailnet-only `serve` is not sufficient for this (see Journal #5).

```bash
sudo tailscale funnel --bg 5678
tailscale funnel status   # confirm it shows "(Funnel on)"
```

Update `.env` / your compose environment to match this hostname
(`WEBHOOK_URL`, `N8N_HOST`) and recreate the container so the values take
effect:

```bash
docker compose down
docker compose up -d --force-recreate
```

---

## 5. Open n8n and create your owner account

Visit `https://<your-hostname>.ts.net` in a browser. First load prompts you
to create a local owner account (email/password — stored only in your own
Postgres, not sent anywhere external).

---

## 6. Create your Telegram bot

1. Message **@BotFather** on Telegram → `/newbot`
2. Follow the prompts, get your bot token
3. Keep the token handy — don't commit it anywhere, it goes into an n8n
   credential (encrypted at rest by n8n), not into this repo

---

## 7. Build the Telegram round-trip workflow

In the n8n editor:

1. New workflow → add node → search `Telegram` (see Journal #4 if the
   Trigger doesn't show up in a plain node-name search)
2. Add the **On message** trigger, create a credential with your bot token
3. Add a **Send a text message** action node after it:
   - Chat ID: `{{ $json.message.chat.id }}`
   - Text: `{{ $json.message.text }}` (echo, just to confirm the pipe works)
4. **Publish** the workflow (not "Execute workflow" — see Journal #8, that
   only creates a temporary test webhook)

Message your bot from Telegram. Check n8n's **Executions** tab — you should
see both nodes run. You should also get the echo back on your phone.

If you edit the workflow later and the change doesn't seem to take effect,
see Journal #9 (unpublish/republish).

---

## 8. Wire up an LLM for classification

You need something that can turn a short message into structured JSON. Two
options — this repo's default workflow assumes you have *one* reachable
endpoint, doesn't matter which:

**Option A — Claude API** (simplest, costs a few dollars/month at this scale)
- Get a key from [console.anthropic.com](https://console.anthropic.com)
- Note: separate billing from any claude.ai Pro/Max subscription (Journal #11)

**Option B — Local model (Ollama)**
- See `docker/optional-ollama-tailscale/` for two variants:
  local-only, or Tailscale sidecar if it's on separate hardware
- If using a local reasoning model (Qwen3, etc.), pass `"think": false` in
  the request body or you'll get empty responses (Journal #10)

Either way, the prompt shape is the same:
```
Classify this stock command into JSON only, no other text:
{"action": "check|list|add|remove", "ticker": "SYMBOL or null"}.
Message: <the user's message>
```

---

## 9. Build the stock agent

See `docs/MILESTONES.md` Phase 1 for the exact node sequence:
HTTP Request (LLM) → Code (parse JSON, with fallback) → Switch (route on
action) → per-branch logic (Alpha Vantage lookup / Postgres read-write) →
Telegram reply.

Alpha Vantage free API key: https://www.alphavantage.co/support/#api-key

---

## 10. Export your workflow for version control

n8n workflows live in its database by default, not as files. See
[`EXPORTING.md`](EXPORTING.md) to get them into this repo so changes are
actually tracked in git.
