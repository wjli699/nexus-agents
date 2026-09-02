"""Family agent — classification, event/task dispatch, date helpers."""

import asyncio
from datetime import date

import pytest

from app.agents import family


def _run(coro):
    return asyncio.run(coro)


def _stub_classify(monkeypatch, parsed):
    async def fake(prompt):
        return parsed

    monkeypatch.setattr(family.llm, "complete_json", fake)


# --- _next_occurrence (pure) --------------------------------------------


@pytest.mark.parametrize(
    "anchor, rec, today, expected",
    [
        (date(2026, 12, 25), None, date(2026, 9, 1), date(2026, 12, 25)),  # future one-off
        (date(2026, 1, 1), None, date(2026, 9, 1), None),                  # past one-off
        (date(1980, 3, 15), "yearly", date(2026, 9, 1), date(2027, 3, 15)),  # rolled to next yr
        (date(1980, 12, 25), "yearly", date(2026, 9, 1), date(2026, 12, 25)),  # still this yr
        (date(2000, 2, 29), "yearly", date(2027, 1, 1), date(2027, 3, 1)),  # feb29 -> mar1
        (date(2026, 1, 31), "monthly", date(2026, 9, 15), date(2026, 9, 30)),  # clamp to 30
    ],
)
def test_next_occurrence(anchor, rec, today, expected):
    assert family._next_occurrence(anchor, rec, today) == expected


# --- task path ---------------------------------------------------------


def test_task_add(monkeypatch, fake_pool):
    _stub_classify(monkeypatch, {"kind": "task", "action": "add", "title": "book dentist"})
    fake_pool(fetchval=4)
    assert _run(family.handle("remind me to book dentist")) == "Added task #4: book dentist"


def test_task_add_needs_title(monkeypatch):
    _stub_classify(monkeypatch, {"kind": "task", "action": "add", "title": None})
    assert "What task" in _run(family.handle("add a task"))


def test_task_done_needs_id(monkeypatch):
    _stub_classify(monkeypatch, {"kind": "task", "action": "done", "id": None})
    assert "Which task number" in _run(family.handle("mark it done"))


def test_task_list_delegates(monkeypatch, fake_pool):
    _stub_classify(monkeypatch, {"kind": "task", "action": "list"})
    fake_pool(fetch_rows=[])
    assert _run(family.handle("my tasks")) == "No open tasks."


# --- event path ------------------------------------------------------


def test_event_add_recurring_echoes_next_occurrence(monkeypatch, fake_pool):
    _stub_classify(monkeypatch, {
        "kind": "event", "action": "add", "title": "Mom's birthday",
        "date_phrase": "1980-03-15", "recurrence": "yearly", "time": None, "id": None,
    })
    fake_pool(fetchval=2)
    out = _run(family.handle("add mom's birthday 1980-03-15 yearly"))
    assert out.startswith("Added event #2: Mom's birthday — Mar 15")
    assert "(yearly)" in out


def test_event_add_needs_title_and_date(monkeypatch):
    _stub_classify(monkeypatch, {"kind": "event", "action": "add", "title": "Dentist"})
    assert "Need a title and a date" in _run(family.handle("add dentist appointment"))


def test_unresolvable_date_phrase_is_reported(monkeypatch):
    _stub_classify(monkeypatch, {
        "kind": "task", "action": "add", "title": "do thing",
        "date_phrase": "sometime-ish whenever",
    })
    out = _run(family.handle("add task do thing sometime-ish whenever"))
    assert 'couldn\'t read the date "sometime-ish whenever"' in out


def test_event_list_sorts_by_next_occurrence(monkeypatch, fake_pool):
    _stub_classify(monkeypatch, {"kind": "event", "action": "list"})
    fake_pool(fetch_rows=[
        {"id": 1, "title": "Anniversary", "event_date": date(2020, 12, 1),
         "start_time": None, "recurrence": "yearly"},
        {"id": 2, "title": "Dentist", "event_date": date(2026, 9, 3),
         "start_time": None, "recurrence": None},
    ])
    out = _run(family.handle("what's coming up"))
    assert out.startswith("Upcoming events:")
    # Dentist (Sep 3) before Anniversary (Dec 1)
    assert out.index("Dentist") < out.index("Anniversary")


def test_event_next_empty(monkeypatch, fake_pool):
    _stub_classify(monkeypatch, {"kind": "event", "action": "next"})
    fake_pool(fetch_rows=[])
    assert _run(family.handle("what's next")) == "Nothing upcoming."


def test_event_remove_miss(monkeypatch, fake_pool):
    _stub_classify(monkeypatch, {"kind": "event", "action": "remove", "id": 99})
    fake_pool(fetchval=None)
    assert _run(family.handle("remove event 99")) == "No event #99 (or it's imported)."


def test_unrecognized_returns_usage(monkeypatch):
    _stub_classify(monkeypatch, {"kind": None, "action": None})
    assert _run(family.handle("hello")).startswith("Family —")


# --- heartbeat -------------------------------------------------------


def test_heartbeat_quiet_when_nothing(fake_pool):
    fake_pool(fetch_rows=[])  # both _upcoming and open_due see no rows
    assert _run(family.heartbeat(lookahead_days=1)) == {"alert": False}


def test_heartbeat_lists_todays_event(monkeypatch, fake_pool):
    from datetime import date as _d

    today = _d.today()
    # FakePool returns the same fetch_rows for every fetch() call; open_due
    # filters happen in SQL (stubbed away), so give it only the event rows
    # and stub tasks.open_due to empty.
    fake_pool(fetch_rows=[
        {"id": 1, "title": "Dentist", "event_date": today,
         "start_time": None, "recurrence": None},
    ])

    async def no_tasks(domain, through):
        return []

    monkeypatch.setattr(family.tasks, "open_due", no_tasks)
    out = _run(family.heartbeat(lookahead_days=0))
    assert out["alert"] is True
    assert "Today" in out["text"] and "Dentist" in out["text"]


def test_heartbeat_includes_overdue_task(monkeypatch, fake_pool):
    from datetime import date as _d, timedelta as _td

    fake_pool(fetch_rows=[])  # no events

    async def overdue(domain, through):
        return [{"id": 3, "title": "pay bill", "due_date": _d.today() - _td(days=2)}]

    monkeypatch.setattr(family.tasks, "open_due", overdue)
    out = _run(family.heartbeat(lookahead_days=1))
    assert out["alert"] is True
    assert "#3 pay bill (overdue)" in out["text"]
