"""Shared task capability (app/tasks.py)."""

import asyncio
from datetime import date, timedelta

from app import tasks


def _run(coro):
    return asyncio.run(coro)


def test_add_without_due(fake_pool):
    pool = fake_pool(fetchval=7)
    out = _run(tasks.add("family", "book dentist"))
    assert out == "Added task #7: book dentist"
    method, query, args = pool.calls[0]
    assert method == "fetchval" and args == ("family", "book dentist", None, None)


def test_add_with_due(fake_pool):
    fake_pool(fetchval=8)
    out = _run(tasks.add("stock", "research NVDA", date(2026, 9, 10)))
    assert out == "Added task #8: research NVDA (due 2026-09-10)"


def test_list_open_empty(fake_pool):
    fake_pool(fetch_rows=[])
    assert _run(tasks.list_("family")) == "No open tasks."


def test_list_open_marks_overdue(fake_pool):
    yesterday = date.today() - timedelta(days=1)
    fake_pool(fetch_rows=[
        {"id": 3, "title": "call plumber", "status": "open", "due_date": None},
        {"id": 5, "title": "pay bill", "status": "open", "due_date": yesterday},
    ])
    out = _run(tasks.list_("family"))
    assert out == (
        "Open tasks:\n"
        "[ ] #3  call plumber\n"
        f"[ ] #5  pay bill  (due {yesterday.isoformat()}; overdue)"
    )


def test_list_include_done(fake_pool):
    fake_pool(fetch_rows=[
        {"id": 1, "title": "done thing", "status": "done", "due_date": None},
        {"id": 2, "title": "open thing", "status": "open", "due_date": None},
    ])
    out = _run(tasks.list_("family", include_done=True))
    assert out == "Tasks:\n[x] #1  done thing\n[ ] #2  open thing"


def test_done_hit_and_miss(fake_pool):
    fake_pool(fetchval="book dentist")
    assert _run(tasks.done("family", 3)) == "Done: book dentist"
    fake_pool(fetchval=None)
    assert _run(tasks.done("family", 99)) == "No open task #99."


def test_remove_hit_and_miss(fake_pool):
    fake_pool(fetchval="old task")
    assert _run(tasks.remove("stock", 4)) == "Removed task: old task"
    fake_pool(fetchval=None)
    assert _run(tasks.remove("stock", 99)) == "No task #99."
