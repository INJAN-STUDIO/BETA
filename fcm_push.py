"""Firebase Cloud Messaging (FCM): the push channel the B.E.T.A. Android app listens to.

Why: the installed Android app is a Capacitor WebView, and a WebView cannot receive browser Web Push. FCM is the way
Android delivers "your reply is ready" to an app that is closed - the same mechanism the big apps use.

Server setup (once, on Render -> Environment):
    FIREBASE_SERVICE_ACCOUNT   the whole contents of the service-account JSON file from Firebase
                               (Project settings -> Service accounts -> Generate new private key)
No extra Python package is needed: the sign-in token is made with `cryptography`, which pywebpush already installs.

The phone's own FCM token is saved by app.py (POST /api/fcm/register); this module only sends.
Never raises: a failed alert must not break a reply.
"""
import base64
import json
import os
import threading
import time
import urllib.error
import urllib.request

SCOPE = "https://www.googleapis.com/auth/firebase.messaging"
CHANNEL_ID = "beta_replies"            # the Android notification channel the app creates (see static/app.js)

STATUS = {"t": 0.0, "ok": None, "detail": ""}      # shown in the System report so a failed alert is never a mystery

_lock = threading.Lock()
_cache = {"raw": None, "acct": None, "token": None, "exp": 0.0}


def _account():
    raw = os.environ.get("FIREBASE_SERVICE_ACCOUNT", "").strip()
    if not raw:
        b64 = os.environ.get("FIREBASE_SERVICE_ACCOUNT_B64", "").strip()      # same file, base64-encoded (easier to paste)
        if b64:
            try:
                raw = base64.b64decode(b64).decode("utf-8")
            except Exception:
                return None
    if not raw:
        return None
    if _cache["raw"] == raw:
        return _cache["acct"]
    try:
        acct = json.loads(raw)
        if not (acct.get("client_email") and acct.get("private_key") and acct.get("project_id")):
            acct = None
    except Exception:
        acct = None
    _cache.update(raw=raw, acct=acct, token=None, exp=0.0)
    return acct


def ready():
    return _account() is not None


def _b64u(b):
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode("ascii")


def _signed_jwt(acct, now):
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding
    head = _b64u(json.dumps({"alg": "RS256", "typ": "JWT"}).encode())
    claims = _b64u(json.dumps({
        "iss": acct["client_email"], "scope": SCOPE, "aud": acct.get("token_uri") or "https://oauth2.googleapis.com/token",
        "iat": int(now), "exp": int(now) + 3600}).encode())
    key = serialization.load_pem_private_key(acct["private_key"].encode("utf-8"), password=None)
    sig = key.sign((head + "." + claims).encode("ascii"), padding.PKCS1v15(), hashes.SHA256())
    return head + "." + claims + "." + _b64u(sig)


def _access_token(acct):
    now = time.time()
    with _lock:
        if _cache["token"] and now < _cache["exp"] - 60:
            return _cache["token"]
    assertion = _signed_jwt(acct, now)
    data = ("grant_type=urn%3Aietf%3Aparams%3Aoauth%3Agrant-type%3Ajwt-bearer&assertion=" + assertion).encode("ascii")
    req = urllib.request.Request(acct.get("token_uri") or "https://oauth2.googleapis.com/token", data=data,
                                 headers={"Content-Type": "application/x-www-form-urlencoded"}, method="POST")
    with urllib.request.urlopen(req, timeout=10) as resp:
        out = json.loads(resp.read().decode("utf-8"))
    with _lock:
        _cache["token"] = out["access_token"]
        _cache["exp"] = now + int(out.get("expires_in", 3600))
    return out["access_token"]


def _http_error_text(e):
    try:
        body = json.loads(e.read(600).decode("utf-8", "replace"))
        err = body.get("error", {})
        return "HTTP %s %s" % (e.code, err.get("status") or err.get("message") or "")
    except Exception:
        return "HTTP %s" % e.code


def send_one(token, title, body):
    """Returns 'ok', 'dead' (this phone's token is no longer valid - forget it) or an error text."""
    acct = _account()
    if not acct:
        return "FIREBASE_SERVICE_ACCOUNT is missing or not valid JSON"
    try:
        access = _access_token(acct)
    except urllib.error.HTTPError as e:
        return "sign-in to Google failed (%s) - check the service-account key" % _http_error_text(e)
    except Exception as e:
        return "sign-in to Google failed: %r" % (e,)
    payload = {"message": {
        "token": token,
        "notification": {"title": title, "body": body},
        "android": {"priority": "HIGH", "ttl": "3600s",
                    "notification": {"channel_id": CHANNEL_ID, "tag": "beta", "default_sound": True}},
    }}
    url = "https://fcm.googleapis.com/v1/projects/%s/messages:send" % acct["project_id"]
    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), method="POST",
                                 headers={"Authorization": "Bearer " + access, "Content-Type": "application/json; charset=UTF-8"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            resp.read()
        return "ok"
    except urllib.error.HTTPError as e:
        text = _http_error_text(e)
        if e.code == 404 or "UNREGISTERED" in text or ("INVALID_ARGUMENT" in text and e.code == 400):
            return "dead"
        if e.code in (401, 403):
            with _lock:
                _cache["token"] = None                       # force a fresh sign-in next time
        return text
    except Exception as e:
        return repr(e)[:120]


def send_many(tokens, title, body):
    """Send to every saved phone. Returns (how many arrived, tokens to forget). Updates STATUS for the System report."""
    sent, dead, last_err = 0, [], ""
    for tok in tokens:
        r = send_one(tok, title, body)
        if r == "ok":
            sent += 1
        elif r == "dead":
            dead.append(tok)
        else:
            last_err = r
    if sent:
        STATUS.update(t=time.time(), ok=True, detail="sent")
    elif tokens:
        STATUS.update(t=time.time(), ok=False, detail=last_err or "the phone's token is no longer valid; open the app and turn notifications on again")
    return sent, dead
