"""
B.E.T.A. - the System report: one small test per thing B.E.T.A. needs, each run on its own so the phone can show
every result the moment it arrives (spinner -> tick / warning / cross).

Two sizes:
  quick - free or nearly free: the server itself, saved data, long-term memory, every AI model (one tiny question
          each), the Groq backup key, the read-aloud voice, and (for the owner) alerts, K-10 and Termux.
  full  - everything in quick, plus the services that spend a little of a free allowance: web/image search and the
          image-generation key. (The picture model itself is never run - only its key is checked.)

Nothing here sends a real notification or mail, runs a Termux command, or leaves test data behind.
"""

import json
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

import gemini_status

UA = "B.E.T.A.-system-report/1.0"
MIN_INTERVAL = 8            # seconds: asking for the same check again sooner returns the saved answer (protects free quotas)

OK, SLOW, WARN, FAIL, OFF = "ok", "slow", "warn", "fail", "off"      # OFF = not set up / not for this account (never counts as a problem)

_cache = {}
_cache_lock = threading.Lock()


def _res(state, detail, ms=0, hint=""):
    return {"state": state, "detail": detail, "ms": int(ms), "hint": hint}


def _http(url, method="GET", headers=None, body=None, timeout=10):
    """Returns (status, body_text, ms). status 0 = no answer. Never raises."""
    h = {"User-Agent": UA}
    h.update(headers or {})
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        h.setdefault("Content-Type", "application/json")
    req = urllib.request.Request(url, data=data, headers=h, method=method)
    t0 = time.time()
    code, text = 0, ""
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            code = resp.status
            text = resp.read(4000).decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        code = e.code
        try:
            text = e.read(400).decode("utf-8", "replace")
        except Exception:
            text = ""
    except Exception as e:
        text = str(e)[:160]
    return code, text, (time.time() - t0) * 1000


# ---------------------------------------------------------------------------
# The plan: which checks exist for this account
# ---------------------------------------------------------------------------

def plan(owner, models):
    """[{id, label, group, full}] in the order they are shown. full=True rows only run in the full report."""
    rows = [
        {"id": "server", "label": "B.E.T.A. server", "group": "Server", "full": False},
        {"id": "storage", "label": "Saved data and chats", "group": "Server", "full": False},
        {"id": "memory", "label": "Long-term memory", "group": "Server", "full": False},
    ]
    for m in models:
        rows.append({"id": "model:" + m, "label": "Gemini " + _short(m), "group": "AI models", "full": False})
    rows.append({"id": "groq", "label": "Groq backup models", "group": "AI models", "full": False})
    rows.append({"id": "tts", "label": "Read-aloud voice", "group": "Services", "full": False})
    if owner:
        rows.append({"id": "alerts", "label": "Reply alerts", "group": "Services", "full": False})
        rows.append({"id": "k10", "label": "K-10 mail", "group": "Services", "full": False})
        rows.append({"id": "termux", "label": "Termux bridge", "group": "Services", "full": False})
    rows.append({"id": "search", "label": "Web and image search", "group": "Services", "full": True})
    rows.append({"id": "imagegen", "label": "Image generation (key check)", "group": "Services", "full": True})
    return rows


def _short(m):
    return str(m or "").replace("groq:", "").replace("gemini-", "").split("/")[-1]


# ---------------------------------------------------------------------------
# The checks. Each takes the shared context dict `x` and returns a result.
# ---------------------------------------------------------------------------

def check_server(x):
    commit = (os.environ.get("RENDER_GIT_COMMIT", "") or "")[:7]
    return _res(OK, "Release %s%s" % (x["version"], (" - commit " + commit) if commit else ""))


def check_storage(x):
    store = x["storage"].get_store()
    key, val = "system_report_probe", "ok-%d" % int(time.time())
    t0 = time.time()
    store.set(key, val)
    back = store.get(key, None)
    ms = (time.time() - t0) * 1000
    try:
        remove = getattr(store, "delete", None)
        if callable(remove):
            remove(key)
    except Exception:
        pass
    if back != val:
        return _res(FAIL, "Saved a test value but got a different one back.", ms,
                    "Check SUPABASE_URL / SUPABASE_KEY on Render and the Render logs for storage errors.")
    return _res(SLOW if ms > 4000 else OK, "Saved and read back a test value", ms)


def check_memory(x):
    from personal_brain import brain_manager
    facts = brain_manager.load_db().get("facts", [])
    return _res(OK, "%d saved fact%s readable" % (len(facts), "" if len(facts) == 1 else "s"))


def check_model(x, model):
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not key:
        return _res(FAIL, "GEMINI_API_KEY isn't set on the server.", 0, "Add it in Render -> Environment.")
    r = gemini_status.probe(key, model)
    if r["state"] in ("ok", "slow") and x.get("on_model_ok"):
        try:
            x["on_model_ok"](model)
        except Exception:
            pass
    state = {"ok": OK, "slow": SLOW, "limited": WARN}.get(r["state"], FAIL)
    hint = ""
    if r["state"] == "limited":
        hint = "Its free allowance is used up for now. B.E.T.A. moves to the next model on its own."
    elif r["state"] in ("overloaded", "timeout"):
        hint = "Google is busy. B.E.T.A. skips this model and tries the next one."
    return _res(state, r["detail"][:1].upper() + r["detail"][1:], r["ms"], hint)


def check_groq(x):
    key = os.environ.get("GROQ_API_KEY", "").strip()
    if not key:
        return _res(OFF, "Not set up (optional backup)")
    code, text, ms = _http("https://api.groq.com/openai/v1/models", headers={"Authorization": "Bearer " + key})
    if code == 200:
        try:
            n = len(json.loads(text).get("data", []))
        except Exception:
            n = 0
        return _res(SLOW if ms > 4000 else OK, "Key accepted" + (", %d models listed" % n if n else ""), ms)
    if code in (401, 403):
        return _res(FAIL, "Groq rejected the key.", ms, "Make a new key at console.groq.com and update GROQ_API_KEY.")
    if code == 429:
        return _res(WARN, "Groq is limiting requests right now.", ms)
    return _res(FAIL, "No proper answer (%s)." % (code or "no reply"), ms)


def check_tts(x):
    tts = x["tts_edge"]
    t0 = time.time()
    try:
        audio = tts.synthesize("Testing, one two three.", x.get("voice") or tts.DEFAULT_VOICE)
    except tts.TTSError as e:
        return _res(FAIL, str(e)[:140], (time.time() - t0) * 1000, "The voice service (Microsoft Edge TTS) may be down or blocking the server.")
    ms = (time.time() - t0) * 1000
    if not audio or len(audio) < 500:
        return _res(FAIL, "The voice service answered with no sound.", ms)
    return _res(SLOW if ms > 6000 else OK, "Voice answered (%d KB of audio)" % max(1, len(audio) // 1024), ms)


def check_alerts(x):
    """'Notify me when a reply is ready': FCM for the Android app, browser push for the web page. Sends nothing."""
    f = x.get("fcm") or {}
    web = int(x.get("web_subs") or 0)
    last = f.get("last") or {}
    if f.get("ready"):
        if f.get("tokens"):
            if last.get("ok") is False:
                return _res(WARN, "Your last alert did not arrive: %s" % str(last.get("detail", ""))[:120], 0,
                            "Open the app and switch 'Notify me when a reply is ready' off and on again.")
            return _res(OK, "Ready - %d phone%s registered" % (f["tokens"], "" if f["tokens"] == 1 else "s"))
        if web:
            return _res(OK, "Browser notifications are on")
        return _res(WARN, "Set up, but no phone is registered yet", 0,
                    "In the app, turn on 'Notify me when a reply is ready'.")
    if web:
        return _res(OK, "Browser notifications are on (the Android app needs the Firebase key to get alerts)")
    if x.get("legacy"):
        return _res(WARN, "Alerts work on a backup channel only", 0, "Finish the Firebase setup (FIREBASE_SERVICE_ACCOUNT on Render).")
    return _res(OFF, "Not set up (FIREBASE_SERVICE_ACCOUNT is missing)")


def check_k10(x):
    k = x["k10_bridge"]
    if not k.enabled():
        return _res(OFF, "Not set up (needs K10_KEY, SUPABASE_URL and SUPABASE_KEY)")
    st = k.status()
    if st.get("ready"):
        n = st.get("unread")
        return _res(OK, "Connected" + (" - %d unread" % n if n else ""))
    msg = str(st.get("message") or "Not connected")[:140]
    if st.get("state") in ("connecting", "reconnecting"):
        return _res(WARN, msg, 0, "It retries by itself; run the report again in a minute.")
    return _res(FAIL, msg, 0, "See K-10 mail in the menu for the log.")


def check_termux(x):
    t = x["term_bridge"]
    if not t.enabled():
        return _res(OFF, "Not set up")
    if t.connected():
        return _res(OK, "Termux is connected")
    return _res(WARN, "Set up, but the Termux script isn't connected right now.", 0,
                "Open Termux on the phone and start the B.E.T.A. script.")


def check_search(x):
    key = os.environ.get("SERPER_API_KEY", "").strip()
    if not key:
        return _res(OFF, "Not set up (SERPER_API_KEY is missing)")
    code, text, ms = _http("https://google.serper.dev/search", "POST",
                           {"X-API-KEY": key}, {"q": "B.E.T.A. system check", "num": 1}, timeout=12)
    if code == 200:
        return _res(SLOW if ms > 5000 else OK, "Search answered (used 1 search credit)", ms)
    if code in (401, 403):
        return _res(FAIL, "Serper rejected the key.", ms, "Check SERPER_API_KEY.")
    if code == 429:
        return _res(WARN, "Serper says the allowance is used up.", ms)
    return _res(FAIL, "No proper answer (%s)." % (code or "no reply"), ms)


def check_imagegen(x):
    env = os.environ
    acct, token = env.get("CLOUDFLARE_ACCOUNT_ID", "").strip(), env.get("CLOUDFLARE_API_TOKEN", "").strip()
    gkey = env.get("GEMINI_IMAGE_API_KEY", "").strip()
    note = " (the picture model itself isn't run, to save your free allowance)"
    if acct and token:
        total = 0
        for url in ("https://api.cloudflare.com/client/v4/accounts/%s/tokens/verify" % urllib.parse.quote(acct, safe=""),
                    "https://api.cloudflare.com/client/v4/user/tokens/verify"):
            code, text, ms = _http(url, headers={"Authorization": "Bearer " + token})
            total += ms
            if code == 200 and '"success":true' in text.replace(" ", ""):
                return _res(OK, "Cloudflare key is active" + note, total)
        return _res(FAIL, "Cloudflare didn't accept the key.", total, "Check CLOUDFLARE_ACCOUNT_ID and CLOUDFLARE_API_TOKEN.")
    if gkey:
        code, text, ms = _http("https://generativelanguage.googleapis.com/v1beta/models?pageSize=1", headers={"x-goog-api-key": gkey})
        if code == 200:
            return _res(OK, "Google image key is active" + note, ms)
        return _res(FAIL, "Google didn't accept the image key (%s)." % (code or "no reply"), ms, "Check GEMINI_IMAGE_API_KEY.")
    return _res(OFF, "Not set up")


# ---------------------------------------------------------------------------
# Running one check
# ---------------------------------------------------------------------------

SIMPLE = {"server": check_server, "storage": check_storage, "memory": check_memory, "groq": check_groq, "tts": check_tts,
          "alerts": check_alerts, "k10": check_k10, "termux": check_termux, "search": check_search, "imagegen": check_imagegen}


def run(check_id, x, uid, allowed_ids):
    """Runs one check (id must be in this account's plan). Never raises. Recent answers are reused for MIN_INTERVAL seconds."""
    if check_id not in allowed_ids:
        return None
    ck = (uid, check_id)
    now = time.time()
    with _cache_lock:
        hit = _cache.get(ck)
        if hit and now - hit[0] < MIN_INTERVAL:
            return dict(hit[1], cached=True)
    try:
        if check_id.startswith("model:"):
            res = check_model(x, check_id[6:])
        else:
            res = SIMPLE[check_id](x)
    except Exception as e:                                     # a broken check is reported, never a crash
        res = _res(FAIL, "The check itself failed: %s" % (str(e)[:120] or type(e).__name__))
    res["id"] = check_id
    with _cache_lock:
        _cache[ck] = (time.time(), res)
        for k in [k for k, v in _cache.items() if time.time() - v[0] > 300]:
            _cache.pop(k, None)
    return res
