-- Task A7: pseudonymous accounts. The server never learns who a user is.
-- `id` is HMAC-SHA256(pepper, account_key) in lowercase hex; the pepper is a key file outside
-- this database, the account key never reaches storage, and there is no user name, e-mail,
-- real name or password column anywhere. Replaces the `users(id, role, display_label,
-- pin_hash)` table of the A1 plan: Task 6 must not create `users`.
CREATE TABLE IF NOT EXISTS accounts (
    id            TEXT PRIMARY KEY NOT NULL CHECK (length(id) = 64),
    role          TEXT NOT NULL,
    display_label TEXT NOT NULL CHECK (length(display_label) BETWEEN 1 AND 32),
    created_at    TEXT NOT NULL,
    disabled      INTEGER NOT NULL DEFAULT 0 CHECK (disabled IN (0, 1))
);

-- One-time enrolment codes: only the HMAC of the code (keyed by the same pepper).
CREATE TABLE IF NOT EXISTS enrolment_codes (
    id              TEXT PRIMARY KEY NOT NULL,
    code_hash       BLOB NOT NULL UNIQUE CHECK (length(code_hash) = 32),
    role            TEXT NOT NULL,
    suggested_label TEXT,
    created_at      TEXT NOT NULL,
    expires_at      TEXT NOT NULL,
    used_at         TEXT
);
