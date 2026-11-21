ALTER TABLE kltn_app.auth_users ADD COLUMN role text NOT NULL DEFAULT 'user' CHECK(role IN ('user','admin'));
ALTER TABLE kltn_app.auth_users ADD COLUMN is_active integer NOT NULL DEFAULT 1 CHECK(is_active IN (0,1));
CREATE TABLE kltn_app.admin_documents (
 document_id text PRIMARY KEY,
 payload text NOT NULL,
 updated_at double precision NOT NULL
);
CREATE TABLE kltn_app.admin_audit (
 audit_id text PRIMARY KEY,
 actor_id text NOT NULL,
 action text NOT NULL,
 target_id text NOT NULL,
 detail text NOT NULL,
 created_at double precision NOT NULL
);
CREATE INDEX admin_audit_recent ON kltn_app.admin_audit(created_at DESC);
