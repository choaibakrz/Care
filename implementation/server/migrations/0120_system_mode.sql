-- Task A8 (fill E1): the emergency mode switch. One row (id = 1), so a restart keeps an
-- emergency on. `by_label` is the pseudonymous operator label of whoever switched it, never
-- a name. No row means "normal, never switched".
CREATE TABLE IF NOT EXISTS system_mode (
    id       INTEGER PRIMARY KEY NOT NULL CHECK (id = 1),
    mode     TEXT NOT NULL CHECK (mode IN ('normal', 'emergency')),
    since    TEXT NOT NULL,
    by_label TEXT,
    reason   TEXT CHECK (reason IS NULL OR length(reason) <= 200)
);

-- The robots the server paused when it entered emergency mode (ruling R26): only they are
-- resumed on exit, also after a restart. Emptied on exit.
CREATE TABLE IF NOT EXISTS system_mode_paused (
    robot_id TEXT PRIMARY KEY NOT NULL
);
