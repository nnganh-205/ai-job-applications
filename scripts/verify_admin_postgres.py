import os, json
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
from backend.app.core.config import settings
import psycopg
from psycopg import sql
original=os.environ['DATABASE_URL']; name='kltn_admin_check_'+uuid4().hex[:10]
admin_connection=psycopg.connect(original,autocommit=True)
admin_connection.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(name)))
u=urlsplit(original)
os.environ.update(DATABASE_URL=urlunsplit((u.scheme,u.netloc,'/'+name,u.query,u.fragment)),KLTN_STORAGE='postgres',KLTN_WORKER_ENABLED='0',ADMIN_EMAIL='admin@example.test',ADMIN_PASSWORD='Admin-only-fixture-123')
checks=[]
def ok(value,label):
 assert value,label
 checks.append(label)
try:
 from backend.app.db import database
 from backend.app.main import app
 from backend.app.services import tasks,administration,knowledge,auth
 from backend.app.core.workspace import workspace
 from fastapi.testclient import TestClient
 from ai.rag.labor_law import retrieve
 with TestClient(app) as a,TestClient(app) as b:
  response=a.post('/api/auth/login',json={'email':'admin@example.test','password':'Admin-only-fixture-123'})
  ok(response.status_code==200,'initial admin signs in on PostgreSQL')
  actor=response.json()['user']['user_id'];a.headers['X-KLTN-CSRF']=response.json()['csrf_token']
  response=b.post('/api/auth/register',json={'full_name':'Kiểm thử PostgreSQL','email':'member@example.test','password':'Member-fixture-123'})
  member=response.json()['user'];b.headers['X-KLTN-CSRF']=response.json()['csrf_token']
  ok(b.get('/api/admin/users').status_code==403,'member cannot access admin API')
  listing=a.get('/api/admin/knowledge').json()
  ok(len(listing)==5 and sum(d['chunk_count'] for d in listing)==977,'all existing sources/chunks imported without loss')
  original_hash=__import__('hashlib').sha256(Path('ai/rag/index.json').read_bytes()).hexdigest()
  source=a.post('/api/admin/knowledge',json={'title':'Nguồn zirconium kiểm thử','text':'Thông tin zirconium token trong tài liệu kiểm thử dành cho hệ thống. '*5,'url':'https://example.test/law','status':'draft'}).json()
  path='/api/admin/knowledge/'+source['document_id']+'/status'
  ok(not a.post('/api/admin/knowledge/search',json={'query':'zirconium token'}).json()['hits'],'draft is not retrieved')
  ok(a.patch(path,json={'status':'published','expected_version':1}).status_code==200,'source publishes transactionally')
  ok(bool(retrieve('zirconium token')),'production RAG reads published source')
  def change(state):
   try:return knowledge.change_status(actor,source['document_id'],state,2)['status']
   except administration.AdminConflict:return 'conflict'
  with ThreadPoolExecutor(max_workers=2) as pool: outcomes=list(pool.map(change,['archived','draft']))
  ok(outcomes.count('conflict')==1,'concurrent source edits reject stale version')
  ok(not retrieve('zirconium token'),'archived/draft source leaves retrieval immediately')
  ok(__import__('hashlib').sha256(Path('ai/rag/index.json').read_bytes()).hexdigest()==original_hash,'original index is unchanged')
  with workspace(member['user_id']): t=tasks.submit('evaluate',{'posting_id':'fixture'},'task-fixture')
  with database.connect() as c:c.execute("UPDATE kltn_app.tasks SET status='failed',error='Fixture failure' WHERE task_id=%s",(t['task_id'],))
  ok(a.post('/api/admin/tasks/'+t['task_id']+'/retry').status_code==200,'admin can retry a failed account task')
  ok(a.post('/api/admin/tasks/'+t['task_id']+'/retry').status_code==409,'running/queued tasks cannot be retried')
  ok(a.patch('/api/admin/users/'+member['user_id'],json={'is_active':False}).status_code==200,'admin can lock member')
  ok(b.get('/api/profile-drafts/profiles').status_code==401,'lock revokes member session')
  with database.connect() as c:ok(tasks.claim(c) is None,'worker does not claim tasks for locked users')
  a.patch('/api/admin/users/'+member['user_id'],json={'is_active':True})
  with database.connect() as c:
   claimed=tasks.claim(c);ok(claimed['task_id']==t['task_id'],'unlock makes queued task eligible')
   with patch.object(tasks,'dispatch',return_value={'fixture':True}):tasks.perform(c,claimed)
  ok(a.get('/api/admin/tasks').json()['items'][0]['status']=='completed','task monitor reflects worker result')
  ok(a.get('/api/admin/overview').json()['accounts']==2,'overview counts actual database accounts')
  logs=a.get('/api/admin/activity').json()
  ok(any(r['action']=='task.retry' for r in logs) and any(r['action']=='account.update' for r in logs),'admin changes are audited')
  ok(a.get('/api/events').status_code==404,'career event API removed')
  administration.bootstrap_admin()
  ok(len(administration.users())==2,'restart does not duplicate or reset admin')
 print(json.dumps({'passed':len(checks),'checks':checks},ensure_ascii=False,indent=2))
finally:
 from backend.app.db.checkpoints import close_checkpointer
 close_checkpointer()
 admin_connection.execute(sql.SQL('DROP DATABASE {} WITH (FORCE)').format(sql.Identifier(name)))
 admin_connection.close()
