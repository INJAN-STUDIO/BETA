"""
B.E.T.A. - Best Everyday Technical Assistant (cloud edition of ALPHA).

A small Flask app that serves a phone-friendly chat page and a JSON API.

How a message flows (built for slow, flaky mobile connections):
    phone  --POST /api/send-->   server starts the agent in a background thread
                                 and answers immediately with a job id
    phone  --GET /api/poll-->    every second or so: "anything new for job X?"
                                 (tool activity, photo galleries, the reply)
Polling instead of one long request means a phone that switches apps, loses
signal for a moment, or hits Render's request time limit doesn't lose the answer.

Security (this is on the public internet, so it matters):
  - Everything except the page itself and /api/health needs the password.
  - Login is throttled; the session cookie is signed, HttpOnly, SameSite=Lax.
  - POSTs must carry a custom header, which cross-site pages can't send (CSRF).
  - The agent has NO file/terminal tools - see beta_agent.py.
"""

import hmac
import json
import mimetypes
import os
import shutil
import tempfile
import threading
import time
import uuid

from flask import Flask, jsonify, request, send_from_directory
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from werkzeug.middleware.proxy_fix import ProxyFix

import image_search

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")

app = Flask(__name__, static_folder=None)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1)   # Render sits behind a proxy: real client IP + https
app.config["MAX_CONTENT_LENGTH"] = 14 * 1024 * 1024

SESSION_COOKIE = "beta_session"
SESSION_DAYS = 30
LOGIN_MAX_FAILS = 5
LOGIN_WINDOW_S = 600
LOGIN_FAIL_DELAY = 0.6   # seconds - slows password guessing a little more
MAX_TEXT_CHARS = 8000
MAX_FILES = 4
MAX_FILE_BYTES = 5 * 1024 * 1024

TEXT_EXTENSIONS = {".txt", ".md", ".py", ".js", ".json", ".csv", ".html", ".css", ".xml",
                   ".yaml", ".yml", ".sh", ".log", ".ini", ".toml", ".cfg"}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}


# ---------------------------------------------------------------------------
# Config helpers
# ---------------------------------------------------------------------------

def _password():
    return os.environ.get("BETA_PASSWORD", "")


def _serializer():
    secret = os.environ.get("SECRET_KEY", "")
    if not secret:
        # Never fall back to a guessable key in production. A random one per
        # process means sessions reset on restart - annoying but safe.
        global _EPHEMERAL_SECRET
        if "_EPHEMERAL_SECRET" not in globals():
            _EPHEMERAL_SECRET = uuid.uuid4().hex
        secret = _EPHEMERAL_SECRET
    return URLSafeTimedSerializer(secret, salt="beta-session")


def _is_authed():
    token = request.cookies.get(SESSION_COOKIE, "")
    if not token:
        return False
    try:
        _serializer().loads(token, max_age=SESSION_DAYS * 86400)
        return True
    except (BadSignature, SignatureExpired):
        return False


# ---------------------------------------------------------------------------
# Agent (built lazily so /api/health works before keys are configured)
# ---------------------------------------------------------------------------

AGENT = None
AGENT_ERROR = None
_agent_lock = threading.Lock()
CURRENT_JOB = None


def get_agent():
    global AGENT, AGENT_ERROR
    with _agent_lock:
        if AGENT is not None:
            return AGENT
        try:
            import beta_agent
            AGENT = beta_agent.build_agent(
                on_provider_switch=_on_provider_switch,
                on_rate_limit=_on_rate_limit,
            )
            AGENT_ERROR = None
        except Exception as e:
            AGENT_ERROR = str(e)
            raise
        return AGENT


def _job_event(event):
    job = CURRENT_JOB
    if job is not None and not job["cancelled"]:
        job["events"].append(event)


def _on_provider_switch(kind, model, reason=None):
    if kind == "switched":
        why = "Gemini's daily quota is used up" if reason == "quota" else "Gemini is overloaded"
        _job_event({"type": "notice", "text": "Switched to a backup model (" + why + ")."})
    elif kind == "restored":
        _job_event({"type": "notice", "text": "Back on Gemini."})


def _on_rate_limit(wait_seconds=0, *args):
    _job_event({"type": "activity", "text": "Rate limit hit - waiting %ss..." % wait_seconds})


# ---------------------------------------------------------------------------
# Jobs
# ---------------------------------------------------------------------------

JOBS = {}
_jobs_lock = threading.Lock()


def _new_job():
    now = time.time()
    with _jobs_lock:
        for jid in [j for j, v in JOBS.items() if now - v["created"] > 900]:
            JOBS.pop(jid, None)
        job = {"id": uuid.uuid4().hex[:16], "events": [], "done": False, "cancelled": False, "created": now}
        JOBS[job["id"]] = job
        return job


def _active_job():
    with _jobs_lock:
        for job in JOBS.values():
            if not job["done"]:
                return job
    return None


def _friendly_error(e):
    text = str(e)
    if "GEMINI_API_KEY" in text:
        return "B.E.T.A. isn't fully set up yet: " + text
    return text[:600] or "Something went wrong."


def _run_job(job, text, saved_paths, tmpdir):
    global CURRENT_JOB
    CURRENT_JOB = job
    try:
        agent = get_agent()

        def on_tool(description):
            if not job["cancelled"]:
                job["events"].append({"type": "activity", "text": description})

        def on_images(payload):
            if not job["cancelled"]:
                job["events"].append({"type": "images", "payload": payload})

        reply = agent.send(text, attachments=saved_paths or None)
        if not job["cancelled"]:
            job["events"].append({"type": "reply", "text": reply or ""})
    except Exception as e:
        print("[B.E.T.A.] job failed:", repr(e))
        if not job["cancelled"]:
            job["events"].append({"type": "error", "text": _friendly_error(e)})
    finally:
        job["done"] = True
        CURRENT_JOB = None
        if tmpdir:
            shutil.rmtree(tmpdir, ignore_errors=True)


def _save_attachments(files):
    """Validate and write uploaded files to a temp dir. Returns (paths, tmpdir)
    or raises ValueError with a message safe to show the user."""
    if not files:
        return [], None
    if not isinstance(files, list) or len(files) > MAX_FILES:
        raise ValueError("You can attach up to %d files at a time." % MAX_FILES)
    import base64
    tmpdir = tempfile.mkdtemp(prefix="beta_")
    paths = []
    try:
        for f in files:
            name = str((f or {}).get("name", "file"))
            ext = os.path.splitext(name)[1].lower()
            try:
                raw = base64.b64decode((f or {}).get("data", ""), validate=True)
            except Exception:
                raise ValueError("Couldn't read the attachment '%s'." % name[:60])
            if not raw or len(raw) > MAX_FILE_BYTES:
                raise ValueError("'%s' is empty or larger than %d MB." % (name[:60], MAX_FILE_BYTES // 1048576))
            if ext in IMAGE_EXTENSIONS:
                mime = image_search._sniff_mime(raw)
                if not mime:
                    raise ValueError("'%s' doesn't look like a real image." % name[:60])
                ext = {"image/jpeg": ".jpg", "image/png": ".png", "image/gif": ".gif", "image/webp": ".webp"}[mime]
            elif ext in TEXT_EXTENSIONS or ext == ".docx":
                pass
            else:
                raise ValueError("'%s' isn't a supported type (images, text/code files and .docx work)." % name[:60])
            path = os.path.join(tmpdir, uuid.uuid4().hex[:10] + ext)   # never trust the client's filename
            with open(path, "wb") as out:
                out.write(raw)
            paths.append(path)
        return paths, tmpdir
    except Exception:
        shutil.rmtree(tmpdir, ignore_errors=True)
        raise


# ---------------------------------------------------------------------------
# Security: headers, CSRF, auth gate
# ---------------------------------------------------------------------------

@app.after_request
def _security_headers(resp):
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["X-Frame-Options"] = "DENY"
    resp.headers["Referrer-Policy"] = "no-referrer"
    resp.headers["X-Robots-Tag"] = "noindex, nofollow"
    resp.headers["Content-Security-Policy"] = (
        "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
        "script-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
    )
    if request.path.startswith("/api/"):
        resp.headers["Cache-Control"] = "no-store"
    return resp


PUBLIC_API = {"/api/health", "/api/login", "/api/me"}


@app.before_request
def _gate():
    if not request.path.startswith("/api/"):
        return None
    if request.method == "POST" and request.headers.get("X-Requested-With") != "beta":
        return jsonify(error="Bad request."), 403
    if request.path in PUBLIC_API:
        return None
    if not _password():
        return jsonify(error="Server is missing BETA_PASSWORD."), 503
    if not _is_authed():
        return jsonify(error="Not logged in."), 401
    return None


# ---------------------------------------------------------------------------
# Auth routes
# ---------------------------------------------------------------------------

_login_fails = {}
_login_lock = threading.Lock()


@app.route("/api/health")
def health():
    return jsonify(ok=True)


@app.route("/api/me")
def me():
    return jsonify(authed=_is_authed(), configured=bool(_password()))


@app.route("/api/login", methods=["POST"])
def login():
    if not _password():
        return jsonify(error="Server is missing BETA_PASSWORD."), 503
    ip = request.remote_addr or "?"
    now = time.time()
    with _login_lock:
        recent = [t for t in _login_fails.get(ip, []) if now - t < LOGIN_WINDOW_S]
        _login_fails[ip] = recent
        if len(recent) >= LOGIN_MAX_FAILS:
            wait = int(LOGIN_WINDOW_S - (now - recent[0]))
            return jsonify(error="Too many attempts. Try again in %d minutes." % max(1, wait // 60 + 1)), 429
    body = request.get_json(silent=True) or {}
    supplied = str(body.get("password", ""))
    if hmac.compare_digest(supplied.encode("utf-8"), _password().encode("utf-8")):
        with _login_lock:
            _login_fails.pop(ip, None)
        resp = jsonify(ok=True)
        resp.set_cookie(SESSION_COOKIE, _serializer().dumps({"u": 1}), max_age=SESSION_DAYS * 86400,
                        httponly=True, secure=request.is_secure, samesite="Lax", path="/")
        return resp
    with _login_lock:
        _login_fails.setdefault(ip, []).append(now)
    time.sleep(LOGIN_FAIL_DELAY)
    return jsonify(error="Wrong password."), 401


@app.route("/api/logout", methods=["POST"])
def logout():
    resp = jsonify(ok=True)
    resp.delete_cookie(SESSION_COOKIE, path="/")
    return resp


# ---------------------------------------------------------------------------
# Chat routes
# ---------------------------------------------------------------------------

def _history_for_ui(agent, limit=30):
    out = []
    for m in getattr(agent, "messages", []):
        role = m.get("role")
        if role not in ("user", "assistant"):
            continue
        content = m.get("content")
        if isinstance(content, list):   # user message with attachments
            content = " ".join(p.get("text", "") for p in content if isinstance(p, dict) and p.get("type") == "text")
        if not isinstance(content, str) or not content.strip():
            continue
        out.append({"role": role, "text": content})
    return out[-limit:]


@app.route("/api/state")
def state():
    try:
        agent = get_agent()
    except Exception as e:
        return jsonify(history=[], usage=None, active_job=None, setup_error=_friendly_error(e))
    active = _active_job()
    return jsonify(history=_history_for_ui(agent), usage=_usage(agent), active_job=active["id"] if active else None,
                   setup_error=None)


def _usage(agent):
    try:
        return agent.usage_snapshot()
    except Exception:
        return None


@app.route("/api/send", methods=["POST"])
def send():
    body = request.get_json(silent=True) or {}
    text = str(body.get("text", "")).strip()
    if not text:
        return jsonify(error="Type a message first."), 400
    if len(text) > MAX_TEXT_CHARS:
        return jsonify(error="That message is too long (max %d characters)." % MAX_TEXT_CHARS), 400
    if _active_job() is not None:
        return jsonify(error="B.E.T.A. is still working on your last message."), 409
    try:
        paths, tmpdir = _save_attachments(body.get("files"))
    except ValueError as e:
        return jsonify(error=str(e)), 400
    job = _new_job()
    threading.Thread(target=_run_job, args=(job, text, paths, tmpdir), daemon=True).start()
    return jsonify(job=job["id"])


@app.route("/api/poll")
def poll():
    job = JOBS.get(request.args.get("job", ""))
    if job is None:
        return jsonify(error="Unknown job.", gone=True), 404
    try:
        after = max(0, int(request.args.get("after", "0")))
    except ValueError:
        after = 0
    events = job["events"][after:]
    agent = AGENT
    return jsonify(events=events, next=after + len(events), done=job["done"] and not events,
                   usage=_usage(agent) if agent else None)


@app.route("/api/cancel", methods=["POST"])
def cancel():
    job = JOBS.get(str((request.get_json(silent=True) or {}).get("job", "")))
    if job:
        job["cancelled"] = True    # the model call itself can't be interrupted, but nothing more is shown
    return jsonify(ok=True)


@app.route("/api/clear", methods=["POST"])
def clear():
    if _active_job() is not None:
        return jsonify(error="Wait for the current reply to finish first."), 409
    try:
        agent = get_agent()
    except Exception as e:
        return jsonify(error=_friendly_error(e)), 503
    with agent._lock:
        agent.messages = [m for m in agent.messages if m.get("role") == "system"][:1]
        import agent_core
        agent_core.save_memory(agent.messages)
    return jsonify(ok=True)


@app.route("/api/full_image", methods=["POST"])
def full_image():
    url = str((request.get_json(silent=True) or {}).get("url", ""))
    agent = AGENT
    if not agent or url not in agent.allowed_image_urls:
        return jsonify(data=None)
    data = image_search.fetch_image_data_url(url, max_bytes=image_search.FULL_MAX_BYTES, timeout=15)
    return jsonify(data=data)


# ---------------------------------------------------------------------------
# Long-term memory panel
# ---------------------------------------------------------------------------

@app.route("/api/memory")
def memory_list():
    from personal_brain import brain_manager
    entries = []
    for i, fact in enumerate(brain_manager.load_db().get("facts", [])):
        ts = (fact.get("timestamp") or "").split("T")[0]
        entries.append({"id": i, "text": fact.get("content", ""), "meta": ts})
    return jsonify(entries=entries)


@app.route("/api/memory/delete", methods=["POST"])
def memory_delete():
    from personal_brain import brain_manager
    try:
        idx = int((request.get_json(silent=True) or {}).get("id"))
    except (TypeError, ValueError):
        return jsonify(error="Bad id."), 400
    data = brain_manager.load_db()
    facts = data.get("facts", [])
    if not 0 <= idx < len(facts):
        return jsonify(error="Not found."), 404
    facts.pop(idx)
    brain_manager.save_db(data)
    return jsonify(ok=True)


# ---------------------------------------------------------------------------
# The page itself
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return send_from_directory(STATIC_DIR, "index.html", max_age=0)


@app.route("/sw.js")
def service_worker():
    resp = send_from_directory(STATIC_DIR, "sw.js", max_age=0)
    resp.headers["Content-Type"] = "application/javascript"
    resp.headers["Service-Worker-Allowed"] = "/"
    return resp


@app.route("/static/<path:name>")
def static_files(name):
    resp = send_from_directory(STATIC_DIR, name, max_age=3600)
    return resp


@app.route("/manifest.webmanifest")
def manifest():
    resp = send_from_directory(STATIC_DIR, "manifest.webmanifest", max_age=3600)
    resp.headers["Content-Type"] = "application/manifest+json"
    return resp


@app.route("/robots.txt")
def robots():
    return "User-agent: *\nDisallow: /\n", 200, {"Content-Type": "text/plain"}


@app.errorhandler(413)
def too_big(_e):
    return jsonify(error="That upload is too large."), 413


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)
