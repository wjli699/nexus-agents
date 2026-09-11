# External Import (Family, M3.5)

Two ways events get into `family_events` without you typing them into
Telegram: a read-only Google Calendar sync, and a Gmail confirm loop. Both
funnel through the same backend endpoint — see `api-spec-v0.1.md` section
4 — so n8n's job on either path is just "get normalized events, POST
them."

## Google Cloud Console setup (once, covers both workflows)

This repo has no prior Google OAuth credential — do this once, before
either workflow's n8n-specific setup below. Covers Google's "Google Auth
Platform" flow (APIs & Services → OAuth consent screen), current as of
late 2026 — scopes and test users are configured in separate tabs *after*
the initial wizard, not as part of it.

1. Create/select a project, then **APIs & Services → Library** → enable
   the **Google Calendar API** and **Gmail API**.
2. **APIs & Services → OAuth consent screen** → **Get started**:
   - **App information** — app name (e.g. "nexus-agents"), your support
     email.
   - **Audience** — **External**.
   - **Contact information** — your email.
   - **Finish** — agree to the Google API Services User Data Policy →
     **Create**.
3. **Data Access** tab → **Add or Remove Scopes** → add:
   - `.../auth/calendar.readonly`
   - `.../auth/gmail.readonly`
   → **Update** → **Save**. (Read-only only — this project never writes
   to Calendar or sends/modifies mail.)
4. **Audience** tab → **Test users** → **Add users** → add your own
   Gmail address (an app in "Testing" status only works for listed
   test users).
5. **Clients** tab → **Create OAuth client** → type **Web application**.
   You'll need the redirect URI n8n shows you when you create the
   credential in the next section — either open n8n first to grab it, or
   come back and add it here once you have it.

## Google Calendar import

### Shape

```
Cron trigger  →  Google Calendar (getAll)  →  Code (normalize)  →  HTTP Request
 (n8n, 06:00)     singleEvents: true             →  ImportItem[]     POST .../import
```

- **Read-only.** The workflow only ever calls GCal's `getAll` — nothing in
  this repo writes back to Google Calendar. GCal stays the source of
  truth; this is a one-way mirror (locked decision, `ROADMAP.md`).
- **Recurring events are pre-expanded.** `singleEvents: true` makes GCal
  return each occurrence of a recurring event as its own instance, so the
  Code node never has to replicate `family_events`' yearly/monthly/weekly
  recurrence math — every imported row is a plain one-off.
- **Idempotent by construction.** Re-running this daily just re-upserts
  the same `(source='gcal', external_id=<GCal event id>)` rows via
  `/agents/family/import` — no dedupe logic needed in the workflow itself.
- Runs at 06:00, an hour before the family heartbeat (07:00), so a
  newly-synced event is already in `family_events` by the time the
  morning digest runs.

### Setup (mini PC)

Do the [Google Cloud Console setup](#google-cloud-console-setup-once-covers-both-workflows)
above first if you haven't.

1. n8n → **Credentials** → new **Google Calendar OAuth2 API** credential
   → paste the Client ID/Secret from the **Clients** tab, copy n8n's
   redirect URI into that client if you haven't yet → **Connect my
   account**.
2. n8n → **Import from File** → `workflows/family-calendar-import.json`.
3. Open **Get upcoming events** → select the credential you just made
   (the workflow ships a `REPLACE_WITH_YOUR_CREDENTIAL_ID` placeholder,
   same idea as the Telegram chat-id placeholders elsewhere).
4. Adjust the **Schedule** node's cadence or the 30-day lookahead window
   (in **Get upcoming events** → Options → `timeMax`) if you want.
5. **Publish**.

### Verify

1. Put a test event on your primary Google Calendar a few days out.
2. **Execute workflow** manually in n8n.
3. `curl -s -X POST localhost:8000/agents/family/handle -d '{"message":"list"}' -H 'content-type: application/json'`
   (or just message the bot "list") — the test event should appear with
   `source` implicitly `gcal` (not removable from Telegram — `_event_remove`
   only touches `source='manual'` rows).
4. Run the workflow again without changing anything — `inserted` should be
   `0` and `updated` should match the event count in the HTTP Request
   node's output, confirming the upsert path, not a duplicate insert.

## Gmail import + confirm loop

Unlike GCal (already a trusted, curated source), free-text email isn't —
nothing from this path writes to `family_events` automatically. Extraction
only *queues a candidate*; you confirm or skip it from Telegram.

### Shape

```
Cron (n8n, 2h)  →  Gmail (search)  →  Gmail (get full)  →  Code (decode)  →  HTTP Request          →  IF (candidate != null)  →  Telegram prompt
                    household ids       raw MIME payload     Subject + plain    POST .../import/extract        │ true                    "confirm N" / "skip N"
                    sender allowlist                          text body                                        └ false → (nothing)               │
                                                                                                                                                     ▼
                                                                                                       existing agent-slim.json (Telegram → /handle)
                                                                                                       recognizes "confirm N"/"skip N" and resolves it
```

- **Two Gmail calls per message, deliberately.** The search step only
  needs message ids to apply the sender/date filter cheaply; Gmail's
  simplified search output truncates to a ~100-200 character snippet,
  which for a *forwarded* email is entirely eaten by the
  `----- Forwarded Message -----` header block — none of the actual event
  content survives. The second call fetches each matching message in full;
  confirmed live that with Simplify off, this n8n version's Gmail node
  already hands back parsed top-level `subject`/`text`/`html` fields, so
  the Code node just picks `text` (falling back to a stripped `html`) —
  no manual MIME/base64 decoding needed. (An earlier version of this
  workflow assumed the raw Gmail API payload shape and had to walk/decode
  MIME parts by hand — turned out unnecessary once we saw the real output.)
- **Extraction is the only new logic**, and it's the same local-Ollama
  pattern the family classifier already uses (`app/agents/family.py`'s
  `IMPORT_EXTRACT_PROMPT` via `llm.complete_json`) — no Claude API call
  needed for this.
- **The confirm/skip reply doesn't go through this workflow at all.** It's
  a plain Telegram message, so it flows through the existing
  `agent-slim.json` (Telegram Trigger → `POST /handle` → reply).
  `family.handle()` checks for `"confirm <id>"` / `"skip <id>"`
  *deterministically* (a regex, no LLM call) before its normal classifier
  ever runs, and dispatches from there.
- **Dedupe is on the Gmail message id.** `pending_family_imports.external_id`
  is unique, so re-running the search workflow (every 2h, on an overlapping
  `newer_than:1d` window) never re-prompts for the same email.

### Setup (mini PC)

Uses the same [Google Cloud Console setup](#google-cloud-console-setup-once-covers-both-workflows)
as the Calendar import — same project, `gmail.readonly` scope already
added there.

1. n8n → **Credentials** → new **Gmail OAuth2 API** credential (same
   Client ID/Secret as the Calendar one, or a separate OAuth client if
   you'd rather keep them apart) → **Connect my account**.
2. n8n → **Import from File** → `workflows/family-gmail-import.json`.
3. Open **Search household senders** → select the Gmail credential, and
   replace `REPLACE_WITH_HOUSEHOLD_SENDERS` in the search query with your
   actual allowlist, e.g. `school@example.org OR partner@example.com`.
4. Open **Get full message** too → select the same Gmail credential (both
   Gmail nodes need it bound independently).
5. Open **Send confirm prompt** → set **Chat ID** (same as the other
   workflows).
6. **Publish**.

### Verify

1. Send yourself a test email from an allowlisted sender describing an
   event ("Soccer practice moved to Saturday 10am").
2. **Execute workflow** manually — you should get a Telegram prompt within
   one run.
3. Reply `confirm <id>` — the bot should reply `Added event: ...`, and the
   event should show up in `/agents/family/handle` `"list"`.
4. Send another test email that *isn't* an event (a newsletter) and
   confirm no Telegram prompt arrives for it.
5. Reply `skip <id>` to a real candidate and confirm it does **not** show
   up in the event list, and that re-running the workflow doesn't
   re-prompt for the same email (dedupe on `message_id`).
