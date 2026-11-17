"""Queue transaction/recovery checks; isolated DB and no model calls."""
import os
from uuid import uuid4
from unittest.mock import patch


def main():
    url=os.environ.get('KLTN_TEST_DATABASE_URL')
    if not url:raise SystemExit('Set disposable KLTN_TEST_DATABASE_URL')
    os.environ.update(KLTN_STORAGE='postgres',DATABASE_URL=url,KLTN_WORKER_ENABLED='0')
    from backend.app.db import database
    from backend.app.services import tasks
    from backend.app.db.profile_revision_repository import RevisionConflict
    from fastapi.testclient import TestClient
    from backend.app.main import app
    key='queue-test-'+uuid4().hex;task=None
    try:
        task=tasks.submit('cv',{'profile_id':'fixture'},key)
        assert tasks.submit('cv',{'profile_id':'fixture'},key)['task_id']==task['task_id']
        try:tasks.submit('cv',{'profile_id':'different'},key)
        except RevisionConflict:pass
        else:raise AssertionError('Idempotency key must bind input')
        with database.connect() as c:
            claimed=tasks.claim(c);assert claimed['task_id']==task['task_id'] and claimed['status']=='running'
            with patch.object(tasks,'dispatch',return_value={'session_id':'fixture'}):tasks.perform(c,claimed)
            assert tasks.read(task['task_id'])['result']=={'session_id':'fixture'}
            assert tasks.read(task['task_id'])['progress']['stage']=='complete'
            # A stale worker cannot overwrite completed results.
            with patch.object(tasks,'dispatch',return_value={'session_id':'wrong'}):tasks.perform(c,{**claimed,'worker_token':'stale'})
            assert tasks.read(task['task_id'])['result']=={'session_id':'fixture'}
            c.execute("UPDATE kltn_app.tasks SET status='failed',error='simulated restart' WHERE task_id=%s",(task['task_id'],))
            assert tasks.retry(task['task_id'])['status']=='queued'
            claimed=tasks.claim(c)
            with patch.object(tasks,'dispatch',side_effect=ValueError('PRIVATE FIXTURE SECRET')):tasks.perform(c,claimed)
            assert 'PRIVATE' not in tasks.read(task['task_id'])['error']
        with TestClient(app) as client:
            assert client.get('/api/tasks/'+task['task_id']).status_code==200
            assert client.post('/api/tasks/'+task['task_id']+'/retry').status_code==202
    finally:
        if task:
            with database.connect() as c:c.execute('DELETE FROM kltn_app.tasks WHERE task_id=%s',(task['task_id'],))


if __name__=='__main__':main()
