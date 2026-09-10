# External Import (Family, M3.5)

Two ways events get into `family_events` without you typing them into
Telegram: a read-only Google Calendar sync, and a Gmail confirm loop. Both
funnel through the same backend endpoint — see `api-spec-v0.1.md` section
4 — so n8n's job on either path is just "get normalized events, POST
them."

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

1. In Google Cloud Console: create/select a project, enable the **Google
   Calendar API**, and create an OAuth client (Desktop or Web, per n8n's
   Google OAuth setup instructions) — this repo has no prior Google OAuth
   credential to point you at, this is the first one.
2. n8n → **Credentials** → new **Google Calendar OAuth2 API** credential,
   complete the consent flow.
3. n8n → **Import from File** → `workflows/family-calendar-import.json`.
4. Open **Get upcoming events** → select the credential you just made
   (the workflow ships a `REPLACE_WITH_YOUR_CREDENTIAL_ID` placeholder,
   same idea as the Telegram chat-id placeholders elsewhere).
5. Adjust the **Schedule** node's cadence or the 30-day lookahead window
   (in **Get upcoming events** → Options → `timeMax`) if you want.
6. **Publish**.

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
