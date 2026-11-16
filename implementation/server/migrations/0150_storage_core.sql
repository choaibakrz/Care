-- Storage build-out: the core tables of the live server (Tasks 6, 9, 12, 14, 15, 16, 17).
-- Times are RFC 3339 UTC text with microseconds and a `Z`, so text order is time order.
-- Enums are their snake_case serde names.

CREATE TABLE IF NOT EXISTS devices (
    id            TEXT PRIMARY KEY NOT NULL,
    user_id       TEXT,
    registered_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS robots (
    id        TEXT PRIMARY KEY NOT NULL,
    name      TEXT NOT NULL,
    role_card TEXT NOT NULL,
    simulated INTEGER NOT NULL DEFAULT 0 CHECK (simulated IN (0, 1)),
    key_hash  TEXT NOT NULL
);

-- Robots only: there is no tablet position table.
CREATE TABLE IF NOT EXISTS robot_last_fix (
    robot_id    TEXT PRIMARY KEY NOT NULL,
    floor       INTEGER NOT NULL,
    x           REAL NOT NULL,
    y           REAL NOT NULL,
    heading_rad REAL,
    at          TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tasks (
    id                TEXT PRIMARY KEY NOT NULL,
    kind              TEXT NOT NULL,
    item              TEXT,
    from_place        TEXT,
    to_place          TEXT NOT NULL,
    deadline          TEXT,
    state             TEXT NOT NULL,
    requested_by_json TEXT NOT NULL,
    requested_by_user TEXT,
    assigned_robot    TEXT,
    failure           TEXT,
    needs_human       TEXT,
    created_at        TEXT NOT NULL,
    updated_at        TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS tasks_created ON tasks (created_at);

CREATE TABLE IF NOT EXISTS processed_events (
    event_id TEXT PRIMARY KEY NOT NULL
);

CREATE TABLE IF NOT EXISTS inventory (
    item                TEXT PRIMARY KEY NOT NULL,
    label               TEXT NOT NULL,
    place               TEXT NOT NULL,
    count               INTEGER NOT NULL CHECK (count >= 0),
    low_threshold       INTEGER NOT NULL CHECK (low_threshold >= 0),
    last_robot_count    INTEGER,
    last_robot_count_at TEXT,
    updated_at          TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS reservations (
    id         TEXT PRIMARY KEY NOT NULL,
    task       TEXT NOT NULL,
    item       TEXT NOT NULL,
    qty        INTEGER NOT NULL CHECK (qty >= 0),
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS zones (
    id           TEXT PRIMARY KEY NOT NULL,
    name         TEXT NOT NULL,
    kind         TEXT NOT NULL,
    floor        INTEGER NOT NULL,
    polygon_json TEXT NOT NULL,
    version      INTEGER NOT NULL
);

-- The global zone-set version (one row).
CREATE TABLE IF NOT EXISTS zone_set (
    id      INTEGER PRIMARY KEY NOT NULL CHECK (id = 1),
    version INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS schedules (
    id               TEXT PRIMARY KEY NOT NULL,
    name             TEXT NOT NULL,
    cron             TEXT NOT NULL,
    timezone         TEXT NOT NULL,
    places_json      TEXT NOT NULL,
    enabled          INTEGER NOT NULL CHECK (enabled IN (0, 1)),
    last_run         TEXT,
    grace_s          INTEGER NOT NULL,
    robot            TEXT,
    last_result      TEXT NOT NULL,
    last_counts_json TEXT NOT NULL
);

-- The database copy of the journal (`GET /audit`); the files remain the authority.
CREATE TABLE IF NOT EXISTS audit_index (
    seq         INTEGER PRIMARY KEY NOT NULL,
    ingested_at TEXT NOT NULL,
    severity    TEXT NOT NULL,
    category    TEXT NOT NULL,
    actor       TEXT NOT NULL,
    record_json TEXT NOT NULL
);
