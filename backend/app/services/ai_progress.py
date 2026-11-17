"""Task-scoped progress; descriptions are code-owned, never model/private text."""
from contextlib import contextmanager
from contextvars import ContextVar

_listener=ContextVar('ai_progress_listener',default=None)

@contextmanager
def progress_listener(callback):
    token=_listener.set(callback)
    try:yield
    finally:_listener.reset(token)

def report(stage,message,completed=None,total=None):
    callback=_listener.get()
    if callback:
        callback(dict(stage=stage,message=message,completed=completed,total=total))
