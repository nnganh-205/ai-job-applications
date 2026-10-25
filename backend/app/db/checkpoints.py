"""One saver shared by the local graphs, with explicit shutdown cleanup."""

from threading import Lock

from langgraph.checkpoint.memory import MemorySaver

from backend.app.db import database

_lock = Lock()
_saver = None
_connection = None


def get_checkpointer():
    global _saver, _connection
    with _lock:
        if _saver is None:
            if database.enabled():
                from langgraph.checkpoint.postgres import PostgresSaver
                _connection = database.connect(checkpoints=True)
                _saver = PostgresSaver(_connection)
            else:
                _saver = MemorySaver()
        return _saver


def close_checkpointer():
    global _saver, _connection
    with _lock:
        if _connection is not None:
            _connection.close()
        _saver = _connection = None
