"""Family / household agent (ROADMAP M3).

`handle()` sub-classifies the message as an **event** (calendar) or a
**task** (to-do), then dispatches. Events live in `family_events`; tasks go
through the shared `app/tasks.py` with `domain='family'`.

Manual entry only in M3 — calendar/email import is M3.5. `_event_remove`
only touches `source='manual'` rows so imported events can't be deleted
from Telegram (they'd just reappear on the next import).
"""

from __future__ import annotations

import calendar
from datetime import date, time, timedelta

from .. import db, llm, tasks
from ..config import get_settings

_USAGE = (
    "Family — events: add / list / remove / next.  tasks: add / list / done / remove.\n"
    'e.g. "add mom\'s birthday 1980-03-15 yearly"  ·  "add task book dentist by friday"  ·  "next"'
)

_EVENT_ACTIONS = {"add", "list", "remove", "next"}
_TASK_ACTIONS = {"add", "list", "done", "remove"}
_RECURRENCES = {"yearly", "monthly", "weekly"}

CLASSIFY_PROMPT = (
    "You manage a family calendar and to-do list. Today is {today} ({weekday}).\n"
    "Classify the message as JSON only, no other text:\n"
    '{{"kind":"event|task","action":"add|list|remove|next|done",'
    '"title":str|null,"date":"YYYY-MM-DD"|null,"time":"HH:MM"|null,'
    '"recurrence":"yearly|monthly|weekly"|null,"id":int|null}}\n'
    "- kind event = calendar items (birthday, appointment, anniversary); "
    "actions add, list, remove, next\n"
    "- kind task = to-dos / things to do; actions add, list, done, remove\n"
    "- resolve relative dates (tomorrow, next friday) to an absolute date from today\n"
    '- remove and done need the item number in "id"\n'
    "Message: {message}"
)


async def handle(message: str) -> str:
    intent = await _classify(message)
    if intent["kind"] == "task":
        return await _handle_task(intent)
    if intent["kind"] == "event":
        return await _handle_event(intent)
    return _USAGE


# --- classification -------------------------------------------------------


async def _classify(message: str) -> dict:
    today = date.today()
    parsed = await llm.complete_json(
        CLASSIFY_PROMPT.format(
            today=today.isoformat(),
            weekday=today.strftime("%A"),
            message=message,
        )
    ) or {}

    kind = parsed.get("kind")
    if kind not in {"event", "task"}:
        kind = None
    valid = _EVENT_ACTIONS if kind == "event" else _TASK_ACTIONS if kind == "task" else set()
    action = parsed.get("action") if parsed.get("action") in valid else None
    recurrence = parsed.get("recurrence")

    return {
        "kind": kind,
        "action": action,
        "title": _clean_str(parsed.get("title")),
        "date": _parse_date(parsed.get("date")),
        "time": _parse_time(parsed.get("time")),
        "recurrence": recurrence if recurrence in _RECURRENCES else None,
        "id": _parse_int(parsed.get("id")),
    }


def _clean_str(v):
    return (v.strip() or None) if isinstance(v, str) else None


def _parse_date(v):
    if not isinstance(v, str):
        return None
    try:
        return date.fromisoformat(v.strip())
    except ValueError:
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
