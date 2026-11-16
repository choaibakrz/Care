-- Step R1 (Task 6, lean): login tokens. Only the SHA-256 of the raw token is stored; the raw
-- token is given to the client once. `subject_json` is a `storage::TokenSubject`; `user_id`
-- (the account's 64 hex digits, NULL for a robot) lets a disabled account's tokens be
-- revoked at once.
CREATE TABLE IF NOT EXISTS tokens (
    hash         BLOB PRIMARY KEY NOT NULL CHECK (length(hash) = 32),
    subject_json TEXT NOT NULL,
    user_id      TEXT,
    expires_at   TEXT NOT NULL,
    revoked_at   TEXT
);

CREATE INDEX IF NOT EXISTS tokens_user ON tokens (user_id);
