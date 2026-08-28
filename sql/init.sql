-- Runs automatically on first Postgres container start
-- (mounted into /docker-entrypoint-initdb.d/ — only executes on an empty DB
-- volume; if you've already initialized, run these manually instead)

-- Stock agent: watchlist
CREATE TABLE IF NOT EXISTS watchlist (
    ticker TEXT PRIMARY KEY,
    added_at TIMESTAMP DEFAULT NOW()
);

-- Future: general task/goal tracker (Phase 3)
-- CREATE TABLE IF NOT EXISTS task_tracker (
--     id SERIAL PRIMARY KEY,
--     item TEXT NOT NULL,
--     status TEXT DEFAULT 'open',
--     last_update_date DATE,
--     next_action TEXT,
--     notes TEXT,
--     created_at TIMESTAMP DEFAULT NOW(),
--     updated_at TIMESTAMP DEFAULT NOW()
-- );

-- Future: news source scoring (Phase 4)
-- CREATE TABLE IF NOT EXISTS news_sources (
--     source TEXT PRIMARY KEY,
--     weight REAL DEFAULT 1.0,
--     last_scored_at TIMESTAMP
-- );

-- Future: home project log (Phase 5)
-- CREATE TABLE IF NOT EXISTS project_log (
--     id SERIAL PRIMARY KEY,
--     project TEXT NOT NULL,
--     week_of DATE,
--     summary TEXT,
--     created_at TIMESTAMP DEFAULT NOW()
-- );
