# Build Journal

A running log of what actually happened setting this up — including the
detours. Written in case any of these bite you too; most of these weren't
obvious from the official docs.

---

## 1. `docker compose up -d` — "no configuration file provided"

Docker Compose requires the file to be named `docker-compose.yml` (hyphen)
or `compose.yml`. A file named `docker_compose.yml` (underscore) is silently
not recognized.

```bash
mv docker_compose.yml docker-compose.yml
```

---

## 2. n8n container stuck in `Restarting (1)` loop

Logs showed:
```
Error: EACCES: permission denied, open '/home/node/.n8n/config'
```

Cause: n8n runs as a non-root user (UID 1000) inside the container, but the
host-mounted `~/n8n-data` directory was created by Docker as `root`-owned.

Fix:
```bash
sudo chown -R 1000:1000 ~/n8n-data
```

Alternative (more robust, avoids host permission issues entirely): use a
named Docker volume instead of a host bind-mount. This is what the default
`docker-compose.yml` in this repo does.

---

## 3. Safari/Firefox: "Your n8n server is configured to use a secure cookie"

Happens when accessing n8n over plain `http://` via a non-localhost hostname
(e.g. a Tailscale hostname). The browser won't accept the session cookie
without HTTPS.

Two fixes, pick one:
- **Quick**: set `N8N_SECURE_COOKIE=false` in the environment. Fine on a
  private Tailscale network you control.
- **Better**: use `tailscale serve` (or `funnel`, see below) to get a real
  HTTPS endpoint with a valid cert, and leave secure cookies on.

---

## 4. Telegram Trigger node doesn't show up in node search

Searching "Telegram Trigger" in the n8n node panel returned nothing, despite
the node existing in the image (`find` inside the container confirmed
`TelegramTrigger.node.js` was present). This looks like a UI/search-index
rendering bug in this n8n version.

**Workaround**: search just `Telegram` (the app name, not the node name).
This surfaces an app tile with **Triggers** (grouped, e.g. "On message",
"On callback query" — 9 of them) and **Actions** (27 of them) nested inside,
bypassing whatever's broken in flat node-name search.

---

## 5. `tailscale serve` vs `tailscale funnel` — these are not the same thing

`tailscale serve` only makes a service reachable to **devices inside your own
tailnet**. It does **not** expose it to the public internet.

Telegram's webhook delivery requires reaching your server from Telegram's own
infrastructure — which is outside your tailnet. `serve` alone will always
fail here with something like:

```
Bad Request: bad webhook: Failed to resolve host: Name or service not known
```

Fix: use `tailscale funnel` instead, which does expose the service publicly
(still through Tailscale's infra, still gets a real cert):

```bash
sudo tailscale serve reset      # clear conflicting serve config on the same port first
sudo tailscale funnel --bg 5678
```

`--bg` matters — without it, funnel runs in the foreground and dies the
moment you close the terminal/SSH session.

Security note: funnel makes the endpoint reachable by anyone on the public
internet who knows the URL, not just tailnet members. Worth scoping funnel to
just the webhook path rather than the whole app once you've moved past
initial setup.

---

## 6. n8n env var changes not taking effect after `docker compose up -d`

If the container already exists, `up -d` alone doesn't always pick up new
environment variables from an edited compose file. Force recreation:

```bash
docker compose down
docker compose up -d --force-recreate
```

Verify what's actually loaded inside the running container:
```bash
docker compose exec n8n env | grep -i webhook
```

---

## 7. "Bad Request: bad webhook: Failed to resolve host" — even after Funnel is on

If you see this right after enabling Funnel, it's very likely **DNS
propagation lag**, not a config problem. Funnel's public DNS record can take
a minute or two to become live.

Verify from an *external* vantage point (not the box itself):
```bash
curl -I https://<your-hostname>.ts.net/
dig <your-hostname>.ts.net
```
Also cross-check with a third-party tool like dnschecker.org. Once these
confirm it resolves, retry.

---

## 8. "Execute workflow" registers a temporary test webhook, not a real one

Clicking **Execute workflow** in the editor only stands up a short-lived test
listener. It deregisters again once the test session ends — so checking
`getWebhookInfo` afterward will show an **empty URL**, which looks like
failure but isn't.

For a persistent webhook, you need to make the workflow live. In this n8n
version that's **Publish**, not the classic Active/Inactive toggle from
older n8n docs.

Useful debug command (needs your bot token):
```bash
curl "https://api.telegram.org/bot<TOKEN>/getWebhookInfo"
```

---

## 9. Adding a node to a published workflow doesn't take effect until you republish

If you edit a workflow that's already Published (e.g. add a reply node),
the *live* webhook keeps running the old version until you explicitly
republish. Symptom: new nodes show correctly on the canvas and even run
during **Execute workflow** tests, but never appear in real **Executions**
triggered by actual Telegram messages.

Fix: **Unpublish, then Publish again.** A simple re-Publish sometimes isn't
enough to force the refresh — unpublish/republish was what reliably worked.

---

## 10. Local reasoning models (e.g. Qwen3) put JSON in `thinking`, not `response`

When asking a local Ollama "thinking" model for JSON-only output, the actual
JSON sometimes lands in the `thinking` field with `response` left empty:

```json
{"response": "", "thinking": "{\n  \"action\": \"check\",\n  \"ticker\": \"AAPL\"\n}", ...}
```

Fix 1 (preferred): pass `"think": false` in the Ollama API request body.
This reliably put the JSON into `response` where it belongs.

Fix 2 (defensive, keep anyway): parse defensively regardless of which field
holds it, and extract JSON via regex rather than assuming clean output —
small/local models are less consistent than hosted frontier models:

```javascript
const data = $input.item.json;
const raw = data.response?.trim() ? data.response : data.thinking;
try {
  const match = raw.match(/\{[\s\S]*\}/);
  const parsed = JSON.parse(match ? match[0] : raw);
  return { json: parsed };
} catch (e) {
  return { json: { action: "unknown", ticker: null } };
}
```

---

## 11. Claude Pro/Max subscription ≠ API credits

The claude.ai subscription (Pro/Max) and the Anthropic API are billed
completely separately. There's no bundled API credit with a Pro plan — API
usage is pay-per-token regardless of any subscription held. Relevant if
you're budgeting for a project like this that calls the API programmatically.

---

## 12. `vi`/arrow keys typing "ABCD" over SSH

Classic `vi` (not `vim`) doesn't handle arrow-key escape sequences correctly
in insert mode — pressing arrows while in insert mode inserts raw escape
characters instead of moving the cursor.

Fixes, in order of convenience:
- Use `nano` instead — much more forgiving for quick edits.
- Use `vim` instead of `vi`, if installed — handles this correctly.
- Or skip interactive editing entirely for full-file rewrites:
  ```bash
  cat > docker-compose.yml << 'EOF'
  ...contents...
  EOF
  ```
