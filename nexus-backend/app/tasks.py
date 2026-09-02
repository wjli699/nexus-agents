"""Shared task capability (ROADMAP M3).

One `tasks` table, scoped by `domain`. Every agent delegates its task
subcommands here. The agent classifies "this is a task command" and
extracts the fields; this module owns storage + formatting only.
"""

from __future__ import annotations

from datetime import date

from . import db


async def add(
    domain: str,
    title: str,
    due_date: date | None = None,
    notes: str | None = None,
) -> str:
    task_id = await db.get_pool().fetchval(
        "INSERT INTO tasks (domain, title, due_date, notes) "
        "VALUES ($1, $2, $3, $4) RETURNING id",
        domain,
        title,
        due_date,
        notes,
    )
    suffix = f" (due {due_date.isoformat()})" if due_date else ""
    return f"Added task #{task_id}: {title}{suffix}"


async def list_(domain: str, *, include_done: bool = False) -> str:
    if include_done:
        rows = await db.get_pool().fetch(
            "SELECT id, title, status, due_date FROM tasks WHERE domain = $1 "
            "ORDER BY status, due_date NULLS LAST, id",
            domain,
        )
    else:
        rows = await db.get_pool().fetch(
            "SELECT id, title, status, due_date FROM tasks "
            "WHERE domain = $1 AND status = 'open' "
            "ORDER BY due_date NULLS LAST, id",
            domain,
        )
    if not rows:
        return "No tasks." if include_done else "No open tasks."

    today = date.today()
    lines = []
    for r in rows:
        mark = "[x]" if r["status"] == "done" else "[ ]"
        due = ""
        if r["due_date"]:
            overdue = r["status"] == "open" and r["due_date"] < today
            due = f"  (due {r['due_date'].isoformat()}{'; overdue' if overdue else ''})"
        lines.append(f"{mark} #{r['id']}  {r['title']}{due}")
    header = "Tasks:" if include_done else "Open tasks:"
    return header + "\n" + "\n".join(lines)


async def done(domain: str, task_id: int) -> str:
    title = await db.get_pool().fetchval(
        "UPDATE tasks SET status = 'done', done_at = NOW() "
        "WHERE domain = $1 AND id = $2 AND status = 'open' RETURNING title",
        domain,
        task_id,
    )
    return f"Done: {title}" if title else f"No open task #{task_id}."


async def remove(domain: str, task_id: int) -> str:
    title = await db.get_pool().fetchval(
        "DELETE FROM tasks WHERE domain = $1 AND id = $2 RETURNING title",
        domain,
        task_id,
    )
    return f"Removed task: {title}" if title else f"No task #{task_id}."


async def open_due(domain: str, through: date) -> list:
    """Open tasks in `domain` with a due date on or before `through`
    (includes overdue). For heartbeat digests."""
    return await db.get_pool().fetch(
        "SELECT id, title, due_date FROM tasks "
        "WHERE domain = $1 AND status = 'open' AND due_date IS NOT NULL "
        "AND due_date <= $2 ORDER BY due_date, id",
        domain,
        through,
    )
