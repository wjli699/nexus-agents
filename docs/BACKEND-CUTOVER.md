# Stock Agent: cutting n8n over to nexus-backend

Covers the last three Milestone 1 items: slim the n8n workflow to 3 nodes,
prove parity with the old version, then delete the old branches. Do this on
the mini PC (n8n + Docker live there).

## 0. Bring up the backend

```bash
cd docker
docker compose up -d --build nexus-backend
docker compose logs -f nexus-backend      # wait for "Uvicorn running"
curl -s localhost:8000/health             # {"status":"ok"}
```

`.env` needs `ALPHA_VANTAGE_API_KEY` and `LLM_BASE_URL` set (see
`.env.example`). The n8n container reaches the backend at
`http://nexus-backend:8000` — same compose network, no Tailscale needed.

## 1. Parity test (run BEFORE touching the live workflow)

The watchlist must start empty:

```bash
python scripts/parity_check.py --reset --url http://localhost:8000
```

11 cases: list/add/remove/dedupe/sorting are exact-match; `check` cases
match on format only (live prices move); the unknown-message case checks
the one intentional deviation from n8n (see below). All must pass.

### Known intentional deviations from the n8n-only version

| Case | n8n-only | nexus-backend |
|---|---|---|
| Unrecognised message | Switch default routed to `check`, then `null.toUpperCase()` threw → no reply | Returns usage text: `Sorry, I didn't get that. Try: check AAPL / ...` |
| `check`/`add`/`remove` with no ticker | same throw | `Which ticker? e.g. "check AAPL"` |
| SQL | `UPPER('{{ ticker }}')` string-interpolated | bound param `$1` + `.upper()` |

Everything else — exact reply strings, `ON CONFLICT DO NOTHING`,
`DELETE ... RETURNING`, empty-list text, "wasn't on your watchlist" — is a
faithful port.

## 2. Swap in the slim workflow

`workflows/stock-agent-slim.json` is `Telegram Trigger → Call backend
(HTTP Request) → Send reply`, with n8n attribution turned **off** on the
reply node.

1. n8n editor → **Import from File** → `stock-agent-slim.json`
2. Open the **Telegram Trigger** and **Send reply** nodes, re-select your
   Telegram credential if the dropdown is empty (the credential *ID* in the
   file only matches if it's the same n8n instance).
3. **Unpublish the old workflow first**, then **Publish** this one
   (JOURNAL #8/#9 — only one workflow can own the Telegram webhook, and a
   live webhook doesn't refresh without an unpublish/republish).
4. Message the bot: run the same messages from the parity script by hand
   and confirm the replies match — this time end-to-end through Telegram,
   and confirm the "sent automatically with n8n" footer is gone.

The `Call backend` node sends `{"message": <text>}` as raw JSON (not Body
Parameters — JOURNAL gotcha). If you rebuild it by hand, use
**Body Content Type: JSON** and the expression
`{{ JSON.stringify($json.message.text) }}` for the value.

## 3. Decommission the old branches

Once the slim workflow has run clean for a day:

- Delete the old workflow (or keep it Unpublished as a reference for one
  release, then delete).
- The per-branch nodes (Switch, the 3 Postgres nodes, LLM Parser, the
  Alpha Vantage node, the 4 responder nodes) all live in that old
  workflow — deleting it removes them.
- Re-export whatever's live: `docker compose exec n8n n8n export:workflow
  --all --output=/tmp/workflows` and commit the result over
  `workflows/workflows.json` (redact the Alpha Vantage key again if the old
  node is still around — see `docs/EXPORTING.md`).

## Rollback

Re-publish the old workflow (unpublish the slim one first). No data
migration is involved — both versions read/write the same `watchlist`
table.
