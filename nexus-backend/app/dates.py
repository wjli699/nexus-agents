"""Deterministic relative-date resolution.

The LLM extracts a date *phrase* ("by friday", "end of next week"); this
turns it into an actual date. Local models are unreliable at weekday math —
the M3 accuracy probe had "by friday" resolve to a Saturday — so date
arithmetic never touches the model.

    resolve(phrase, today) -> date | None

None means "couldn't parse it" — the caller should ask for an explicit
YYYY-MM-DD. Weekday phrases ("friday", "next friday", "this friday") all
resolve to the nearest upcoming occurrence; the caller echoes the resolved
date so the user can correct a wrong guess.
"""

from __future__ import annotations

import calendar
import re
from datetime import date, datetime, timedelta

from dateutil import parser as _dtparser
from dateutil.relativedelta import relativedelta

_WEEKDAYS = {
    "monday": 0, "mon": 0,
    "tuesday": 1, "tue": 1, "tues": 1,
    "wednesday": 2, "wed": 2,
    "thursday": 3, "thu": 3, "thur": 3, "thurs": 3,
    "friday": 4, "fri": 4,
    "saturday": 5, "sat": 5,
    "sunday": 6, "sun": 6,
}
_MONTHS = {m: i for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july", "august",
     "september", "october", "november", "december"], start=1)}
_MONTHS.update({m[:3]: i for m, i in list(_MONTHS.items())})
_MONTHS["sept"] = 9

_WD = "|".join(_WEEKDAYS)
_MO = "|".join(_MONTHS)
_SMALL = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6}


def resolve(phrase, today: date):
    if not isinstance(phrase, str):
        return None
    p = re.sub(r"\s+", " ", phrase.strip().lower()).strip(" .!")
    while True:
        stripped = re.sub(
            r"^(by|on|due|before|until|no later than|the|this coming|coming|around|sometime) ",
            "", p)
        if stripped == p:
            break
        p = stripped
    if not p:
        return None

    if m := re.search(r"\d{4}-\d{2}-\d{2}", p):
        try:
            return date.fromisoformat(m.group(0))
        except ValueError:
            pass

    if p in ("today", "tonight", "eod", "end of day"):
        return today
    if p in ("tomorrow", "tmrw", "tmr", "tomorow"):
        return today + timedelta(days=1)
    if p in ("day after tomorrow", "the day after tomorrow", "overmorrow"):
        return today + timedelta(days=2)

    if m := re.fullmatch(r"(?:in |after )?(\d+|" + "|".join(_SMALL) + r") (day|days|week|weeks)"
                         r"(?: from (?:now|today))?", p):
        n = _SMALL.get(m.group(1)) or int(m.group(1))
        return today + timedelta(days=n * (7 if m.group(2).startswith("week") else 1))

    if m := re.fullmatch(r"(?:in |after )?(\d+|" + "|".join(_SMALL) + r") months?"
                         r"(?: from (?:now|today))?", p):
        n = _SMALL.get(m.group(1)) or int(m.group(1))
        return today + relativedelta(months=n)

    if m := re.fullmatch(r"a week from (.+)", p):
        base = resolve(m.group(1), today)
        return base + timedelta(days=7) if base else None

    if p in ("weekend", "this weekend"):
        return _next_weekday(today, 5)
    if p == "next weekend":
        return _next_weekday(today, 5) + timedelta(days=7)

    if p in ("end of week", "end of the week", "eow", "this week"):
        return _next_weekday(today, 6, allow_today=True)
    if p == "end of next week":
        return _next_weekday(today, 6, allow_today=True) + timedelta(days=7)
    if p in ("next week", "beginning of next week", "start of next week", "early next week"):
        return _next_weekday(today, 0)

    if m := re.fullmatch(rf"(?:next |this )?({_WD})s?", p):
        return _next_weekday(today, _WEEKDAYS[m.group(1)])
    if m := re.fullmatch(rf"(?:every|each) ({_WD})s?", p):  # recurrence anchor
        return _next_weekday(today, _WEEKDAYS[m.group(1)], allow_today=True)

    if p in ("end of month", "end of the month", "eom"):
        return _end_of_month(today)
    if p in ("next month", "beginning of next month", "start of next month",
             "first of next month", "1st of next month"):
        return today.replace(day=1) + relativedelta(months=1)
    if p == "end of next month":
        return _end_of_month(today + relativedelta(months=1))

    if m := re.fullmatch(rf"(?:mid|middle of) ({_MO})", p):
        return _month_date(today, _MONTHS[m.group(1)], 15)
    if m := re.fullmatch(rf"({_MO})(?: (\d{{1,2}}))?(?:st|nd|rd|th)?", p):
        return _month_date(today, _MONTHS[m.group(1)], int(m.group(2) or 1))
    if m := re.fullmatch(rf"(\d{{1,2}})(?:st|nd|rd|th)? (?:of )?({_MO})", p):
        return _month_date(today, _MONTHS[m.group(2)], int(m.group(1)))

    if m := re.fullmatch(r"(\d{1,2})(?:st|nd|rd|th)", p):
        day = int(m.group(1))
        this_month = _clamp(today.year, today.month, day)
        return this_month if this_month >= today else _clamp(
            *_next_month(today.year, today.month), day)

    # numeric fallback (e.g. "9/20", "2026/09/20") — only if it looks like a date
    if re.search(r"\d[/.\-]\d", p):
        try:
            d = _dtparser.parse(
                p, default=datetime(today.year, today.month, today.day)
            ).date()
            return d
        except (ValueError, OverflowError):
            return None

    return None


def _next_weekday(today: date, target: int, *, allow_today: bool = False) -> date:
    delta = (target - today.weekday()) % 7
    if delta == 0 and not allow_today:
        delta = 7
    return today + timedelta(days=delta)


def _end_of_month(d: date) -> date:
    return d.replace(day=1) + relativedelta(months=1) - timedelta(days=1)


def _next_month(year: int, month: int) -> tuple[int, int]:
    return (year + 1, 1) if month == 12 else (year, month + 1)


def _clamp(year: int, month: int, day: int) -> date:
    return date(year, month, min(day, calendar.monthrange(year, month)[1]))


def _month_date(today: date, month: int, day: int) -> date:
    cand = _clamp(today.year, month, day)
    return cand if cand >= today else _clamp(today.year + 1, month, day)
