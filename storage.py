"""
B.E.T.A. - persistent storage.

Render's free web services have an EPHEMERAL filesystem: anything written to
disk is gone after a restart or a spin-down. So conversation memory, long-term
facts and the daily request counts live in a small key/value table in Supabase
(free tier). With no Supabase credentials configured it falls back to local
JSON files in ./data - fine for trying things out on your own computer, but
it will NOT survive on Render's free plan.

Writes are batched: set() updates an in-memory copy instantly and a
background thread sends the newest value to Supabase about once a second, so
a reply is never held up waiting on a database round-trip. flush() pushes
everything immediately (called when the server shuts down).
"""

import atexit
import json
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

TABLE = "beta_kv"
MAX_PERMANENT_FAILS = 3     # a request the database rejects (4xx) will not start working by itself: give up after this many rounds


def _describe(e):
    """The error text, plus Supabase's own explanation (code / message / hint) when it sent one. The 'details' field is
    left out on purpose: it can contain the row that failed, which may hold someone's chat."""
    if isinstance(e, urllib.error.HTTPError):
        try:
            j = json.loads(e.read().decode("utf-8", "replace"))
            why = " | ".join(str(j[k]) for k in ("code", "message", "hint") if isinstance(j, dict) and j.get(k))
        except Exception:
            why = ""
        return "%s - %s" % (e, why) if why else str(e)
    return str(e)


def _is_permanent(e):
    """A 4xx answer (except 'timeout' and 'slow down') means the request itself is wrong, so retrying forever only
    fills the log. Network errors, 5xx and 429 are temporary and ARE retried."""
    return isinstance(e, urllib.error.HTTPError) and 400 <= e.code < 500 and e.code not in (408, 429)


class _BaseStore:
    def __init__(self):
        self._cache = {}
        self._dirty = set()
        self._deletes = set()           # keys to remove from the database
        self._fails = {}                # (action, key) -> how many rounds the database has refused it
        self._lock = threading.Lock()
        self._wake = threading.Event()
        self._stop = False
        self._thread = threading.Thread(target=self._writer, daemon=True)
        self._thread.start()
        atexit.register(self.flush)

    # -- subclass hooks --------------------------------------------------
    def _read(self, key):
        raise NotImplementedError

    def _write(self, key, value):
        raise NotImplementedError

    def _delete(self, key):
        raise NotImplementedError

    # -- public ----------------------------------------------------------
    def get(self, key, default=None):
        with self._lock:
            if key in self._deletes:
                return default
            if key in self._cache:
                return json.loads(json.dumps(self._cache[key]))  # copy, so callers can't mutate the cache by accident
        try:
            value = self._read(key)
        except Exception as e:
            print(f"[B.E.T.A.] storage read failed for '{key}': {e}")
            value = None
        if value is None:
            return default
        with self._lock:
            self._cache.setdefault(key, value)
            return json.loads(json.dumps(self._cache[key]))

    def set(self, key, value):
        if value is None:                # the table's value column rejects null, so "empty it" means "remove the row"
            return self.delete(key)
        with self._lock:
            self._cache[key] = json.loads(json.dumps(value))
            self._deletes.discard(key)
            self._dirty.add(key)
        self._wake.set()

    def delete(self, key):
        """Forget a key completely: out of the memory copy, out of the write queue, and out of the database."""
        with self._lock:
            self._cache.pop(key, None)
            self._dirty.discard(key)
            self._deletes.add(key)
        self._wake.set()

    def _attempt(self, what, key, fn):
        """Run one database call (two tries). True = finished or given up for good; False = try again next cycle."""
        for attempt in (1, 2):
            try:
                fn()
                self._fails.pop((what, key), None)
                return True
            except Exception as e:
                print(f"[B.E.T.A.] storage {what} failed for '{key}' (try {attempt}): {_describe(e)}")
                if _is_permanent(e):
                    n = self._fails[(what, key)] = self._fails.get((what, key), 0) + 1
                    if n >= MAX_PERMANENT_FAILS:
                        print(f"[B.E.T.A.] storage: giving up on {what} for '{key}' - the database keeps refusing it.")
                        self._fails.pop((what, key), None)
                        return True
                    return False          # no second immediate try: the same request would fail the same way
                time.sleep(0.5)
        return False

    def flush(self):
        with self._lock:
            deletes = list(self._deletes)
            keys = list(self._dirty)
            self._dirty.clear()
        for key in deletes:
            if self._attempt("delete", key, lambda k=key: self._delete(k)):
                with self._lock:
                    self._deletes.discard(key)
        for key in keys:
            with self._lock:
                if key not in self._cache:      # deleted while waiting
                    continue
                value = self._cache[key]
            if not self._attempt("write", key, lambda k=key, v=value: self._write(k, v)):
                with self._lock:
                    if key in self._cache:
                        self._dirty.add(key)   # try again on the next cycle

    def _writer(self):
        while not self._stop:
            self._wake.wait(timeout=5)
            self._wake.clear()
            time.sleep(1.0)  # let a burst of set() calls settle into one write
            self.flush()


class FileStore(_BaseStore):
    def __init__(self, directory):
        self.dir = directory
        os.makedirs(self.dir, exist_ok=True)
        super().__init__()

    def _path(self, key):
        safe = "".join(c for c in key if c.isalnum() or c in "-_")
        return os.path.join(self.dir, safe + ".json")

    def _read(self, key):
        path = self._path(key)
        if not os.path.exists(path):
            return None
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _write(self, key, value):
        path = self._path(key)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(value, f)
        os.replace(tmp, path)

    def _delete(self, key):
        try:
            os.remove(self._path(key))
        except FileNotFoundError:
            pass


class SupabaseStore(_BaseStore):
    """Talks to Supabase's REST API (PostgREST) with plain urllib - no extra
    dependency. Needs a table:  beta_kv (key text primary key, value jsonb)."""

    def __init__(self, url, key):
        self.base = url.rstrip("/") + "/rest/v1/" + TABLE
        # Supabase's newer keys (sb_secret_...) are NOT JWTs and must go in the
        # apikey header only - sending them as a Bearer token too can be rejected
        # as an "Invalid JWT". The older service_role key IS a JWT (starts "eyJ")
        # and works in both headers, so keep sending it the way it always was.
        self.headers = {"apikey": key, "Content-Type": "application/json"}
        if key.startswith("eyJ"):
            self.headers["Authorization"] = "Bearer " + key
        super().__init__()

    def _read(self, key):
        url = self.base + "?key=eq." + urllib.parse.quote(key, safe="") + "&select=value"
        req = urllib.request.Request(url, headers=self.headers)
        with urllib.request.urlopen(req, timeout=10) as resp:
            rows = json.loads(resp.read().decode("utf-8"))
        return rows[0]["value"] if rows else None

    def _write(self, key, value):
        body = json.dumps([{"key": key, "value": value}]).encode("utf-8")
        headers = dict(self.headers)
        headers["Prefer"] = "resolution=merge-duplicates,return=minimal"
        req = urllib.request.Request(self.base + "?on_conflict=key", data=body, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=10) as resp:
            resp.read()

    def _delete(self, key):
        headers = dict(self.headers)
        headers["Prefer"] = "return=minimal"
        req = urllib.request.Request(self.base + "?key=eq." + urllib.parse.quote(key, safe=""), headers=headers, method="DELETE")
        with urllib.request.urlopen(req, timeout=10) as resp:
            resp.read()


def make_store():
    url, key = os.environ.get("SUPABASE_URL", "").strip(), os.environ.get("SUPABASE_KEY", "").strip()
    if url and key:
        print("[B.E.T.A.] Storage: Supabase")
        return SupabaseStore(url, key)
    print("[B.E.T.A.] Storage: local files (./data) - NOT persistent on Render's free plan. Set SUPABASE_URL + SUPABASE_KEY.")
    return FileStore(os.path.join(os.path.dirname(os.path.abspath(__file__)), "data"))


STORE = None
_store_lock = threading.Lock()


def get_store():
    global STORE
    with _store_lock:
        if STORE is None:
            STORE = make_store()
        return STORE
