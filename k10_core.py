"""
K-10 Network - the encrypted mailbox that lets ALPHA, B.E.T.A. and you send each other messages and files.

Used by BOTH programs (the same file goes on the laptop and on the Render server).

How it works
  * Mail is stored as small records in the Supabase table you already use for B.E.T.A.'s memory (beta_kv), under keys
    that start with "k10:msg:". Nothing else is needed: no extra server, no open ports on your laptop or phone.
  * Everything that matters (subject, text, attached file) is ENCRYPTED with AES-256-GCM before it leaves the program,
    using a secret key that only ALPHA and B.E.T.A. have (K10_KEY). Supabase only ever sees scrambled data plus who it
    is for and when it was sent. Each direction uses its own key (derived from K10_KEY) and every record is bound to
    its sender, recipient, time and id, so a record that is altered or re-addressed fails to open.
  * An AI never sends or reads mail on its own: the programs built on this file must show you the exact content and
    wait for your Accept (see K10_ALPHA_GUIDE.md).

Settings (environment variables, same on both sides):
  K10_KEY       32 random bytes as url-safe base64 - make one with:  python k10_core.py newkey
  SUPABASE_URL, SUPABASE_KEY   the same two values B.E.T.A. already uses
"""

import base64
import collections
import json
import os
import socket
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

NODES = ("alpha", "beta")
PREFIX = "k10:msg:"
MAX_SUBJECT = 150
MAX_BODY = 20_000
MAX_ATTACH = 200_000
TTL_DAYS = 14
STATES = ("new", "accepted", "rejected")


class K10Error(Exception):
    """A problem with a message that is safe to show to the user."""


class K10Unavailable(K10Error):
    """The mail line itself can't be used right now (network, Supabase, settings). Safe to show to the user.
    kind: config | key | network | timeout | auth | table | server | other.   detail: technical note for the log only."""

    def __init__(self, kind, message, detail=""):
        super().__init__(message)
        self.kind, self.detail = kind, detail


# ---------------------------------------------------------------------------
# Logging: one line per event on stdout (Render's log / ALPHA's terminal) and a small in-memory history
# that the programs can show on screen. Secrets are scrubbed before anything is written.
# ---------------------------------------------------------------------------

_LOG = collections.deque(maxlen=60)
_LOG_LOCK = threading.Lock()


def _redact(text):
    text = str(text)
    for name in ("K10_KEY", "SUPABASE_KEY"):
        secret = (os.environ.get(name) or "").strip()
        if len(secret) >= 8:
            text = text.replace(secret, "<%s hidden>" % name)
    return text


def log(message):
    line = _redact(message)
    stamp = time.strftime("%H:%M:%S")
    print("[K-10] %s" % line, flush=True)
    with _LOG_LOCK:
        _LOG.append("%s  %s" % (stamp, line))


def recent_log():
    with _LOG_LOCK:
        return list(_LOG)


def classify_error(exc):
    """Turns any low-level failure into a K10Unavailable that says what is actually wrong."""
    if isinstance(exc, K10Unavailable):
        return exc
    detail = "%s: %s" % (type(exc).__name__, str(exc)[:160])
    if isinstance(exc, urllib.error.HTTPError):
        code = exc.code
        try:
            detail += " | " + exc.read(200).decode("utf-8", "replace")
        except Exception:
            pass
        if code in (401, 403):
            return K10Unavailable("auth", "Supabase rejected SUPABASE_KEY (HTTP %d). Check that the key is current and allowed to use the beta_kv table." % code, detail)
        if code == 404:
            return K10Unavailable("table", "Supabase answered 404. Check SUPABASE_URL, and that the beta_kv table exists.", detail)
        if code == 429:
            return K10Unavailable("server", "Supabase is limiting requests right now (HTTP 429). K-10 will try again shortly.", detail)
        if code >= 500:
            return K10Unavailable("server", "Supabase has a problem on its side (HTTP %d). If your free project was paused for inactivity, restore it in the Supabase dashboard." % code, detail)
        return K10Unavailable("other", "Supabase refused the request (HTTP %d)." % code, detail)
    reason = getattr(exc, "reason", None)
    if isinstance(exc, (socket.timeout, TimeoutError)) or isinstance(reason, (socket.timeout, TimeoutError)):
        return K10Unavailable("timeout", "Supabase didn't answer in time.", detail)
    if isinstance(exc, urllib.error.URLError):
        if isinstance(reason, socket.gaierror):
            return K10Unavailable("network", "Couldn't find Supabase on the network (DNS lookup failed). Check SUPABASE_URL and the internet connection.", detail)
        return K10Unavailable("network", "Couldn't reach Supabase (%s). Check the internet connection." % type(reason).__name__, detail)
    if isinstance(exc, (json.JSONDecodeError, UnicodeDecodeError)):
        return K10Unavailable("server", "Supabase sent an answer K-10 couldn't read. Check that SUPABASE_URL points at the right project.", detail)
    return K10Unavailable("other", "K-10 couldn't reach its mailbox (%s)." % type(exc).__name__, detail)


def _b64(raw):
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _unb64(text):
    text = str(text)
    return base64.urlsafe_b64decode(text + "=" * ((4 - len(text) % 4) % 4))


def new_master_key():
    return _b64(os.urandom(32))


def _direction_key(master_b64, sender, recipient):
    try:
        master = _unb64(master_b64)
    except Exception:
        raise K10Error("K10_KEY isn't valid (make one with: python k10_core.py newkey).")
    if len(master) != 32:
        raise K10Error("K10_KEY must be 32 random bytes (make one with: python k10_core.py newkey).")
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=None,
                info=("k10|%s>%s" % (sender, recipient)).encode("utf-8")).derive(master)


# ---------------------------------------------------------------------------
# Where the records live
# ---------------------------------------------------------------------------

class MemoryBackend:
    """For tests."""

    def __init__(self):
        self.data = {}

    def put(self, key, value):
        self.data[key] = json.loads(json.dumps(value))

    def get(self, key):
        v = self.data.get(key)
        return json.loads(json.dumps(v)) if v is not None else None

    def list(self, prefix, limit=100):
        keys = sorted(k for k in self.data if k.startswith(prefix))[-limit:]
        return [(k, self.get(k)) for k in keys]

    def delete(self, key):
        self.data.pop(key, None)


class SupabaseBackend:
    """Plain HTTPS calls to Supabase's REST interface (table beta_kv: key text primary key, value jsonb)."""

    def __init__(self, url, key, table="beta_kv", timeout=8):
        self.timeout = timeout
        self.base = url.rstrip("/") + "/rest/v1/" + table
        self.headers = {"apikey": key, "Content-Type": "application/json"}
        if key.startswith("eyJ"):
            self.headers["Authorization"] = "Bearer " + key

    def _open(self, req):
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return resp.read().decode("utf-8")
        except Exception as e:
            raise classify_error(e) from e

    @staticmethod
    def _json(text):
        try:
            return json.loads(text)
        except Exception as e:
            raise classify_error(e) from e

    def put(self, key, value):
        headers = dict(self.headers, Prefer="resolution=merge-duplicates,return=minimal")
        body = json.dumps([{"key": key, "value": value}]).encode("utf-8")
        self._open(urllib.request.Request(self.base + "?on_conflict=key", data=body, headers=headers, method="POST"))

    def get(self, key):
        url = self.base + "?key=eq." + urllib.parse.quote(key, safe="") + "&select=value"
        rows = self._json(self._open(urllib.request.Request(url, headers=self.headers)))
        return rows[0]["value"] if rows else None

    def list(self, prefix, limit=100):
        url = (self.base + "?key=like." + urllib.parse.quote(prefix + "*", safe="*") +
               "&select=key,value&order=key.desc&limit=%d" % int(limit))
        rows = self._json(self._open(urllib.request.Request(url, headers=self.headers)))
        return [(r["key"], r["value"]) for r in reversed(rows)]

    def delete(self, key):
        url = self.base + "?key=eq." + urllib.parse.quote(key, safe="")
        self._open(urllib.request.Request(url, headers=self.headers, method="DELETE"))


# ---------------------------------------------------------------------------
# The mailbox
# ---------------------------------------------------------------------------

class Mailbox:
    def __init__(self, me, master_key, backend):
        if me not in NODES:
            raise K10Error("me must be one of %s" % (NODES,))
        self.me, self.master, self.backend = me, master_key, backend
        _direction_key(master_key, "alpha", "beta")          # fail early if the key is bad

    @staticmethod
    def _aad(msg_id, frm, to, ts):
        return ("%s|%s|%s|%s" % (msg_id, frm, to, ts)).encode("utf-8")

    def send(self, to, subject, body, attachment=None):
        """attachment = {"name": ..., "text": ...} (text files only) or None. Returns the message id."""
        if to not in NODES or to == self.me:
            raise K10Error("You can only send mail to %s." % " or ".join(n for n in NODES if n != self.me))
        subject, body = str(subject or "").strip()[:MAX_SUBJECT], str(body or "")
        if not subject and not body and not attachment:
            raise K10Error("The message is empty.")
        if len(body) > MAX_BODY:
            raise K10Error("The message is too long (limit %d characters)." % MAX_BODY)
        att = None
        if attachment:
            att = {"name": str(attachment.get("name") or "attachment.txt")[:80], "text": str(attachment.get("text") or "")}
            if len(att["text"].encode("utf-8")) > MAX_ATTACH:
                raise K10Error("The attached file is too big (limit %d KB)." % (MAX_ATTACH // 1000))
        msg_id, ts = uuid.uuid4().hex[:16], int(time.time() * 1000)
        payload = json.dumps({"subject": subject, "body": body, "attachment": att}).encode("utf-8")
        nonce = os.urandom(12)
        ct = AESGCM(_direction_key(self.master, self.me, to)).encrypt(nonce, payload, self._aad(msg_id, self.me, to, ts))
        record = {"v": 1, "id": msg_id, "from": self.me, "to": to, "ts": ts, "nonce": _b64(nonce), "ct": _b64(ct), "state": "new"}
        self.backend.put("%s%s:%013d-%s" % (PREFIX, to, ts, msg_id), record)
        return msg_id

    def _open_record(self, record):
        frm, to = record.get("from"), record.get("to")
        if frm not in NODES or to not in NODES or frm == to:
            raise K10Error("Unreadable message.")
        try:
            plain = AESGCM(_direction_key(self.master, frm, to)).decrypt(
                _unb64(record["nonce"]), _unb64(record["ct"]), self._aad(record["id"], frm, to, record["ts"]))
            data = json.loads(plain.decode("utf-8"))
        except K10Error:
            raise
        except Exception:
            raise K10Error("This message couldn't be opened (wrong key, or it was altered).")
        return {"id": record["id"], "from": frm, "to": to, "ts": record["ts"], "state": record.get("state", "new"),
                "subject": data.get("subject", ""), "body": data.get("body", ""), "attachment": data.get("attachment")}

    def _summary(self, full):
        att = full["attachment"]
        return {"id": full["id"], "from": full["from"], "to": full["to"], "ts": full["ts"], "state": full["state"],
                "subject": full["subject"], "preview": full["body"][:120],
                "attachment": {"name": att["name"], "size": len(att["text"].encode("utf-8"))} if att else None}

    def inbox(self, limit=50):
        out = []
        for _key, rec in reversed(self.backend.list("%s%s:" % (PREFIX, self.me), limit)):
            try:
                out.append(self._summary(self._open_record(rec)))
            except K10Error:
                out.append({"id": rec.get("id", "?"), "from": rec.get("from"), "to": self.me, "ts": rec.get("ts", 0),
                            "state": "unreadable", "subject": "(couldn't be opened)", "preview": "", "attachment": None})
        return out

    def sent(self, limit=30):
        other = [n for n in NODES if n != self.me][0]
        out = []
        for _key, rec in reversed(self.backend.list("%s%s:" % (PREFIX, other), limit * 2)):
            if rec.get("from") != self.me:
                continue
            try:
                out.append(self._summary(self._open_record(rec)))
            except K10Error:
                continue
        return out[:limit]

    def _find(self, msg_id):
        for box in NODES:
            for key, rec in self.backend.list("%s%s:" % (PREFIX, box), 200):
                if rec.get("id") == msg_id:
                    return key, rec
        raise K10Error("That message no longer exists.")

    def read(self, msg_id):
        """The full message. Only messages addressed to you, or sent by you, can be read."""
        _key, rec = self._find(msg_id)
        if self.me not in (rec.get("to"), rec.get("from")):
            raise K10Error("That message isn't yours.")
        return self._open_record(rec)

    def set_state(self, msg_id, state):
        """Only the recipient may change a message's state (accepted / rejected)."""
        if state not in STATES:
            raise K10Error("Unknown state.")
        key, rec = self._find(msg_id)
        if rec.get("to") != self.me:
            raise K10Error("Only the recipient can do that.")
        rec["state"] = state
        self.backend.put(key, rec)

    def purge_old(self):
        cutoff = int((time.time() - TTL_DAYS * 86400) * 1000)
        for box in NODES:
            for key, rec in self.backend.list("%s%s:" % (PREFIX, box), 200):
                if rec.get("ts", cutoff + 1) < cutoff:
                    try:
                        self.backend.delete(key)
                    except Exception:
                        pass


def _settings(env):
    env = env if env is not None else os.environ
    return tuple((env.get(n) or "").strip() for n in ("SUPABASE_URL", "SUPABASE_KEY", "K10_KEY"))


def from_env(me, env=None, timeout=8):
    url, key, master = _settings(env)
    missing = [n for n, v in (("SUPABASE_URL", url), ("SUPABASE_KEY", key), ("K10_KEY", master)) if not v]
    if missing:
        raise K10Unavailable("config", "K-10 isn't set up: %s %s missing." % (", ".join(missing), "is" if len(missing) == 1 else "are"))
    return Mailbox(me, master, SupabaseBackend(url, key, timeout=timeout))


def diagnose(env=None, timeout=6):
    """Checks the settings, the key and the connection, step by step, and says exactly which one is wrong.
    Never raises. Returns {"ok": bool, "kind": ..., "message": ..., "detail": ..., "step": ...}."""
    url, key, master = _settings(env)
    missing = [n for n, v in (("SUPABASE_URL", url), ("SUPABASE_KEY", key), ("K10_KEY", master)) if not v]
    if missing:
        return {"ok": False, "step": "settings", "kind": "config", "detail": "",
                "message": "K-10 isn't set up: %s %s missing." % (", ".join(missing), "is" if len(missing) == 1 else "are")}
    try:
        _direction_key(master, "alpha", "beta")
    except K10Error as e:
        return {"ok": False, "step": "key", "kind": "key", "message": str(e), "detail": ""}
    try:
        SupabaseBackend(url, key, timeout=timeout).list(PREFIX, limit=1)
    except K10Unavailable as e:
        return {"ok": False, "step": "connection", "kind": e.kind, "message": str(e), "detail": e.detail}
    except Exception as e:
        u = classify_error(e)
        return {"ok": False, "step": "connection", "kind": u.kind, "message": str(u), "detail": u.detail}
    return {"ok": True, "step": "done", "kind": None, "message": "K-10 is reachable.", "detail": ""}


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "newkey":
        print("K10_KEY=" + new_master_key())
        print("(Put this same value on BOTH sides - Render for B.E.T.A., and ALPHA's environment. Keep it secret.)")
    else:
        print(__doc__)
