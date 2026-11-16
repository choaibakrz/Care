-- Task A4: stored clinic plans (invented data only). The plan is the JSON text of a
-- `locations::ClinicPlan`; `name` is copied out of it for listing.
-- No foreign key: this table can be applied before or after the base schema of Task 6.
CREATE TABLE IF NOT EXISTS clinics (
    id         TEXT PRIMARY KEY NOT NULL,
    name       TEXT NOT NULL,
    version    INTEGER NOT NULL CHECK (version >= 1),
    active     INTEGER NOT NULL DEFAULT 0 CHECK (active IN (0, 1)),
    plan_json  TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- At most one active plan.
CREATE UNIQUE INDEX IF NOT EXISTS clinics_one_active ON clinics (active) WHERE active = 1;
