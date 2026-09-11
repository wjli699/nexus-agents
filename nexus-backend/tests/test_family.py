"""Family agent — classification, event/task dispatch, date helpers."""

import asyncio
from datetime import date, timedelta

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
    today = date.today()
    fake_pool(fetch_rows=[
        {"id": 1, "title": "Anniversary", "event_date": date(today.year - 1, 12, 1),
         "start_time": None, "recurrence": "yearly"},
        {"id": 2, "title": "Dentist", "event_date": today + timedelta(days=3),
         "start_time": None, "recurrence": None},
    ])
    out = _run(family.handle("what's coming up"))
    assert out.startswith("Upcoming events:")
    # Dentist (in 3 days) before the yearly Anniversary (rolls to Dec this/next year)
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


# --- import: idempotent write for externally-sourced events (ROADMAP M3.5) -


def _item(**overrides):
    item = {
        "source": "gcal",
        "external_id": "evt-1",
        "title": "Dentist",
        "event_date": date(2026, 10, 2),
        "start_time": None,
        "end_time": None,
        "location": None,
        "notes": None,
        "recurrence": None,
    }
    item.update(overrides)
    return item


def test_import_new_event_inserts(fake_pool):
    pool = fake_pool(fetchval_queue=[True])
    out = _run(family.import_events([_item()]))
    assert out == {"inserted": 1, "updated": 0}
    assert pool.calls[0][0] == "fetchval"
    # The WHERE clause must match family_events_source_external_id's partial
    # index predicate exactly, or Postgres rejects the ON CONFLICT target.
    assert "ON CONFLICT (source, external_id) WHERE external_id IS NOT NULL" in pool.calls[0][1]


def test_import_existing_event_updates_not_duplicates(fake_pool):
    # Same (source, external_id) re-imported — the upsert takes the DO
    # UPDATE branch, so xmax != 0 and FakePool is configured to return that.
    pool = fake_pool(fetchval_queue=[False])
    out = _run(family.import_events([_item(title="Dentist (rescheduled)")]))
    assert out == {"inserted": 0, "updated": 1}
    assert pool.calls[0][2][0] == "Dentist (rescheduled)"


def test_import_mixed_batch_tallies_both(fake_pool):
    fake_pool(fetchval_queue=[True, False, True])
    out = _run(family.import_events([
        _item(external_id="evt-1"),
        _item(external_id="evt-2"),
        _item(external_id="evt-3", source="email"),
    ]))
    assert out == {"inserted": 2, "updated": 1}


# --- email import: extract + confirm loop (ROADMAP M3.5) ------------------


def test_extract_not_an_event_returns_none(monkeypatch):
    _stub_classify(monkeypatch, {"is_event": False})
    out = _run(family.extract_candidate("Weekly newsletter", "stuff", "msg-1"))
    assert out == {"candidate": None}


def test_extract_falls_back_to_stripped_html_when_body_empty(monkeypatch, fake_pool):
    seen = {}

    async def fake(prompt):
        seen["prompt"] = prompt
        return {
            "is_event": True, "title": "Fall Picnic", "date_phrase": "2026-10-03",
            "time": None, "location": None,
        }

    monkeypatch.setattr(family.llm, "complete_json", fake)
    fake_pool(fetchval_queue=[9])
    html = "<html><body><p>Join us <b>October 3, 2026</b> for the picnic!</p></body></html>"
    out = _run(family.extract_candidate("Fall Picnic", "", "msg-html", html=html))
    assert out == {"candidate": {
        "id": 9, "title": "Fall Picnic", "date": "2026-10-03",
        "time": None, "location": None,
    }}
    # The stripped text, not raw markup, went into the extraction prompt.
    assert "<p>" not in seen["prompt"]
    assert "Join us October 3, 2026 for the picnic!" in seen["prompt"]


def test_extract_unresolvable_date_returns_none(monkeypatch):
    _stub_classify(monkeypatch, {
        "is_event": True, "title": "Recital", "date_phrase": "sometime soonish",
        "time": None, "location": None,
    })
    out = _run(family.extract_candidate("Recital", "body", "msg-2"))
    assert out == {"candidate": None}


def test_extract_valid_event_queues_and_returns_candidate(monkeypatch, fake_pool):
    _stub_classify(monkeypatch, {
        "is_event": True, "title": "School play", "date_phrase": "2026-10-02",
        "time": "18:30", "location": "Gym",
    })
    pool = fake_pool(fetchval_queue=[7])
    out = _run(family.extract_candidate("School play", "body text", "msg-3"))
    assert out == {"candidate": {
        "id": 7, "title": "School play", "date": "2026-10-02",
        "time": "18:30", "location": "Gym",
    }}
    assert "pending_family_imports" in pool.calls[0][1]


def test_extract_resolves_relative_phrase_against_received_date(monkeypatch, fake_pool):
    # "this Friday" must resolve relative to when the email actually
    # arrived, not whenever we happen to process/confirm it later.
    _stub_classify(monkeypatch, {
        "is_event": True, "title": "Coffee", "date_phrase": "this Friday",
        "time": None, "location": None,
    })
    fake_pool(fetchval_queue=[8])
    out = _run(family.extract_candidate(
        "Coffee", "body", "msg-received",
        received="2026-09-01T12:00:00.000Z",  # a Tuesday
    ))
    assert out["candidate"]["date"] == "2026-09-04"  # that week's Friday


def test_extract_dedupes_already_queued_message(monkeypatch, fake_pool):
    _stub_classify(monkeypatch, {
        "is_event": True, "title": "School play", "date_phrase": "2026-10-02",
        "time": None, "location": None,
    })
    fake_pool(fetchval_queue=[None])  # ON CONFLICT DO NOTHING, no row returned
    out = _run(family.extract_candidate("School play", "body text", "msg-3"))
    assert out == {"candidate": None}


def _pending_row(**overrides):
    row = {
        "external_id": "msg-1",
        "title": "Dentist",
        "event_date": date(2026, 10, 2),
        "start_time": None,
        "end_time": None,
        "location": None,
        "notes": None,
        "recurrence": None,
    }
    row.update(overrides)
    return row


def test_confirm_pending_adds_event_and_clears_row(fake_pool):
    pool = fake_pool(fetch_rows=[_pending_row()], fetchval_queue=[True])
    out = _run(family.handle("confirm 5"))
    assert out.startswith("Added event: Dentist")
    kinds = [c[0] for c in pool.calls]
    assert kinds == ["fetch", "fetchval", "execute"]
    delete_call = pool.calls[2]
    assert "DELETE FROM pending_family_imports" in delete_call[1]
    assert delete_call[2] == (5,)


def test_skip_pending_deletes_without_adding(fake_pool):
    pool = fake_pool(fetch_rows=[_pending_row()])
    out = _run(family.handle("skip 5"))
    assert out == "Skipped."
    assert [c[0] for c in pool.calls] == ["fetch", "execute"]


def test_confirm_unknown_pending_id_is_reported(fake_pool):
    fake_pool(fetch_rows=[])
    out = _run(family.handle("confirm 99"))
    assert out == "No pending import #99."
