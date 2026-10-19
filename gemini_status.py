"""
B.E.T.A. - a live check of how busy Google's Gemini servers are, right now.

Google's own status page often says "all good" while models are returning "high demand" errors, so this asks the
models themselves: it sends each one a tiny test request and reports how it answered and how fast. Each test uses a
little of that model's daily allowance, so the chat page only checks while its traffic window is open.
"""

import json
import threading
import time
import urllib.error
import urllib.request

ROOT = "https://generativelanguage.googleapis.com/v1beta/models"
OFFICIAL_STATUS_URL = "https://aistudio.google.com/status"
SLOW_MS = 4000
MIN_INTERVAL = 8            # seconds: the same answer is reused if asked again sooner
HISTORY_LEN = 30

_lock = threading.Lock()
_history = {}               # model -> [(unix time, state, ms), ...]
_cache = {"t": 0.0, "key": None, "data": None}


def classify(code, ms, text=""):
    low = (text or "").lower()
    if code == 200:
        return "slow" if ms >= SLOW_MS else "ok"
    if code == 429:
        return "limited"
    if code in (500, 502, 503, 504) or "unavailable" in low or "high demand" in low or "overloaded" in low:
        return "overloaded"
    if code == 0:
        return "timeout"
    return "error"


def probe(api_key, model, timeout=15):
    body = json.dumps({"contents": [{"role": "user", "parts": [{"text": "ping"}]}],
                       "generationConfig": {"maxOutputTokens": 8, "temperature": 0}}).encode("utf-8")
    req = urllib.request.Request("%s/%s:generateContent" % (ROOT, model), data=body, method="POST",
                                 headers={"Content-Type": "application/json", "x-goog-api-key": api_key})
    t0, code, text = time.time(), 0, ""
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            code = resp.status
            resp.read()
    except urllib.error.HTTPError as e:
        code = e.code
        try:
            text = e.read().decode("utf-8", "replace")[:400]
        except Exception:
            text = ""
    except Exception as e:
        text = str(e)[:200]
    ms = int((time.time() - t0) * 1000)
    state = classify(code, ms, text)
    detail = {"ok": "answered", "slow": "answered, but slowly", "limited": "rate or daily limit reached",
              "overloaded": "Google says it is overloaded (high demand)", "timeout": "no answer in time"}.get(state, "error %s" % code)
    return {"model": model, "state": state, "ms": ms, "code": code, "detail": detail}


def _verdict(results):
    n = len(results)
    bad = sum(1 for r in results if r["state"] in ("overloaded", "timeout"))
    limited = sum(1 for r in results if r["state"] == "limited")
    slow = sum(1 for r in results if r["state"] == "slow")
    if n == 0:
        return "unknown", "No models to check."
    if bad >= max(2, (n + 1) // 2) or bad == n:
        return "heavy", "Heavy traffic: most models are overloaded or not answering. Expect failures - B.E.T.A. may switch to Groq."
    if bad:
        return "busy", "Some models are overloaded right now. Others still work."
    if limited == n:
        return "quota", "Every model has hit its rate or daily limit."
    if slow:
        return "slow", "Models are answering, but slowly - Google is under some load."
    if limited:
        return "ok", "Models are answering normally (one has hit its own limit)."
    return "ok", "Everything is answering normally."


def check(api_key, models, on_success=None, force=False):
    """Probe every model at once. Returns {checked_at, verdict, message, models:[...], official_url}."""
    key = (api_key, tuple(models))
    with _lock:
        if not force and _cache["key"] == key and _cache["data"] and time.time() - _cache["t"] < MIN_INTERVAL:
            return _cache["data"]
    results = [None] * len(models)

    def run(i, m):
        results[i] = probe(api_key, m)

    threads = [threading.Thread(target=run, args=(i, m), daemon=True) for i, m in enumerate(models)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(25)
    results = [r or {"model": models[i], "state": "timeout", "ms": 25000, "code": 0, "detail": "no answer in time"}
               for i, r in enumerate(results)]
    now = time.time()
    with _lock:
        for r in results:
            h = _history.setdefault(r["model"], [])
            h.append((now, r["state"], r["ms"]))
            del h[:-HISTORY_LEN]
            r["history"] = [{"t": int(a), "state": b, "ms": c} for a, b, c in h]
    if on_success:
        for r in results:
            if r["state"] in ("ok", "slow"):
                try:
                    on_success(r["model"])
                except Exception:
                    pass
    verdict, message = _verdict(results)
    data = {"checked_at": int(now), "verdict": verdict, "message": message, "models": results, "official_url": OFFICIAL_STATUS_URL}
    with _lock:
        _cache.update(t=now, key=key, data=data)
    return data
