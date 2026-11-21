"""Administrator provisioning, account controls and an append-only activity log."""
import json
import os
import secrets
import time
from pathlib import Path
from uuid import uuid4
from backend.app.core.config import PROJECT_ROOT
from backend.app.db import auth_repository as accounts, database
from backend.app.services import auth


class AdminConflict(ValueError):
    pass


def audit(store, actor, action, target, detail=''):
    store.execute('INSERT INTO admin_audit(audit_id,actor_id,action,target_id,detail,created_at) VALUES (?,?,?,?,?,?)',
                  ('audit_' + uuid4().hex, actor, action, target, detail, time.time()))


def bootstrap_admin():
    """Provision once. Never promote an existing public signup or reset on restart."""
    with accounts.transaction() as store:
        if store.postgres:
            store.execute("SELECT pg_advisory_xact_lock(hashtext('kltn_admin_accounts'))")
        if store.execute("SELECT user_id FROM auth_users WHERE role='admin' LIMIT 1").fetchone():
            return
        path = Path(os.getenv('ADMIN_BOOTSTRAP_PATH', str(PROJECT_ROOT/'backend/storage/admin-bootstrap.json')))
        saved = json.loads(path.read_text()) if path.is_file() else {}
        email = auth.normalize_email(os.getenv('ADMIN_EMAIL') or saved.get('email') or 'admin@career.local')
        password = os.getenv('ADMIN_PASSWORD') or saved.get('password') or secrets.token_urlsafe(18)
        if not 12 <= len(password) <= 128:
            raise ValueError('ADMIN_PASSWORD cần từ 12 đến 128 ký tự.')
        if store.execute('SELECT user_id FROM auth_users WHERE email=?', (email,)).fetchone():
            raise AdminConflict('Email quản trị đã thuộc tài khoản khác. Chọn ADMIN_EMAIL riêng để khởi tạo an toàn.')
        user_id = 'user_' + uuid4().hex
        store.execute("INSERT INTO auth_users(user_id,email,full_name,password_hash,created_at,role,is_active) VALUES (?,?,?,?,?,'admin',1)",
                      (user_id, email, 'Quản trị viên', auth.hash_password(password), time.time()))
        from backend.app.core.workspace import workspace
        from backend.app.db import profile_repository
        from backend.app.schemas.profile import MasterProfile
        with workspace(user_id):
            profile_repository.save_master_profile('account_' + user_id,
                MasterProfile(contact={'full_name': 'Quản trị viên', 'email': email}, experience=[], project=[], education=[], involvement=[], skills=[]),
                connection=store.connection if store.postgres else None)
        audit(store, user_id, 'admin.bootstrap', user_id, 'Khởi tạo tài khoản quản trị')
        # This local file is ignored by Git and never served by the web app.
        if not os.getenv('ADMIN_PASSWORD') and not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, 'w') as output:
                json.dump({'email': email, 'password': password, 'login_url': '/login?next=/admin'}, output, ensure_ascii=False, indent=2)
        if path.exists():
            os.chmod(path, 0o600)


def users():
    with accounts.transaction() as store:
        rows = store.execute('SELECT user_id,email,full_name,role,is_active,created_at FROM auth_users ORDER BY created_at DESC').fetchall()
    return [{**dict(row), 'is_active': bool(row['is_active'])} for row in rows]


def update_user(actor, target, changes):
    with accounts.transaction() as store:
        if store.postgres:
            store.execute("SELECT pg_advisory_xact_lock(hashtext('kltn_admin_accounts'))")
        row = store.execute('SELECT * FROM auth_users WHERE user_id=?', (target,)).fetchone()
        if row is None:
            raise LookupError('Không tìm thấy tài khoản.')
        role = changes.get('role', row['role'])
        active = int(changes.get('is_active', row['is_active']))
        password = changes.get('password')
        if actor == target and (role != row['role'] or active != row['is_active']):
            raise AdminConflict('Không thể tự khóa hoặc tự đổi quyền tài khoản đang dùng.')
        if row['role'] == 'admin' and row['is_active'] and (role != 'admin' or not active):
            total = store.execute("SELECT count(*) AS total FROM auth_users WHERE role='admin' AND is_active=1").fetchone()['total']
            if total <= 1:
                raise AdminConflict('Hệ thống phải còn ít nhất một quản trị viên đang hoạt động.')
        if password and not 12 <= len(password) <= 128:
            raise ValueError('Mật khẩu đặt lại cần từ 12 đến 128 ký tự.')
        store.execute('UPDATE auth_users SET role=?,is_active=?,password_hash=? WHERE user_id=?',
                      (role, active, auth.hash_password(password) if password else row['password_hash'], target))
        if password or role != row['role'] or active != row['is_active']:
            store.execute('DELETE FROM auth_sessions WHERE user_id=?', (target,))
        actions = []
        if role != row['role']: actions.append('Đổi quyền: ' + role)
        if active != row['is_active']: actions.append('Mở khóa' if active else 'Khóa tài khoản')
        if password: actions.append('Đặt lại mật khẩu')
        if actions: audit(store, actor, 'account.update', target, row['full_name'] + ' · ' + '; '.join(actions))
    return {'updated': True}


def activity():
    with accounts.transaction() as store:
        rows = store.execute('SELECT a.*,u.full_name AS actor_name FROM admin_audit a LEFT JOIN auth_users u ON u.user_id=a.actor_id ORDER BY a.created_at DESC LIMIT 100').fetchall()
    return [dict(row) for row in rows]


def task_list():
    if not database.enabled():
        return {'available': False, 'items': []}
    with database.connect() as connection:
        rows = connection.execute('''SELECT t.task_id,t.kind,t.status,t.attempt,t.error,t.created_at,t.updated_at,
            u.full_name AS owner_name,u.email AS owner_email,u.is_active AS owner_active
            FROM kltn_app.tasks t LEFT JOIN kltn_app.auth_users u ON u.user_id=t.owner_id
            ORDER BY t.created_at DESC LIMIT 100''').fetchall()
    return {'available': True, 'items': [{**dict(row), 'created_at': row['created_at'].isoformat(), 'updated_at': row['updated_at'].isoformat()} for row in rows]}


def retry_task(actor, task_id):
    from backend.app.services import tasks
    tasks.require_database()
    with database.connect() as connection, connection.transaction():
        row = connection.execute('SELECT t.owner_id,u.is_active FROM kltn_app.tasks t LEFT JOIN kltn_app.auth_users u ON u.user_id=t.owner_id WHERE task_id=%s FOR UPDATE OF t', (task_id,)).fetchone()
        if row is None: raise LookupError('Không tìm thấy tác vụ.')
        if row['is_active'] == 0: raise AdminConflict('Mở khóa tài khoản trước khi thử lại tác vụ.')
        updated = connection.execute("UPDATE kltn_app.tasks SET status='queued',result=NULL,error=NULL,progress=NULL,worker_token=NULL,updated_at=now() WHERE task_id=%s AND status='failed' RETURNING task_id", (task_id,)).fetchone()
        if not updated: raise AdminConflict('Chỉ thử lại tác vụ đã thất bại.')
        audit(accounts.Store(connection, True), actor, 'task.retry', task_id, 'Đưa tác vụ lỗi trở lại hàng chờ')
    return {'queued': True}


def overview():
    from backend.app.services import knowledge
    members = users()
    documents = knowledge.list_documents()
    now = time.time()
    days = [time.strftime('%Y-%m-%d', time.gmtime(now - n*86400)) for n in range(6, -1, -1)]
    trend = [{'date': day, 'accounts': sum(time.strftime('%Y-%m-%d', time.gmtime(u['created_at'])) == day for u in members)} for day in days]
    result = dict(accounts=len(members), active_accounts=sum(u['is_active'] for u in members),
                  admins=sum(u['role'] == 'admin' for u in members), documents=len(documents),
                  published=sum(d['status'] == 'published' for d in documents),
                  chunks=sum(d['chunk_count'] for d in documents if d['status'] == 'published'),
                  recent_accounts=members[:5], trend=trend, tasks_available=database.enabled(),
                  tasks={'queued': 0, 'running': 0, 'completed': 0, 'failed': 0}, jobs=0)
    if database.enabled():
        with database.connect() as c:
            result['tasks'].update({r['status']: r['total'] for r in c.execute('SELECT status,count(*) AS total FROM kltn_app.tasks GROUP BY status').fetchall()})
            result['jobs'] = c.execute('SELECT count(*) AS total FROM kltn_app.job_postings').fetchone()['total']
    return result
