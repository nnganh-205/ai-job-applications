"""JSON/PostgreSQL parity for source filters; uses disposable DB and exact cleanup."""
import os
from uuid import uuid4


def main():
    url=os.getenv('KLTN_TEST_DATABASE_URL')
    if not url:raise SystemExit('Set disposable KLTN_TEST_DATABASE_URL')
    os.environ.update(KLTN_STORAGE='postgres',DATABASE_URL=url,KLTN_WORKER_ENABLED='0')
    from backend.app.db import database
    from backend.app.db.job_posting_repository import posting_id,upsert_posting,search_postings,utc_now
    from backend.app.schemas.dashboard import JobPosting
    from backend.app.services.job_filters import matches
    from backend.app.main import app
    from fastapi.testclient import TestClient
    database.migrate()
    source='filter-fixture-'+uuid4().hex
    jobs=[]
    try:
        for i,metadata in enumerate([
            dict(industry='Software',experience_level='Senior',salary_min=20_000_000,salary_max=30_000_000,salary_currency='VND',salary_period='month'),
            dict(industry='Software',experience_level='Junior',salary_min=30_000,salary_currency='USD',salary_period='year'),
            dict(salary='20–30 triệu/tháng'),
        ]):
            job=JobPosting(posting_id=posting_id(source,'',str(i)),title='C++ Backend Engineer',company=source,
                description='Python SQL 100% remote \\ path',source_name=source,external_id=str(i),imported_at=utc_now(),**metadata)
            job,_=upsert_posting(job);jobs.append(job)
        for filters in [dict(q='SQL C++'),dict(q='100%'),dict(q='_'),dict(q='\\'),dict(q="' OR true --"),dict(industry='Software',experience_level='Senior'),dict(salary_min=15_000_000),dict(salary_min=1,salary_currency='USD',salary_period='year'),dict(saved=True)]:
            expected={job.posting_id for job in jobs if matches(job,**filters)}
            actual={job.posting_id for job in search_postings(source_name=source,**filters)}
            assert actual==expected,(filters,expected,actual)
        with TestClient(app) as client:
            response=client.get('/api/dashboard',params=dict(source_name=source,salary_min=15_000_000))
            assert response.status_code==200,response.text
            assert [row['posting_id'] for row in response.json()['jobs']]==[jobs[0].posting_id]
            for value in ('-1','nan','inf'):
                assert client.get('/api/dashboard',params={'salary_min':value}).status_code==422
    finally:
        with database.connect() as connection,connection.transaction():
            for job in jobs:
                connection.execute('DELETE FROM kltn_app.job_snapshots WHERE posting_id=%s',(job.posting_id,))
                connection.execute('DELETE FROM kltn_app.job_postings WHERE posting_id=%s',(job.posting_id,))


if __name__=='__main__':main()
