-- Backfill once, then repositories use these tables as the only posting store.
CREATE TABLE kltn_app.job_postings (
 posting_id text PRIMARY KEY,
 source_name text NOT NULL,
 external_id text NOT NULL,
 title text NOT NULL,
 company text,
 location text,
 employment_type text,
 workplace_type text,
 saved boolean NOT NULL DEFAULT false,
 content_hash text NOT NULL,
 payload jsonb NOT NULL,
 updated_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(source_name, external_id)
);
CREATE INDEX jobs_location ON kltn_app.job_postings(location);
CREATE INDEX jobs_source ON kltn_app.job_postings(source_name);
CREATE INDEX jobs_saved ON kltn_app.job_postings(saved) WHERE saved;
CREATE INDEX jobs_search ON kltn_app.job_postings USING gin(to_tsvector('simple', title || ' ' || coalesce(company, '') || ' ' || coalesce(payload->>'description', '')));
CREATE TABLE kltn_app.job_snapshots (
 posting_id text NOT NULL REFERENCES kltn_app.job_postings(posting_id),
 content_hash text NOT NULL,
 payload jsonb NOT NULL,
 captured_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY(posting_id, content_hash)
);
INSERT INTO kltn_app.job_postings(posting_id,source_name,external_id,title,company,location,employment_type,workplace_type,saved,content_hash,payload)
 SELECT record_id,payload->>'source_name',payload->>'external_id',payload->>'title',payload->>'company',payload->>'location',payload->>'employment_type',payload->>'workplace_type',coalesce((payload->>'saved')::boolean,false),payload->>'content_hash',payload
 FROM kltn_app.records WHERE kind='postings';
INSERT INTO kltn_app.job_snapshots(posting_id,content_hash,payload)
 SELECT posting_id,content_hash,payload FROM kltn_app.job_postings;
INSERT INTO kltn_app.job_snapshots(posting_id,content_hash,payload)
 SELECT payload->>'posting_id',payload->>'content_hash',payload FROM kltn_app.records
 WHERE kind='posting_history' AND payload->>'posting_id' IN (SELECT posting_id FROM kltn_app.job_postings)
 ON CONFLICT DO NOTHING;
-- Legacy records stay intact for auditing and rollback; runtime no longer writes them.
