"""Family / household agent (ROADMAP M3, M3.5).

`handle()` sub-classifies the message as an **event** (calendar) or a
**task** (to-do), then dispatches. Events live in `family_events`; tasks go
through the shared `app/tasks.py` with `domain='family'`.

`_event_remove` only touches `source='manual'` rows so imported events
can't be deleted from Telegram (they'd just reappear on the next import).

M3.5 adds import: `/agents/family/import` (GCal + confirmed email events)
writes directly into `family_events`; `/agents/family/import/extract`
(Gmail) instead queues a candidate in `pending_family_imports` for a
"confirm N" / "skip N" reply, checked deterministically in `handle()`
before the LLM classifier ever runs.
"""

from __future__ import annotations

import calendar
import re
from datetime import date, time, timedelta

from .. import db, dates, llm, tasks
from ..config import get_settings

_USAGE = (
    "Family — events: add / list / remove / next.  tasks: add / list / done / remove.\n"
    'e.g. "add mom\'s birthday 1980-03-15 yearly"  ·  "add task book dentist by friday"  ·  "next"'
)

_EVENT_ACTIONS = {"add", "list", "remove", "next"}
_TASK_ACTIONS = {"add", "list", "done", "remove"}
_RECURRENCES = {"yearly", "monthly", "weekly"}

CLASSIFY_PROMPT = (
    "You manage a family calendar and to-do list.\n"
    "Classify the message as JSON only, no other text:\n"
    '{{"kind":"event|task","action":"add|list|remove|next|done",'
    '"title":str|null,"date_phrase":str|null,"time":"HH:MM"|null,'
    '"recurrence":"yearly|monthly|weekly"|null,"id":int|null}}\n'
    "- kind event = calendar items (birthday, appointment, anniversary); "
    "actions add, list, remove, next\n"
    "- kind task = to-dos / things to do; actions add, list, done, remove\n"
    '- date_phrase = the date words exactly as written ("friday", "march 15", '
    '"end of next week", "2026-10-02"). Do NOT convert to a number. null if none.\n'
    '- title = what the event/task is, with the date words removed.\n'
    '- remove and done need the item number in "id"\n'
    'Example: "add anniversary dinner october 2" -> '
    '{{"kind":"event","action":"add","title":"anniversary dinner",'
    '"date_phrase":"october 2","time":null,"recurrence":null,"id":null}}\n'
    "Message: {message}"
)


_PENDING_RE = re.compile(r"^(confirm|skip)\s+(\d+)$", re.IGNORECASE)


async def handle(message: str) -> str:
    if m := _PENDING_RE.match(message.strip()):
        return await _handle_pending(m.group(1).lower(), int(m.group(2)))
    intent = await _classify(message)
    if intent["kind"] == "task":
        return await _handle_task(intent)
    if intent["kind"] == "event":
        return await _handle_event(intent)
    return _USAGE


# --- classification -------------------------------------------------------


async def _classify(message: str) -> dict:
    parsed = await llm.complete_json(CLASSIFY_PROMPT.format(message=message)) or {}

    kind = parsed.get("kind")
    if kind not in {"event", "task"}:
        kind = None
    valid = _EVENT_ACTIONS if kind == "event" else _TASK_ACTIONS if kind == "task" else set()
    action = parsed.get("action") if parsed.get("action") in valid else None
    recurrence = parsed.get("recurrence")

    date_phrase = _clean_str(parsed.get("date_phrase"))
    return {
        "kind": kind,
        "action": action,
        "title": _clean_str(parsed.get("title")),
        "date_phrase": date_phrase,
        "date": dates.resolve(date_phrase, date.today()) if date_phrase else None,
        "time": _parse_time(parsed.get("time")),
        "recurrence": recurrence if recurrence in _RECURRENCES else None,
        "id": _parse_int(parsed.get("id")),
    }


def _clean_str(v):
    return (v.strip() or None) if isinstance(v, str) else None


def _unresolved_date(intent: dict) -> str | None:
    """The model gave a date phrase but app/dates.py couldn't resolve it."""
    if intent["date_phrase"] and intent["date"] is None:
        return (
            f'I couldn\'t read the date "{intent["date_phrase"]}". '
            "Try an explicit date like 2026-10-02."
        )
    return None


def _parse_time(v):
    if not isinstance(v, str):
        return None
    try:
        return time.fromisoformat(v.strip())
    except ValueError:
        return None


def _parse_int(v):
    if isinstance(v, bool):
        return None
    if isinstance(v, int):
        return v
    if isinstance(v, str) and v.strip().isdigit():
        return int(v.strip())
    return None


# --- tasks (delegated to the shared module) ------------------------------


async def _handle_task(intent: dict) -> str:
    action = intent["action"]
    if action is None:
        return _USAGE
    if action == "list":
        return await tasks.list_("family")
    if action == "add":
        if not intent["title"]:
            return 'What task? e.g. "add task book dentist"'
        if bad := _unresolved_date(intent):
            return bad
        return await tasks.add("family", intent["title"], due_date=intent["date"])
    if action == "done":
        if intent["id"] is None:
            return 'Which task number? "list" to see them, then "done 3".'
        return await tasks.done("family", intent["id"])
    if action == "remove":
        if intent["id"] is None:
            return 'Which task number? "list" to see them, then "remove 3".'
        return await tasks.remove("family", intent["id"])
    return _USAGE


# --- events -------------------------------------------------------------


async def _handle_event(intent: dict) -> str:
    action = intent["action"]
    if action == "add":
        return await _event_add(intent)
    if action == "list":
        return await _event_list()
    if action == "next":
        return await _event_next()
    if action == "remove":
        if intent["id"] is None:
            return 'Which event number? "list" to see them, then "remove 3".'
        return await _event_remove(intent["id"])
    return _USAGE


async def _event_add(intent: dict) -> str:
    if bad := _unresolved_date(intent):
        return bad
    if not intent["title"] or not intent["date"]:
        return 'Need a title and a date, e.g. "add dentist 2026-10-02 14:00"'
    event_id = await db.get_pool().fetchval(
        "INSERT INTO family_events (title, event_date, start_time, recurrence) "
        "VALUES ($1, $2, $3, $4) RETURNING id",
        intent["title"],
        intent["date"],
        intent["time"],
        intent["recurrence"],
    )
    rec = f" ({intent['recurrence']})" if intent["recurrence"] else ""
    tm = f" {intent['time'].strftime('%H:%M')}" if intent["time"] else ""
    # Echo the next occurrence, not the stored anchor (a 1980 birthday reads
    # oddly as a confirmation).
    shown = _next_occurrence(intent["date"], intent["recurrence"], date.today()) or intent["date"]
    return f"Added event #{event_id}: {intent['title']} — {_fmt_date(shown)}{tm}{rec}"


async def _event_list() -> str:
    items = await _upcoming()
    if not items:
        return "No upcoming events."
    today = date.today()
    lines = []
    for occ, r in items:
        rec = f" ({r['recurrence']})" if r["recurrence"] else ""
        tm = f" {r['start_time'].strftime('%H:%M')}" if r["start_time"] else ""
        lines.append(f"#{r['id']}  {_fmt_date(occ, today)}{tm}  {r['title']}{rec}")
    return "Upcoming events:\n" + "\n".join(lines)


async def _event_next() -> str:
    items = await _upcoming(limit=1)
    if not items:
        return "Nothing upcoming."
    occ, r = items[0]
    days = (occ - date.today()).days
    when = "today" if days == 0 else "tomorrow" if days == 1 else f"in {days} days"
    tm = f" at {r['start_time'].strftime('%H:%M')}" if r["start_time"] else ""
    return f"{r['title']} — {_fmt_date(occ)}{tm} ({when})"


async def _event_remove(event_id: int) -> str:
    title = await db.get_pool().fetchval(
        "DELETE FROM family_events WHERE id = $1 AND source = 'manual' RETURNING title",
        event_id,
    )
    return f"Removed event: {title}" if title else f"No event #{event_id} (or it's imported)."


async def _upcoming(limit: int = 20) -> list:
    rows = await db.get_pool().fetch(
        "SELECT id, title, event_date, start_time, recurrence FROM family_events"
    )
    today = date.today()
    out = []
    for r in rows:
        occ = _next_occurrence(r["event_date"], r["recurrence"], today)
        if occ is not None:
            out.append((occ, r))
    out.sort(key=lambda pair: pair[0])
    return out[:limit]


# --- import: idempotent write for externally-sourced events (ROADMAP M3.5) -


async def import_events(items: list[dict]) -> dict:
    """Upsert normalized events keyed on (source, external_id), so
    re-running an import (a daily GCal sync, a re-processed email) never
    duplicates a row — it just refreshes it."""
    pool = db.get_pool()
    inserted = updated = 0
    for item in items:
        was_insert = await pool.fetchval(
            "INSERT INTO family_events "
            "(title, event_date, start_time, end_time, location, notes, "
            "recurrence, source, external_id) "
            "VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9) "
            "ON CONFLICT (source, external_id) WHERE external_id IS NOT NULL "
            "DO UPDATE SET "
            "title = EXCLUDED.title, event_date = EXCLUDED.event_date, "
            "start_time = EXCLUDED.start_time, end_time = EXCLUDED.end_time, "
            "location = EXCLUDED.location, notes = EXCLUDED.notes, "
            "recurrence = EXCLUDED.recurrence "
            "RETURNING (xmax = 0)",
            item["title"],
            item["event_date"],
            item.get("start_time"),
            item.get("end_time"),
            item.get("location"),
            item.get("notes"),
            item.get("recurrence"),
            item["source"],
            item["external_id"],
        )
        if was_insert:
            inserted += 1
        else:
            updated += 1
    return {"inserted": inserted, "updated": updated}


# --- email import: extract + confirm loop (ROADMAP M3.5) ------------------

IMPORT_EXTRACT_PROMPT = (
    "You extract calendar event details from a household email, if any.\n"
    "Reply JSON only, no other text: "
    '{{"is_event":bool,"title":str|null,"date_phrase":str|null,'
    '"time":"HH:MM"|null,"location":str|null}}\n'
    "- is_event = true only if this email is about a specific dated "
    "event/appointment/activity — not a newsletter, receipt, or ad.\n"
    '- date_phrase = the date words exactly as written ("friday", '
    '"march 15", "2026-10-02"). Do NOT convert to a number. null if none.\n'
    "- Emails are often a casual, conversational reminder, not a formal "
    "announcement — still extract the event buried in the sentence.\n"
    'Example: Subject: "Reminder: Fall Picnic" Body: "Just a reminder '
    "that the Fall Picnic is happening on October 3, 2026 at 4:30 PM in "
    'the school courtyard. Hope to see you there!" -> '
    '{{"is_event":true,"title":"Fall Picnic","date_phrase":"October 3, 2026",'
    '"time":"16:30","location":"school courtyard"}}\n'
    "Subject: {subject}\n"
    "Body: {body}"
)


_HTML_TAG_RE = re.compile(r"<style[\s\S]*?</style>|<script[\s\S]*?</script>|<[^>]+>")


def _strip_html(html: str) -> str:
    return re.sub(r"\s+", " ", _HTML_TAG_RE.sub(" ", html)).strip()


async def extract_candidate(
    subject: str, body: str, message_id: str, html: str | None = None
) -> dict:
    """LLM-extract an event from an email and queue it in
    pending_family_imports for a "confirm N" / "skip N" reply. Returns
    {"candidate": None} if it's not an event, the date can't be resolved,
    or this message_id was already queued/handled by a prior run.

    `body` is the preferred plain-text content; `html` is a fallback for a
    message with no plain-text part (some Gmail clients only send HTML) —
    deciding between them is real logic, so it lives here rather than in
    the n8n workflow that calls this endpoint."""
    body = body if body and body.strip() else (_strip_html(html) if html else "")
    parsed = await llm.complete_json(
        IMPORT_EXTRACT_PROMPT.format(subject=subject, body=body)
    ) or {}
    if not parsed.get("is_event"):
        return {"candidate": None}

    title = _clean_str(parsed.get("title"))
    date_phrase = _clean_str(parsed.get("date_phrase"))
    event_date = dates.resolve(date_phrase, date.today()) if date_phrase else None
    if not title or not event_date:
        return {"candidate": None}

    event_time = _parse_time(parsed.get("time"))
    location = _clean_str(parsed.get("location"))
    snippet = f"{subject}\n{body}".strip()[:200]

    pending_id = await db.get_pool().fetchval(
        "INSERT INTO pending_family_imports "
        "(external_id, title, event_date, start_time, location, raw_snippet) "
        "VALUES ($1, $2, $3, $4, $5, $6) "
        "ON CONFLICT (external_id) DO NOTHING RETURNING id",
        message_id, title, event_date, event_time, location, snippet,
    )
    if pending_id is None:
        return {"candidate": None}
    return {
        "candidate": {
            "id": pending_id,
            "title": title,
            "date": event_date.isoformat(),
            "time": event_time.strftime("%H:%M") if event_time else None,
            "location": location,
        }
    }


async def _handle_pending(action: str, pending_id: int) -> str:
    pool = db.get_pool()
    rows = await pool.fetch(
        "SELECT external_id, title, event_date, start_time, end_time, "
        "location, notes, recurrence FROM pending_family_imports WHERE id = $1",
        pending_id,
    )
    if not rows:
        return f"No pending import #{pending_id}."
    row = rows[0]
    if action == "confirm":
        item = dict(row)
        item["source"] = "email"
        await import_events([item])
    await pool.execute("DELETE FROM pending_family_imports WHERE id = $1", pending_id)
    if action == "skip":
        return "Skipped."
    tm = f" {row['start_time'].strftime('%H:%M')}" if row["start_time"] else ""
    return f"Added event: {row['title']} — {_fmt_date(row['event_date'])}{tm}"


# --- heartbeat: morning digest (ROADMAP M3) ---------------------------


async def heartbeat(lookahead_days: int | None = None) -> dict:
    """Digest of events + tasks from today through today+lookahead (plus
    overdue tasks). {"alert": False} when there's nothing. Deterministic."""
    days = (
        lookahead_days
        if lookahead_days is not None
        else get_settings().family_digest_lookahead_days
    )
    today = date.today()
    horizon = today + timedelta(days=days)

    events = [(occ, r) for occ, r in await _upcoming(limit=100) if occ <= horizon]
    due = await tasks.open_due("family", horizon)

    if not events and not due:
        return {"alert": False}

    lines: list[str] = []
    last_day = None
    for occ, r in events:
        if occ != last_day:
            lines.append(_day_label(occ, today))
            last_day = occ
        tm = f" {r['start_time'].strftime('%H:%M')}" if r["start_time"] else ""
        lines.append(f"  {r['title']}{tm}")

    if due:
        lines.append("Tasks due:")
        for t in due:
            when = "overdue" if t["due_date"] < today else _day_label(t["due_date"], today).lower()
            lines.append(f"  #{t['id']} {t['title']} ({when})")

    return {"alert": True, "text": "\n".join(lines)}


def _day_label(d: date, today: date) -> str:
    delta = (d - today).days
    if delta == 0:
        return "Today"
    if delta == 1:
        return "Tomorrow"
    return d.strftime("%A") if delta < 7 else _fmt_date(d, today)


# --- date helpers ------------------------------------------------------


def _fmt_date(d: date, ref: date | None = None) -> str:
    ref = ref or date.today()
    s = f"{d.strftime('%b')} {d.day}"
    return s if d.year == ref.year else f"{s}, {d.year}"


def _next_occurrence(event_date: date, recurrence: str | None, today: date):
    """Next date this event happens on or after `today`, or None for a
    one-off that has already passed."""
    if not recurrence:
        return event_date if event_date >= today else None
    if recurrence == "yearly":
        for year in (today.year, today.year + 1):
            try:
                cand = event_date.replace(year=year)
            except ValueError:  # Feb 29 in a non-leap year
                cand = date(year, 3, 1)
            if cand >= today:
                return cand
        return event_date
    if recurrence == "monthly":
        y, m = today.year, today.month
        for _ in range(2):
            last = calendar.monthrange(y, m)[1]
            cand = date(y, m, min(event_date.day, last))
            if cand >= today:
                return cand
            y, m = (y + 1, 1) if m == 12 else (y, m + 1)
        return event_date
    if recurrence == "weekly":
        delta = (today - event_date).days % 7
        return today if delta == 0 else today + timedelta(days=7 - delta)
    return event_date
