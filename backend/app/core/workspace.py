"""Request-local workspace identity, also propagated explicitly to queued work."""
import os
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path

_owner = ContextVar('workspace_owner', default=None)


def owner_id():
    return _owner.get() or os.getenv('WORKSPACE_OWNER_ID', 'local-demo')


@contextmanager
def workspace(owner):
    token = _owner.set(owner)
    try:
        yield
    finally:
        _owner.reset(token)


def record_kind(kind):
    # Feed metadata belongs to the shared job catalogue. Candidate data does not.
    owner = _owner.get()
    return f'{owner}:{kind}' if owner and kind != 'feed_state' else kind


def storage_path(base):
    base = Path(base)
    owner = _owner.get()
    if not owner or base.parts[-2:] == ('users', owner):
        return base
    return base / 'users' / owner


def graph_config(thread_id):
    owner = _owner.get()
    return {'configurable': {'thread_id': f'{owner}:{thread_id}' if owner else thread_id}}
