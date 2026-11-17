-- Nullable source metadata lives in the original snapshot payload; no inference
-- or rewriting of legacy documents. Indexes support exact facet filters.
CREATE INDEX jobs_industry ON kltn_app.job_postings ((payload->>'industry'));
CREATE INDEX jobs_experience ON kltn_app.job_postings ((payload->>'experience_level'));
CREATE INDEX jobs_salary ON kltn_app.job_postings
 ((payload->>'salary_currency'), (payload->>'salary_period'), ((payload->>'salary_min')::numeric))
 WHERE payload->>'salary_min' IS NOT NULL;
