"""Who is this code running for? A tiny per-thread note ("this request / this job belongs to account X").

accounts.py uses it to give every account its own slice of the database without touching the many places that already
call storage.get_store(): while a request or a job runs for a friend, that call quietly returns the friend's own slice.
Outside any account (start-up, background housekeeping) it returns the normal, shared store.
"""
import contextlib
import threading

_local = threading.local()


def set_uid(uid):
    _local.uid = uid


def get_uid():
    return getattr(_local, "uid", None)


def clear():
    _local.uid = None


@contextlib.contextmanager
def as_user(uid):
    previous = get_uid()
    set_uid(uid)
    try:
        yield
    finally:
        set_uid(previous)
