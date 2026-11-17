ALTER TABLE kltn_app.tasks DROP CONSTRAINT tasks_kind_check;
ALTER TABLE kltn_app.tasks ADD CONSTRAINT tasks_kind_check CHECK(kind IN ('cv','evaluate','interview','assistant'));
