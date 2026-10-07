"""
B.E.T.A. - builds the cloud agent.

This is ALPHA's agent (agent_core.py) with four changes, all applied here
rather than by editing ALPHA's code:
  1. Tools: only cloud-safe ones. No terminal, no file access, no email, no
     clipboard - the server has no business touching files, and a public
     endpoint must never offer a shell.
  2. Memory: conversation history, long-term facts and daily request counts
     are stored through storage.py (Supabase) instead of local files.
  3. Persona: B.E.T.A., written for a phone screen.
  4. Approvals: every remaining tool is read-only or writes only B.E.T.A.'s
     own memory, so they run without asking each time (a permission pop-up
     per web search would be miserable on a phone).
"""

import json
import os

import agent_core as ac
import image_search
import storage
from usage_tracker import UsageTracker

CLOUD_TOOLS = {
    "web_search",
    "search_images",
    "watch_youtube_video",
    "save_long_term_memory",
    "search_long_term_memory",
}

MAX_REMEMBERED = 30  # a little shorter than ALPHA's 40 - less to load and send each turn

BETA_PROMPT = """You are B.E.T.A, which stands for Best Everyday Technical Assistant - the cloud
companion of A.L.P.H.A. You run on a server and the user opens you in the browser
on his phone (a Huawei Honor 8x). Refer to the user as "Karachi". He is a self-taught
developer building INJAN Technologies: ALPHA (a desktop assistant on his Fedora laptop),
BETA OS, and more. You are NOT on his laptop and cannot see or change his files, run
commands, or reach ALPHA - if he asks for that, say so plainly and suggest using ALPHA
on his laptop instead.

What you can do: search the web (web_search), find and show photos (search_images),
watch and analyze YouTube videos (watch_youtube_video), read images and text files he
attaches, and keep long-term memory (save_long_term_memory / search_long_term_memory).

He reads on a small phone screen, so keep answers tight: lead with the answer, short
paragraphs, no filler. Markdown works - use short lists and tables when comparing
things, and headings only for longer answers. Explain technical things in plain,
simple language and say why, not just what.

Your recent conversation (about the last 30 messages) is visible to you automatically.
Use long-term memory only for durable facts worth keeping forever (his projects, setup,
preferences, decisions) - not for routine questions.

When you use web_search, don't just relay the first result. Search more than once if
needed, check whether different sites agree, say so when sources conflict, and explain
what you found in your own simple words. Be careful with anything technical (commands,
versions, whether a method is still current).

When he asks for photos or pictures (or seeing images would clearly help), use
search_images with count=4 - the photos appear in the chat by themselves, so don't paste
links. For anything that could show violence, injury, death, destruction or other
distressing scenes (attacks, bombings, wars, accidents, disasters) set sensitive=true and
give a SHORT warning saying what the photos may show - the app blurs them and prints your
warning on each one so he can decide whether to open them. In your reply, say briefly that
they're blurred and why, mention which sites they came from, and remind him that photos
found on the web are often from other dates or other events - never claim a photo shows
the specific event he asked about unless its source says so."""


class CloudUsage(UsageTracker):
    """UsageTracker whose daily counts live in the shared store, and whose
    limits can come from the BETA_DAILY_LIMITS environment variable."""

    def __init__(self, store):
        self._store = store
        super().__init__(usage_path="(unused)")

    def _load_limit_overrides(self):
        raw = os.environ.get("BETA_DAILY_LIMITS", "").strip()
        if not raw:
            return
        try:
            for model, limit in json.loads(raw).items():
                if isinstance(limit, int) and limit > 0:
                    self._limits[model] = limit
        except Exception:
            print("[B.E.T.A.] BETA_DAILY_LIMITS isn't valid JSON - ignoring it.")

    def _load(self):
        data = self._store.get("usage", None)
        if isinstance(data, dict) and data.get("date") == self._today():
            self._state = {"date": data["date"], "counts": dict(data.get("counts", {})),
                           "exhausted": list(data.get("exhausted", []))}

    def _save(self):
        self._store.set("usage", self._state)


def _load_memory():
    store = storage.get_store()
    messages = store.get("memory", None)
    if isinstance(messages, list):
        cleaned = ac.AIRIS.heal_history(messages)
        if cleaned and cleaned[0].get("role") == "system":
            return cleaned
        return [{"role": "system", "content": ac.SYSTEM_PROMPT}] + cleaned
    return [{"role": "system", "content": ac.SYSTEM_PROMPT}]


def _save_memory(messages):
    messages = ac.AIRIS.heal_history(messages)
    system_msgs = [m for m in messages if m.get("role") == "system"]
    rest = [m for m in messages if m.get("role") != "system"]
    budget = max(ac.MAX_REMEMBERED_MESSAGES - len(system_msgs), 0)
    storage.get_store().set("memory", system_msgs + rest[-budget:])


def configure():
    """Apply the cloud settings to agent_core. Safe to call more than once."""
    ac.ALLOWED_TOOLS = set(CLOUD_TOOLS)
    ac.SYSTEM_PROMPT = BETA_PROMPT
    ac.MAX_REMEMBERED_MESSAGES = MAX_REMEMBERED
    ac.load_memory = _load_memory
    ac.save_memory = _save_memory
    ac.USAGE = CloudUsage(storage.get_store())
    # Phone data plan: keep image payloads small. Serper thumbnails are tiny;
    # anything bigger than this is skipped rather than sent over mobile data.
    image_search.THUMB_MAX_BYTES = 150_000
    image_search.FULL_MAX_BYTES = 3_000_000


def build_agent(on_provider_switch=None, on_rate_limit=None, on_usage_update=None):
    gemini_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not gemini_key:
        raise RuntimeError("GEMINI_API_KEY isn't set on the server.")
    configure()
    return ac.Agent(
        gemini_key,
        confirm_callback=lambda action, details: True,   # see module docstring, point 4
        on_rate_limit=on_rate_limit,
        groq_api_key=os.environ.get("GROQ_API_KEY", "").strip() or None,
        on_provider_switch=on_provider_switch,
        on_usage_update=on_usage_update,
    )
