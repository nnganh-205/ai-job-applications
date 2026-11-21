"""Small optional PostgreSQL JSONB store; credentials are never logged."""

import os
from pathlib import Path
from backend.app.core.workspace import record_kind


class DatabaseUnavailable(RuntimeError):
    pass


def enabled() -> bool:
    return os.environ.get("KLTN_STORAGE", "json") == "postgres"


def connect(*, checkpoints=False):
    try:
        import psycopg
        from psycopg.rows import dict_row
    except ImportError as error:
        raise DatabaseUnavailable("Chưa có driver PostgreSQL; cần psycopg và PostgreSQL checkpointer") from error
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise DatabaseUnavailable("Chưa cấu hình DATABASE_URL cho backend")
    try:
        return psycopg.connect(url, autocommit=True, prepare_threshold=0, row_factory=dict_row,
                              options="-c search_path=kltn_checkpoints,public" if checkpoints else "-c search_path=kltn_app,public",
                              connect_timeout=5)
    except psycopg.Error as error:
        raise DatabaseUnavailable("Không kết nối được PostgreSQL local; dữ liệu cũ được giữ nguyên") from error


def get_record(kind: str, key: str, *, connection=None, shared=False):
    if connection is None:
        with connect() as active:
            return get_record(kind, key, connection=active, shared=shared)
    row = connection.execute("SELECT payload FROM kltn_app.records WHERE kind=%s AND record_id=%s", (kind if shared else record_kind(kind), key)).fetchone()
    return row["payload"] if row else None


def list_records(kind: str, *, shared=False) -> list[dict]:
    with connect() as connection:
        rows = connection.execute("SELECT record_id, payload FROM kltn_app.records WHERE kind=%s ORDER BY updated_at DESC", (kind if shared else record_kind(kind),)).fetchall()
    return [{"id": row["record_id"], "data": row["payload"]} for row in rows]


def put_record(kind: str, key: str, data: dict, *, immutable=False, connection=None):
    from psycopg.types.json import Jsonb
    if connection is None:
        with connect() as active:
            return put_record(kind, key, data, immutable=immutable, connection=active)
    clause = "DO NOTHING" if immutable else "DO UPDATE SET payload=EXCLUDED.payload, updated_at=now()"
    connection.execute(f"INSERT INTO kltn_app.records(kind,record_id,payload) VALUES (%s,%s,%s) ON CONFLICT(kind,record_id) {clause}", (record_kind(kind), key, Jsonb(data)))
    return data


def migrate():
    with connect() as connection:
        with connection.transaction():
            connection.execute("SELECT pg_advisory_xact_lock(hashtext('kltn_migrations'))")
            connection.execute("CREATE SCHEMA IF NOT EXISTS kltn_app")
            connection.execute("CREATE TABLE IF NOT EXISTS kltn_app.schema_migrations (name text PRIMARY KEY, checksum text NOT NULL, applied_at timestamptz NOT NULL DEFAULT now())")
            import hashlib
            for path in sorted((Path(__file__).parent / "migrations").glob("[0-9]*.sql")):
                sql = path.read_text()
                checksum = hashlib.sha256(sql.encode()).hexdigest()
                previous = connection.execute("SELECT checksum FROM kltn_app.schema_migrations WHERE name=%s", (path.name,)).fetchone()
                if previous:
                    if previous["checksum"] != checksum:
                        raise ValueError(f"Migration đã áp dụng bị thay đổi: {path.name}")
                    continue
                connection.execute(sql, prepare=False)
                connection.execute("INSERT INTO kltn_app.schema_migrations(name,checksum) VALUES (%s,%s)", (path.name, checksum))
    # Saver migrations are also additive and isolated from application tables.
    from langgraph.checkpoint.postgres import PostgresSaver
    with connect(checkpoints=True) as connection:
        PostgresSaver(connection).setup()


if __name__ == "__main__":
    migrate()
