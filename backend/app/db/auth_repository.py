"""Accounts in PostgreSQL, or SQLite when running the existing JSON storage mode."""
import os
import sqlite3
from contextlib import closing, contextmanager
from pathlib import Path
from backend.app.core.config import PROJECT_ROOT
from backend.app.db import database


class Store:
    def __init__(self, connection, postgres):
        self.connection, self.postgres = connection, postgres

    def execute(self, sql, parameters=()):
        if self.postgres:
            for table in ('auth_users', 'auth_sessions', 'admin_documents', 'admin_templates', 'admin_audit'):
                sql = sql.replace(table, 'kltn_app.' + table)
            sql = sql.replace('?', '%s')
        return self.connection.execute(sql, parameters)


@contextmanager
def transaction():
    if database.enabled():
        with database.connect() as connection, connection.transaction():
            yield Store(connection, True)
        return
    path = Path(os.getenv('AUTH_SQLITE_PATH', str(PROJECT_ROOT / 'backend/storage/accounts.sqlite3')))
    path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(path, timeout=10)) as connection:
        os.chmod(path, 0o600)
        connection.row_factory = sqlite3.Row
        connection.execute('PRAGMA foreign_keys=ON')
        connection.execute('BEGIN IMMEDIATE')
        connection.execute('CREATE TABLE IF NOT EXISTS auth_users (user_id TEXT PRIMARY KEY, email TEXT NOT NULL UNIQUE, full_name TEXT NOT NULL, password_hash TEXT NOT NULL, created_at REAL NOT NULL)')
        connection.execute('CREATE TABLE IF NOT EXISTS auth_sessions (token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES auth_users(user_id) ON DELETE CASCADE, csrf_token TEXT NOT NULL, expires_at REAL NOT NULL)')
        columns = {row['name'] for row in connection.execute('PRAGMA table_info(auth_users)')}
        if 'role' not in columns:
            connection.execute("ALTER TABLE auth_users ADD COLUMN role TEXT NOT NULL DEFAULT 'user' CHECK(role IN ('user','admin'))")
        if 'is_active' not in columns:
            connection.execute('ALTER TABLE auth_users ADD COLUMN is_active INTEGER NOT NULL DEFAULT 1 CHECK(is_active IN (0,1))')
        connection.execute('CREATE TABLE IF NOT EXISTS admin_documents (document_id TEXT PRIMARY KEY,payload TEXT NOT NULL,updated_at REAL NOT NULL)')
        connection.execute('CREATE TABLE IF NOT EXISTS admin_templates (template_id TEXT PRIMARY KEY,payload TEXT NOT NULL,updated_at REAL NOT NULL)')
        connection.execute('CREATE TABLE IF NOT EXISTS admin_audit (audit_id TEXT PRIMARY KEY,actor_id TEXT NOT NULL,action TEXT NOT NULL,target_id TEXT NOT NULL,detail TEXT NOT NULL,created_at REAL NOT NULL)')
        try:
            yield Store(connection, False)
        except BaseException:
            connection.rollback()
            raise
        else:
            connection.commit()


def duplicate_email(error):
    if isinstance(error, sqlite3.IntegrityError):
        return True
    if database.enabled():
        from psycopg.errors import UniqueViolation
        return isinstance(error, UniqueViolation)
    return False
