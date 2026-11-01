"""
B.E.T.A. accounts: who is logging in, and which part of the data they get.

  * One database for everyone. Every account's data lives under its own prefix ("u:<id>:memory" ...), so one person never
    sees another's. The OWNER (you) has no prefix at all: your existing data stays exactly where it is.
  * The password you type decides who you are. Your own password is still BETA_PASSWORD; friends choose theirs when they
    join with an invite code (stored only as a salted PBKDF2 hash). Two accounts can never share a password.
  * Friends get a daily allowance of messages. If they paste their own free Gemini key it is stored encrypted and the
    allowance no longer applies. Termux and K-10 mail are tied to your phone and your desktop, so they are owner-only.
Everything here is plain Python on top of the store's get(key, default) / set(key, value) - nothing else is assumed.
"""
import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import threading
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timedelta, timezone

import storage
import userctx

OWNER_ID = "owner"
OWNER_NAME = (os.environ.get("BETA_OWNER_NAME") or "Karachi").strip() or "Karachi"
USERS_KEY, INVITES_KEY, OWNER_KEY = "acct:users", "acct:invites", "acct:owner"
DEFAULT_THEME = "icon-dark"                      # the logo colours: every new account starts here
INVITE_DAYS = 14
PBKDF_ROUNDS = 150_000
PER_ACCOUNT_KEYS = ("memory", "model_pref", "usage", "push_subs", "notify_prefs", "brain")
LIKES = ["Football", "Music", "Coding", "Gaming", "School", "Business", "Movies", "Anime", "Faith"]
CODE_ALPHABET = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"
GEMINI_KEY_RE = re.compile(r"^AIza[0-9A-Za-z_\-]{35}$")


class AccountError(Exception):
    """Safe to show to the user."""


_lock = threading.RLock()
_raw_get_store = None
_cache = {"users": None, "invites": None}


def default_limit():
    try:
        return max(5, int(os.environ.get("BETA_FRIEND_DAILY_LIMIT", "50")))
    except ValueError:
        return 50


# --------------------------------------------------------------------------- the per-account slice of the database
class UserStore:
    """Same get/set as the normal store, but every key is stored under this account's prefix."""

    def __init__(self, base, prefix):
        self._base, self._prefix = base, prefix

    def get(self, key, default=None):
        return self._base.get(self._prefix + key, default)

    def set(self, key, value):
        return self._base.set(self._prefix + key, value)

    def delete(self, key):
        if hasattr(self._base, "delete"):
            return self._base.delete(self._prefix + key)
        return self._base.set(self._prefix + key, None)

    def __getattr__(self, name):                    # anything else the store offers passes straight through
        return getattr(self._base, name)


def prefix_of(uid):
    return "" if uid in (None, OWNER_ID) else "u:%s:" % uid


def _base():
    return _raw_get_store() if _raw_get_store is not None else storage.get_store()


def store_for(uid):
    p = prefix_of(uid)
    return _base() if not p else UserStore(_base(), p)


def _scoped_store():
    return store_for(userctx.get_uid())


def install():
    """Make storage.get_store() return the current account's slice. Safe to call twice."""
    global _raw_get_store
    if _raw_get_store is None:
        _raw_get_store = storage.get_store
        storage.get_store = _scoped_store


# --------------------------------------------------------------------------- loading / saving the account list
def _users():
    with _lock:
        if _cache["users"] is None:
            v = _base().get(USERS_KEY, None)
            _cache["users"] = v if isinstance(v, dict) else {}
        return _cache["users"]


def _save_users():
    _base().set(USERS_KEY, _users())


def _invites():
    with _lock:
        if _cache["invites"] is None:
            v = _base().get(INVITES_KEY, None)
            _cache["invites"] = v if isinstance(v, dict) else {}
        return _cache["invites"]


def _save_invites():
    _base().set(INVITES_KEY, _invites())


def reset_cache():                                   # for tests
    with _lock:
        _cache.update(users=None, invites=None)


# --------------------------------------------------------------------------- passwords
def _b64(raw):
    return base64.b64encode(raw).decode("ascii")


def _hash(password, salt=None, rounds=PBKDF_ROUNDS):
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, rounds)
    return {"s": _b64(salt), "h": _b64(digest), "r": rounds}


def _matches(password, rec):
    try:
        digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), base64.b64decode(rec["s"]), int(rec["r"]))
        return hmac.compare_digest(digest, base64.b64decode(rec["h"]))
    except Exception:
        return False


def _owner_password():
    return os.environ.get("BETA_PASSWORD", "")


def password_taken(password, except_uid=None):
    owner = _owner_password()
    if owner and hmac.compare_digest(password.encode("utf-8"), owner.encode("utf-8")):
        return True
    return any(_matches(password, u["pw"]) for uid, u in _users().items() if uid != except_uid)


def authenticate(password):
    """The password decides who you are. Returns the account id, or None."""
    password = str(password or "")
    owner = _owner_password()
    if owner and hmac.compare_digest(password.encode("utf-8"), owner.encode("utf-8")):
        return OWNER_ID
    found = None
    for uid, u in list(_users().items()):            # always check everyone, so timing doesn't hint who exists
        if _matches(password, u["pw"]) and found is None:
            found = uid
    return found


# --------------------------------------------------------------------------- reading accounts
def _owner_prefs():
    v = _base().get(OWNER_KEY, None)
    return v if isinstance(v, dict) else {}


def is_owner(uid):
    return uid == OWNER_ID


def get_user(uid):
    """The account record (owner: a synthetic one built from env + saved prefs). None if it doesn't exist."""
    if uid == OWNER_ID:
        prefs = _owner_prefs()
        return {"id": OWNER_ID, "name": OWNER_NAME, "role": "owner", "theme": prefs.get("theme"), "interview_done": True,
                "paused": False, "own_key": None, "limit": None, "profile": {}}
    return _users().get(uid)


def _today():
    try:
        hours = float(os.environ.get("BETA_UTC_OFFSET_HOURS", "1") or 1)
    except ValueError:
        hours = 1.0
    return datetime.now(timezone(timedelta(hours=hours))).strftime("%Y-%m-%d")


def allowance(uid):
    """{'limit','used','left','own_key'} for a friend, None for the owner (no limit)."""
    u = get_user(uid)
    if not u or u["role"] == "owner":
        return None
    usage = u.get("usage") or {}
    used = usage.get("count", 0) if usage.get("date") == _today() else 0
    return {"limit": u["limit"], "used": used, "left": max(0, u["limit"] - used), "own_key": bool(u.get("own_key"))}


def can_send(uid):
    a = allowance(uid)
    return a is None or a["own_key"] or a["left"] > 0


def consume(uid):
    """One message used from the daily allowance (not counted when the friend uses their own key)."""
    with _lock:
        u = _users().get(uid)
        if not u or u.get("own_key"):
            return
        usage = u.get("usage") or {}
        if usage.get("date") != _today():
            usage = {"date": _today(), "count": 0}
        usage["count"] += 1
        u["usage"] = usage
        _save_users()


def public(uid):
    u = get_user(uid)
    if not u:
        return None
    return {"id": u["id"], "name": u["name"], "role": u["role"], "owner": u["role"] == "owner", "theme": u.get("theme"),
            "interview_done": bool(u.get("interview_done")), "own_key": bool(u.get("own_key")), "own_key_mask": u.get("own_key_mask"),
            "profile": u.get("profile") or {}, "allowance": allowance(uid)}


# --------------------------------------------------------------------------- invites and joining
def _norm_code(code):
    return re.sub(r"\s+", "", str(code or "")).upper()


def create_invite():
    with _lock:
        invites = _invites()
        for k in [k for k, v in invites.items() if time.time() - v.get("created", 0) > INVITE_DAYS * 86400 and not v.get("used_by")]:
            invites.pop(k, None)
        code = "FRIEND-" + "".join(secrets.choice(CODE_ALPHABET) for _ in range(6))
        invites[code] = {"created": time.time(), "used_by": None}
        _save_invites()
        return code


def invite_ok(code):
    inv = _invites().get(_norm_code(code))
    return bool(inv) and not inv.get("used_by") and time.time() - inv.get("created", 0) <= INVITE_DAYS * 86400


def open_invites():
    return [c for c in _invites() if invite_ok(c)]


def create_user(code, name, password):
    """Returns (user_id, {}) on success or (None, {field: message}) - one message per wrong field, nothing else is lost."""
    errors = {}
    code = _norm_code(code)
    name = re.sub(r"\s+", " ", str(name or "")).strip()[:30]
    password = str(password or "")
    if not invite_ok(code):
        errors["code"] = "That invite code isn't valid. Check it and try again."
    if not name:
        errors["name"] = "Enter your name."
    if len(password) < 6:
        errors["password"] = "Use at least 6 characters for the password."
    elif len(password) > 200:
        errors["password"] = "That password is too long."
    elif password_taken(password):
        errors["password"] = "Choose a different password."
    if errors:
        return None, errors
    with _lock:
        if not invite_ok(code):                      # someone used it a moment ago
            return None, {"code": "That invite code isn't valid. Check it and try again."}
        uid = re.sub(r"[^a-z0-9]", "", name.lower())[:12] + "-" + uuid.uuid4().hex[:4]
        _users()[uid] = {"id": uid, "name": name, "role": "friend", "pw": _hash(password), "created": time.time(),
                         "paused": False, "limit": default_limit(), "theme": DEFAULT_THEME, "interview_done": False,
                         "profile": {"style": -1, "likes": [], "note": ""}, "own_key": None, "usage": {"date": "", "count": 0}}
        _invites()[code]["used_by"] = uid
        _save_users()
        _save_invites()
    return uid, {}


# --------------------------------------------------------------------------- preferences and the interview
def set_theme(uid, theme):
    theme = str(theme or "")
    if not re.fullmatch(r"[a-z0-9-]{1,24}", theme):
        raise AccountError("Unknown theme.")
    with _lock:
        if uid == OWNER_ID:
            prefs = _owner_prefs()
            prefs["theme"] = theme
            _base().set(OWNER_KEY, prefs)
        else:
            _users()[uid]["theme"] = theme
            _save_users()


def set_profile(uid, style, likes, note):
    if uid == OWNER_ID:
        raise AccountError("The owner's profile is built into B.E.T.A.")
    try:
        style = int(style)
    except (TypeError, ValueError):
        style = -1
    style = style if style in (0, 1, 2) else -1
    likes = [x for x in (likes if isinstance(likes, list) else []) if x in LIKES][:9]
    note = re.sub(r"\s+", " ", str(note or "")).strip()[:300]
    with _lock:
        u = _users()[uid]
        u["profile"] = {"style": style, "likes": likes, "note": note}
        u["interview_done"] = True
        _save_users()


def greeting(uid):
    """B.E.T.A.'s first message, in the style the friend picked."""
    u = get_user(uid)
    p, n = u.get("profile") or {}, u["name"]
    likes = p.get("likes") or []
    if p.get("style") == 0:
        return "Hey %s. What do you need?" % n
    if p.get("style") == 2:
        return "Hello %s. I'm B.E.T.A. Tell me what you're working on and I'll go through it step by step." % n
    return "Hey %s! I'm B.E.T.A. Ready when you are.%s" % (n, (" Want the latest on %s?" % likes[0].lower()) if likes else "")


# --------------------------------------------------------------------------- admin
def list_friends():
    out = []
    for u in _users().values():
        a = allowance(u["id"])
        out.append({"id": u["id"], "name": u["name"], "limit": u["limit"], "used": a["used"], "paused": bool(u.get("paused")),
                    "own_key": bool(u.get("own_key")), "interview_done": bool(u.get("interview_done"))})
    return out


def admin_update(uid, limit=None, paused=None):
    with _lock:
        u = _users().get(uid)
        if not u:
            raise AccountError("That account doesn't exist.")
        if limit is not None:
            u["limit"] = max(5, min(1000, int(limit)))
        if paused is not None:
            u["paused"] = bool(paused)
        _save_users()


def delete_user(uid):
    """Wipes the account and its data. (The store's values are emptied; the account entry is removed.)"""
    if uid == OWNER_ID:
        raise AccountError("The owner account can't be deleted.")
    with _lock:
        if uid not in _users():
            return
        store = UserStore(_base(), prefix_of(uid))
        for key in PER_ACCOUNT_KEYS:
            try:
                store.set(key, None)
            except Exception:
                pass
        _users().pop(uid, None)
        _save_users()


def export_data(uid):
    u = get_user(uid)
    if not u:
        raise AccountError("That account doesn't exist.")
    store = store_for(uid)
    messages = store.get("memory", None)
    chat = [m for m in (messages if isinstance(messages, list) else []) if isinstance(m, dict) and m.get("role") in ("user", "assistant")]
    return {"name": u["name"], "theme": u.get("theme"), "profile": u.get("profile"), "created": u.get("created"),
            "chat": chat, "exported": int(time.time())}


# --------------------------------------------------------------------------- a friend's own Gemini key
def _box():
    secret = os.environ.get("SECRET_KEY", "")
    if not secret:
        raise AccountError("Saving a key needs SECRET_KEY to be set on the server.")
    try:
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        from cryptography.hazmat.primitives.kdf.hkdf import HKDF
    except Exception:
        raise AccountError("Saving a key needs the 'cryptography' package on the server.")
    return AESGCM(HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=b"beta-own-key").derive(secret.encode("utf-8")))


def check_gemini_key_format(key):
    key = str(key or "").strip()
    if not key:
        return "Paste your key first."
    if key.startswith("gsk_"):
        return "That is a Groq key. This box is for a Google AI Studio key, which starts with AIza."
    if not key.startswith("AIza"):
        return "That does not look like a Google AI Studio key. It should start with AIza."
    if not GEMINI_KEY_RE.match(key):
        return "That key looks cut off or has extra characters. Copy it again in full."
    return ""


def verify_gemini_key(key):
    """Asks Google whether the key works. Returns '' if it does, otherwise a plain-words reason."""
    url = "https://generativelanguage.googleapis.com/v1beta/models?pageSize=1&key=" + key
    try:
        with urllib.request.urlopen(urllib.request.Request(url), timeout=10) as r:
            r.read(200)
        return ""
    except urllib.error.HTTPError as e:
        if e.code in (400, 401, 403):
            return "Google rejected this key. Check you copied the whole key, or create a new one."
        return "Google couldn't check the key right now (HTTP %d). Try again in a minute." % e.code
    except Exception:
        return "Couldn't reach Google to check the key. Try again in a minute."


def set_own_key(uid, key):
    box = _box()
    nonce = os.urandom(12)
    enc = {"n": _b64(nonce), "c": _b64(box.encrypt(nonce, key.encode("utf-8"), uid.encode("utf-8")))}
    with _lock:
        _users()[uid]["own_key"] = enc
        _users()[uid]["own_key_mask"] = mask_key(key)
        _save_users()


def get_own_key(uid):
    u = _users().get(uid)
    enc = u.get("own_key") if u else None
    if not enc:
        return None
    try:
        return _box().decrypt(base64.b64decode(enc["n"]), base64.b64decode(enc["c"]), uid.encode("utf-8")).decode("utf-8")
    except Exception:
        return None


def remove_own_key(uid):
    with _lock:
        if uid in _users():
            _users()[uid]["own_key"] = None
            _users()[uid]["own_key_mask"] = None
            _save_users()


def mask_key(key):
    return key[:4] + "\u2022" * 8 + key[-4:]
