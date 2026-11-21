"""Small durable queue. One PostgreSQL session lock owns the local worker."""
import logging
import threading
from uuid import uuid4
from backend.app.db import database
from backend.app.db.profile_revision_repository import RevisionConflict
from backend.app.core.workspace import owner_id, workspace

log=logging.getLogger(__name__)


def require_database():
    if not database.enabled():raise database.DatabaseUnavailable('Tác vụ nền cần PostgreSQL. Chạy preflight và migration theo runbook.')


def public(row):
    fields=('task_id','kind','payload','status','attempt','result','error')
    return {**{key:row[key] for key in fields},'created_at':row['created_at'].isoformat(),'updated_at':row['updated_at'].isoformat(),'progress':row.get('progress')}


def submit(kind,payload,idempotency_key, *, connection=None):
    require_database()
    from psycopg.types.json import Jsonb
    if connection is None:
        with database.connect() as c,c.transaction():
            return submit(kind,payload,idempotency_key,connection=c)
    c=connection
    c.execute('INSERT INTO kltn_app.tasks(task_id,kind,payload,idempotency_key,owner_id) VALUES (%s,%s,%s,%s,%s) ON CONFLICT(owner_id,idempotency_key) DO NOTHING',('task_'+uuid4().hex,kind,Jsonb(payload),idempotency_key,owner_id()))
    row=c.execute('SELECT * FROM kltn_app.tasks WHERE idempotency_key=%s AND owner_id=%s',(idempotency_key,owner_id())).fetchone()
    if row['kind']!=kind or row['payload']!=payload:raise RevisionConflict('Mã gửi đã dùng cho dữ liệu khác. Tạo yêu cầu mới.')
    return public(row)


def read(task_id):
    require_database()
    with database.connect() as c:row=c.execute('SELECT * FROM kltn_app.tasks WHERE task_id=%s AND owner_id=%s',(task_id,owner_id())).fetchone()
    if row is None:raise LookupError('Không tìm thấy tác vụ')
    return public(row)


def retry(task_id):
    require_database()
    with database.connect() as c,c.transaction():
        row=c.execute('SELECT * FROM kltn_app.tasks WHERE task_id=%s AND owner_id=%s FOR UPDATE',(task_id,owner_id())).fetchone()
        if row is None:raise LookupError('Không tìm thấy tác vụ')
        if row['status']!='failed':raise RevisionConflict('Chỉ thử lại tác vụ đã thất bại')
        row=c.execute("UPDATE kltn_app.tasks SET status='queued',result=NULL,error=NULL,progress=NULL,worker_token=NULL,updated_at=now() WHERE task_id=%s RETURNING *",(task_id,)).fetchone()
    return public(row)


def claim(connection):
    with connection.transaction():
        row=connection.execute("SELECT t.* FROM kltn_app.tasks t WHERE status='queued' AND NOT EXISTS (SELECT 1 FROM kltn_app.auth_users u WHERE u.user_id=t.owner_id AND u.is_active=0) ORDER BY t.created_at,t.task_id FOR UPDATE OF t SKIP LOCKED LIMIT 1").fetchone()
        if row is None:return None
        return connection.execute("UPDATE kltn_app.tasks SET status='running',attempt=attempt+1,worker_token=%s,updated_at=now() WHERE task_id=%s RETURNING *",(uuid4().hex,row['task_id'])).fetchone()


def dispatch(task):
    if task['kind']=='cv':
        from ai.graph.cv_workflow import start
        from backend.app.schemas.cv import CVStart
        return start(CVStart.model_validate(task['payload']),session_id=task['task_id'].removeprefix('task_')).model_dump(mode='json')
    if task['kind']=='assistant':
        from backend.app.services.assistant import run_message
        return run_message(task['task_id'],task['payload'])
    if task['kind']=='interview':
        from backend.app.services.interviews import run_turn
        return run_turn(task['task_id'],task['payload'])
    if task['kind']!='evaluate':raise ValueError('Unknown task kind')
    from backend.app.services.dashboard_service import evaluate_job
    return evaluate_job(task['payload']['posting_id'],task['payload'].get('profile_id'),cv_id=task['payload'].get('cv_id')).model_dump(mode='json')


def perform(connection,task):
    from psycopg.types.json import Jsonb
    from backend.app.services.ai_progress import progress_listener,report
    def update_progress(value):
        connection.execute("UPDATE kltn_app.tasks SET progress=%s,updated_at=now() WHERE task_id=%s AND status='running' AND worker_token=%s",(Jsonb(value),task['task_id'],task['worker_token']))
    try:
        account = task.get('owner_id')
        with workspace(account if account and account.startswith('user_') else None), progress_listener(update_progress):
            report('prepare','Đang chuẩn bị nội dung đã chọn')
            result=dispatch(task)
            report('complete','Đã xử lý xong và lưu kết quả')
    except Exception as error:
        # ValidationError can include private inputs. Never serialize exception repr/traceback.
        from ai.llm.ollama_client import OllamaError
        message=str(error) if isinstance(error,(OllamaError,LookupError,RevisionConflict)) else 'Không hoàn tất được tác vụ. Kiểm tra dữ liệu và thử lại.'
        connection.execute("UPDATE kltn_app.tasks SET status='failed',error=%s,updated_at=now() WHERE task_id=%s AND status='running' AND worker_token=%s",(message,task['task_id'],task['worker_token']))
    else:
        connection.execute("UPDATE kltn_app.tasks SET status='completed',result=%s,error=NULL,updated_at=now() WHERE task_id=%s AND status='running' AND worker_token=%s",(Jsonb(result),task['task_id'],task['worker_token']))


class LocalWorker:
    def __init__(self):
        self.stop_event=threading.Event();self.thread=None

    def start(self):
        self.thread=threading.Thread(target=self.loop,name='kltn-local-worker',daemon=True);self.thread.start()

    def stop(self):
        self.stop_event.set()
        if self.thread:self.thread.join(timeout=2)

    def loop(self):
        while not self.stop_event.is_set():
            try:
                with database.connect() as c:
                    if not c.execute("SELECT pg_try_advisory_lock(hashtext('kltn_local_worker')) AS acquired").fetchone()['acquired']:
                        self.stop_event.wait(3);continue
                    # The previous process cannot own this lock anymore. Do not silently rerun costly work.
                    c.execute("UPDATE kltn_app.tasks SET status='failed',error='Backend đã khởi động lại khi đang xử lý. Bạn có thể thử lại.',worker_token=NULL,updated_at=now() WHERE status='running'")
                    while not self.stop_event.is_set():
                        task=claim(c)
                        if task:perform(c,task)
                        else:self.stop_event.wait(1)
            except Exception:
                log.warning('Local task worker disconnected or schema unavailable; retrying. Check migrations/database.')
                self.stop_event.wait(3)


def list_recent(kind=None,profile_id=None):
    require_database()
    with database.connect() as c:
        rows=c.execute("SELECT * FROM kltn_app.tasks WHERE owner_id=%s AND (%s::text IS NULL OR kind=%s) AND (%s::text IS NULL OR payload->>'profile_id'=%s) ORDER BY created_at DESC,task_id DESC LIMIT 30",(owner_id(),kind,kind,profile_id,profile_id)).fetchall()
    return [public(row) for row in rows]
