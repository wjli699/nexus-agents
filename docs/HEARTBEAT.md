# The Heartbeat Pattern

Borrowed from OpenClaw (the pattern, not their code): a **scheduled check
that stays silent unless something is actually notable**, instead of a
chatty periodic status message. The first use is the stock agent's daily
big-move alert (ROADMAP Milestone 2).

## Shape

```
Cron trigger  →  HTTP Request  →  IF (alert == true)  →  Telegram send
 (n8n)           POST .../heartbeat      │ true               │
                                         └ false → (nothing)
```

- **All the logic is in the backend.** `POST /agents/stock/heartbeat`
  reads the watchlist itself, checks each ticker's daily move against
  `HEARTBEAT_MOVE_THRESHOLD_PCT` (default 5%), and returns either
  `{"alert": false}` or `{"alert": true, "text": "..."}`.
- **n8n only schedules and gates.** The IF node drops `alert: false` runs
  on the floor — no message is sent. n8n never decides *what* is notable.
- **Deterministic.** No LLM anywhere in this path. A threshold comparison
  decides whether to alert; the message text is templated from the movers.
  (Explaining *why* a stock moved needs news data and belongs to the future
  news agent — out of scope here, see `docs/MILESTONES.md`.)

## Setup (mini PC)

1. Backend must be running with `ALPHA_VANTAGE_API_KEY` set (see
   `docs/BACKEND-CUTOVER.md` step 0).
2. n8n → **Import from File** → `workflows/stock-heartbeat.json`
3. Open **Send alert** →
   - re-select the Telegram credential if the dropdown is empty
   - set **Chat ID** to your own (the workflow ships a
     `REPLACE_WITH_YOUR_CHAT_ID` placeholder). Find yours: message
     `@userinfobot` on Telegram, or open any past execution of the command
     workflow and read `message.chat.id`.
4. Open the **Schedule** node to adjust cadence if you want (default:
   `30 12 * * 1-5` — 12:30 on weekdays, in `GENERIC_TIMEZONE`).
5. **Publish**.

### Alpha Vantage rate limit — pick the schedule accordingly

The free tier is **25 requests/day**. Each heartbeat run makes **one
request per watchlist ticker**. So with 8 tickers, one run/day = 8
requests; three runs/day = 24, right at the ceiling. The shipped default
is a single midday run for that reason. Only go intraday (every 30–60 min,
as the roadmap muses) if you have a premium key.

## Verify "quiet on a normal day"

The point of the pattern is no noise when nothing happens. Confirm it:

1. Trigger a run manually in n8n (**Execute workflow**) on a day with no
   big movers. The `alert == true?` IF node should send the item down the
   **false** branch and **Send alert** should not execute — check the
   Executions view shows no Telegram call.
2. Force the alert path once to prove it still fires: temporarily lower the
   threshold so something qualifies —
   ```bash
   curl -s -X POST localhost:8000/agents/stock/heartbeat \
     -H 'content-type: application/json' -d '{"threshold_pct": 0.1}'
   ```
   should come back `{"alert": true, "text": "..."}`.
3. Leave the real workflow published for a full trading day and confirm
   you only get a message on a day something actually moved ≥5%.

## Family digest (M3) — same pattern, second use

`workflows/family-heartbeat.json`: `Schedule (daily 07:00) → POST
/agents/family/heartbeat → IF alert==true → Send digest`.

`POST /agents/family/heartbeat` returns `{"alert": false}` unless there's
an event today (through `FAMILY_DIGEST_LOOKAHEAD_DAYS`, default +1 day) or
a task due/overdue, in which case `{"alert": true, "text": <digest>}`.
Optional `{"lookahead_days": N}` body override. Set the chat ID in **Send
digest** the same way as the stock one.

Verify the quiet path: on a day with nothing scheduled and no tasks due,
`curl -s -X POST localhost:8000/agents/family/heartbeat` → `{"alert":false}`.

## Reusing this for other agents

Every agent gets the same shape — only the endpoint and schedule change:

| Agent | Endpoint | Cron | Notable-when | Status |
|---|---|---|---|---|
| stock | `/agents/stock/heartbeat` | midday weekdays | ticker moved ≥5% | ✅ M2 |
| family | `/agents/family/heartbeat` | daily 07:00 | event today / task due | ✅ M3 |
| project | `/agents/project/heartbeat` | weekly | stale, or cadence hit | M4 |

Each `heartbeat` endpoint owns its own "is this worth a message?" rule and
returns the same `{alert, text}` contract, so the n8n side is copy-paste:
swap the URL, set the schedule, keep the `alert == true?` gate.
