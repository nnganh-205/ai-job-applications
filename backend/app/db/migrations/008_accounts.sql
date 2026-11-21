-- Existing records/checkpoints remain untouched; authenticated records use scoped kinds.
CREATE TABLE kltn_app.auth_users (
    user_id text PRIMARY KEY,
    email text NOT NULL UNIQUE,
    full_name text NOT NULL,
    password_hash text NOT NULL,
    created_at double precision NOT NULL
);
CREATE TABLE kltn_app.auth_sessions (
    token_hash text PRIMARY KEY,
    user_id text NOT NULL REFERENCES kltn_app.auth_users(user_id) ON DELETE CASCADE,
    csrf_token text NOT NULL,
    expires_at double precision NOT NULL
);
CREATE INDEX auth_sessions_expiry ON kltn_app.auth_sessions(expires_at);
ALTER TABLE kltn_app.tasks ADD COLUMN owner_id text NOT NULL DEFAULT 'local-demo';
ALTER TABLE kltn_app.tasks DROP CONSTRAINT tasks_idempotency_key_key;
ALTER TABLE kltn_app.tasks ADD CONSTRAINT tasks_owner_idempotency UNIQUE(owner_id,idempotency_key);
CREATE INDEX tasks_owner_recent ON kltn_app.tasks(owner_id,created_at DESC);
