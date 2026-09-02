-- Canonical schema for nexus-agents.
--
-- Auto-runs on FIRST Postgres container start (mounted into
-- /docker-entrypoint-initdb.d/, only on an empty data volume). Every
-- statement is idempotent (IF NOT EXISTS), so on an already-initialised DB
-- you can re-run it by hand to pick up new tables:
--
--   docker compose exec -T postgres psql -U nexus -d nexus < ../sql/init.sql

-- ---------------------------------------------------------------------------
-- Stock agent (Milestone 1)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS watchlist (
    ticker   TEXT PRIMARY KEY,
    added_at TIMESTAMP DEFAULT NOW()
);

-- ---------------------------------------------------------------------------
-- Family agent — events (Milestone 3)
-- Calendar shape. Manual entry in M3; `source`/`external_id` support
-- read-only import from Google Calendar / email in M3.5.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS family_events (
    id          SERIAL PRIMARY KEY,
    title       TEXT NOT NULL,
    event_date  DATE NOT NULL,
    start_time  TIME,                       -- NULL = all-day
    end_time    TIME,
    location    TEXT,
    notes       TEXT,
    recurrence  TEXT,                       -- NULL = one-off | 'yearly' | 'monthly' | 'weekly'
    source      TEXT NOT NULL DEFAULT 'manual',  -- 'manual' | 'gcal' | 'email'
    external_id TEXT,                        -- provider id, for dedupe on re-import
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Dedupe imported events by (source, external_id); manual rows (external_id
-- NULL) are unconstrained.
CREATE UNIQUE INDEX IF NOT EXISTS family_events_source_external_id
    ON family_events (source, external_id)
    WHERE external_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS family_events_event_date
    ON family_events (event_date);

-- ---------------------------------------------------------------------------
-- Shared task capability (Milestone 3)
-- One table, scoped by `domain`. Each agent delegates its task subcommands
-- to app/tasks.py. `project_id` links a task to a Project (Milestone 4);
-- the FK constraint is added when the projects table lands.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS tasks (
    id         SERIAL PRIMARY KEY,
    domain     TEXT NOT NULL,               -- 'family' | 'stock' | 'project' | ...
    title      TEXT NOT NULL,
    status     TEXT NOT NULL DEFAULT 'open', -- 'open' | 'done'
    due_date   DATE,
    notes      TEXT,
    project_id INTEGER,                      -- FK to projects(id) — added in M4
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    done_at    TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS tasks_domain_status
    ON tasks (domain, status);

-- ---------------------------------------------------------------------------
-- Future (not yet created):
--   projects        — Project agent (Milestone 4)
--   news_sources    — News curation agent (Milestone 5)
-- ---------------------------------------------------------------------------
