CREATE TABLE kltn_app.tasks (
 task_id text PRIMARY KEY,
 kind text NOT NULL CHECK(kind IN ('cv','evaluate')),
 payload jsonb NOT NULL,
 idempotency_key text NOT NULL UNIQUE,
 status text NOT NULL DEFAULT 'queued' CHECK(status IN ('queued','running','completed','failed')),
 attempt integer NOT NULL DEFAULT 0,
 worker_token text,
 result jsonb,
 error text,
 created_at timestamptz NOT NULL DEFAULT now(),
 updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX tasks_pending ON kltn_app.tasks(created_at,task_id) WHERE status='queued';
