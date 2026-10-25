-- Additive local-demo schema. Existing schemas, tables and JSON files are untouched.
CREATE SCHEMA IF NOT EXISTS kltn_app;
CREATE SCHEMA IF NOT EXISTS kltn_checkpoints;
CREATE TABLE IF NOT EXISTS kltn_app.records (
    kind text NOT NULL,
    record_id text NOT NULL,
    payload jsonb NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (kind, record_id)
);
CREATE TABLE IF NOT EXISTS kltn_app.profile_heads (
    root_id text PRIMARY KEY,
    revision_id text NOT NULL
);
CREATE TABLE IF NOT EXISTS kltn_app.profile_revisions (
    revision_id text PRIMARY KEY,
    root_id text NOT NULL,
    parent_id text,
    session_id text,
    changed_paths jsonb NOT NULL DEFAULT '[]'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS profile_revision_root ON kltn_app.profile_revisions(root_id, created_at);
