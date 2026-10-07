"""
ALPHA - daily request tracker.

Powers the "requests left today" indicator in the GUI. Neither Gemini nor
Groq tells you how many requests you have left (Gemini sends no quota
headers at all), so ALPHA counts its own successful requests per model and
compares them with each model's daily limit.

Things worth knowing:
  - Gemini free-tier quotas are per MODEL (and per project), and reset at
    midnight Pacific time - so counts are keyed by model and the day is
    computed in Pacific time, not local time.
  - Each model-API call is one request. A reply that needs 3 tool calls
    costs 4 requests (3 tool rounds + the final answer), not 1.
  - The numbers are an ESTIMATE: they only see requests made by ALPHA on this
    machine. Anything else using the same key (AI Studio playground, another
    device) isn't counted. A real "daily quota exceeded" error from Google
    is the final word and marks that model as exhausted for the day.
  - Google doesn't publish free-tier limits any more - AI Studio shows the
    ones active on YOUR project. Override the defaults below by adding a
    "daily_limits" object to personal_brain/config.json, e.g.
        "daily_limits": {"gemini-3.8-flash": 20, "gemini-3.1-flash-lite": 500}
"""

import json
import os
import threading
from datetime import datetime, timedelta, timezone

try:
    from zoneinfo import ZoneInfo
    _PACIFIC = ZoneInfo("America/Los_Angeles")
except Exception:  # tzdata missing - fixed UTC-8 is close enough for a counter
    _PACIFIC = timezone(timedelta(hours=-8))

# Last verified October 2026 (third-party trackers + Google AI Studio forum
# reports) - treat as starting points and correct them from AI Studio.
DEFAULT_DAILY_LIMITS = {
    "gemini-3.8-flash": 20,
    "gemini-3.7-flash": 20,
    "gemini-3.6-flash": 20,
    "gemini-3.5-flash": 20,
    "gemini-3.1-flash-lite": 500,
    "openai/gpt-oss-120b": 1000,  # Groq
}


class UsageTracker:
    def __init__(self, usage_path, config_path=None):
        self._path = usage_path
        self._config_path = config_path
        self._lock = threading.Lock()
        self._limits = dict(DEFAULT_DAILY_LIMITS)
        self._load_limit_overrides()
        self._state = {"date": self._today(), "counts": {}, "exhausted": []}
        self._load()

    # -- internals -------------------------------------------------------
    @staticmethod
    def _today():
        return datetime.now(_PACIFIC).strftime("%Y-%m-%d")

    def _load_limit_overrides(self):
        if not self._config_path or not os.path.exists(self._config_path):
            return
        try:
            with open(self._config_path, "r") as f:
                overrides = json.load(f).get("daily_limits", {})
            for model, limit in overrides.items():
                if isinstance(limit, int) and limit > 0:
                    self._limits[model] = limit
        except Exception:
            pass  # a bad config must never stop ALPHA from starting

    def _load(self):
        try:
            with open(self._path, "r") as f:
                data = json.load(f)
            if data.get("date") == self._today():
                self._state = {
                    "date": data["date"],
                    "counts": dict(data.get("counts", {})),
                    "exhausted": list(data.get("exhausted", [])),
                }
        except Exception:
            pass  # missing/corrupt file -> start today's count from zero

    def _save(self):
        try:
            tmp = self._path + ".tmp"
            with open(tmp, "w") as f:
                json.dump(self._state, f)
            os.replace(tmp, self._path)
        except Exception:
            pass  # losing a counter write is never worth crashing a reply

    def _roll_if_new_day(self):
        today = self._today()
        if self._state["date"] != today:
            self._state = {"date": today, "counts": {}, "exhausted": []}
            self._save()

    # -- public API ------------------------------------------------------
    def record(self, model_id):
        """Call once per successful model request."""
        with self._lock:
            self._roll_if_new_day()
            counts = self._state["counts"]
            counts[model_id] = counts.get(model_id, 0) + 1
            self._save()

    def mark_exhausted(self, model_id):
        """Call when Google/Groq reports this model's DAILY quota is gone."""
        with self._lock:
            self._roll_if_new_day()
            if model_id not in self._state["exhausted"]:
                self._state["exhausted"].append(model_id)
                self._save()

    def is_exhausted(self, model_id):
        with self._lock:
            self._roll_if_new_day()
            return model_id in self._state["exhausted"]

    def limit_for(self, model_id):
        return self._limits.get(model_id)

    def entry(self, model_id):
        with self._lock:
            self._roll_if_new_day()
            used = self._state["counts"].get(model_id, 0)
            exhausted = model_id in self._state["exhausted"]
        limit = self._limits.get(model_id)
        if exhausted:
            remaining = 0
        elif limit is None:
            remaining = None
        else:
            remaining = max(0, limit - used)
        return {
            "model": model_id,
            "used": used,
            "limit": limit,
            "remaining": remaining,
            "exhausted": exhausted,
        }

    def seconds_until_reset(self):
        now = datetime.now(_PACIFIC)
        midnight = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        return int((midnight - now).total_seconds())
