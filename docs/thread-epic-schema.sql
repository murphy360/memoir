-- Thread/Epic hierarchy extension for memoir timeline model.
-- Target dialect: PostgreSQL-compatible SQL.

CREATE TABLE IF NOT EXISTS life_threads (
    id BIGSERIAL PRIMARY KEY,
    title VARCHAR(160) NOT NULL UNIQUE,
    slug VARCHAR(180) UNIQUE,
    summary TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

ALTER TABLE life_periods
    ADD COLUMN IF NOT EXISTS thread_id BIGINT REFERENCES life_threads(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS ix_life_periods_thread_id ON life_periods(thread_id);

CREATE TABLE IF NOT EXISTS life_epics (
    id BIGSERIAL PRIMARY KEY,
    period_id BIGINT NOT NULL REFERENCES life_periods(id) ON DELETE CASCADE,
    title VARCHAR(180) NOT NULL,
    description TEXT,
    weight INTEGER NOT NULL DEFAULT 5 CHECK (weight >= 1 AND weight <= 10),
    start_date_text VARCHAR(100),
    end_date_text VARCHAR(100),
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_life_epics_period_id ON life_epics(period_id);
CREATE INDEX IF NOT EXISTS ix_life_epics_title ON life_epics(title);

ALTER TABLE life_events
    ADD COLUMN IF NOT EXISTS epic_id BIGINT REFERENCES life_epics(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS weight INTEGER NOT NULL DEFAULT 5;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'ck_life_events_weight_1_10'
    ) THEN
        ALTER TABLE life_events
            ADD CONSTRAINT ck_life_events_weight_1_10
            CHECK (weight >= 1 AND weight <= 10);
    END IF;
END
$$;

CREATE INDEX IF NOT EXISTS ix_life_events_epic_id ON life_events(epic_id);

-- Optional hierarchy guard when you want every event to have exactly one parent path:
-- - direct to period: period_id set and epic_id null
-- - nested via epic: epic_id set and period_id auto-filled from epic
-- ALTER TABLE life_events
--   ADD CONSTRAINT ck_life_events_parent_present
--   CHECK (period_id IS NOT NULL OR epic_id IS NOT NULL);
