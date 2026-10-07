"""
ALPHA 9 — core agent logic (GUI-friendly version).
Modified to use local 'personal_brain' for long-term storage.
Updated: AIRIS (Artificial Intelligence for Robotic Integrating System)
now owns both provider fallback switching and conversation-history
healing/trimming - see the AIRIS class below.
"""

import json
import os
import sys

# Add the local directory to sys.path so we can import personal_brain
sys.path.append(os.path.dirname(__file__))
from personal_brain import brain_manager
from usage_tracker import UsageTracker
import image_search

import base64
import math
import mimetypes
import re
import subprocess
import threading
import time
import urllib.parse
import urllib.request

from openai import OpenAI

# Gemini free-tier quotas are PER MODEL, so this chain runs smartest-first and
# drops to the next model when one runs out for the day. The Flash models have
# a tiny free allowance (~20 requests/day each) and Flash-Lite a big one (~500),
# so Flash-Lite is the safety net at the end. gemini-3.8-flash is the newest
# stable Flash (Sept 2026); it supports function calling.
MODEL = "gemini-3.8-flash"
FALLBACK_MODELS = ["gemini-3.7-flash", "gemini-3.6-flash", "gemini-3.5-flash", "gemini-3.1-flash-lite"]
VISION_MODEL = "gemini-3.1-flash-lite"  # YouTube analysis - kept on the big-allowance model so it never eats the smart models' daily requests
GROQ_MODEL = "openai/gpt-oss-120b"  # Groq's current recommended free-tier flagship (replaces the deprecated llama-3.3-70b-versatile) - text/tools only, no image support
MAX_ATTACHMENTS = 5  # sane ceiling per message - each image adds real token/quota weight, so this isn't just a UI nicety

# Approximate usable context window per provider, for the context meter in
# the GUI. These are published figures, not measured - Karachi's own testing
# has found Gemini's real limits tighter than documented before (hence
# AIRIS), so treat this as a rough indicator, not an exact countdown.
CONTEXT_WINDOW_TOKENS = {
    "gemini": 1_000_000,
    # gpt-oss-120b's real context window is much larger than this, but the
    # free/on_demand Groq tier throttles at 8,000 tokens/minute regardless -
    # that account-level cap is what actually causes failures, so the meter
    # should warn against that, not the model's theoretical capacity. Raise
    # this if the Groq account is ever upgraded off the free tier.
    "groq": 8_000,
}

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
MEMORY_DIR = os.path.join(SCRIPT_DIR, "personal_brain")
MEMORY_FILE = os.path.join(MEMORY_DIR, "memory.json")
USAGE = UsageTracker(os.path.join(MEMORY_DIR, "usage.json"), os.path.join(MEMORY_DIR, "config.json"))
MAX_REMEMBERED_MESSAGES = 40

# None = every tool (desktop ALPHA). A set of tool names restricts the agent to
# just those - used by the cloud build (B.E.T.A.), which must never expose
# file/terminal tools. Enforced both in the schema the model sees AND at
# dispatch, so a hallucinated call to a removed tool still can't run.
ALLOWED_TOOLS = None

SYSTEM_PROMPT = """You are A.L.P.H.A which stands for Advanced Learning Platform and Hybrid Assistant, model 9 in an ongoing personal assistant
lineage, running directly on the user's Linux machine. The user is
running Fedora (KDE Plasma) on a Dell Latitude E5440 laptop with 8gb ram and has a Huawei Honor 8x phone with 6gb ram you are to refer to the user as "Karachi".
"ALPHA" is your name; "9" is your model/version number, not part of an
acronym. You can run shell commands, read files, write files, list
directories, search the web, find and show photos (search_images), watch and analyze YouTube videos, copy
text to the clipboard, and manage long-term memory to help the user
with tasks. Always explain what you're
about to do and why, in plain, simple language, before requesting a tool
call — the user is still learning Linux, so keep explanations clear and
avoid unexplained jargon. Be careful and conservative with destructive
operations (deleting files, partitioning, anything touching /dev/*, or
system-critical config).

Your recent conversation (last ~40 messages) is always visible to you
automatically. For anything further back, or genuinely important facts
worth keeping forever (the user's projects, hardware, preferences, key
decisions), use data.json file in the personal_brain folder to know the facts.
or use any of the files in personal_brain when the user references something from further back than your recent
messages, or asks you to recall something. Be selective about what you
save - routine questions ("what's in this folder?") aren't worth saving;
durable facts about the user, their projects, and their setup are.

When you use web_search, don't just relay the first result you find and
call it done. Search more than once if needed, checking multiple
different websites to see if they actually agree with each other before
presenting something as fact - if sources conflict, say so rather than
picking one arbitrarily. Then explain what you found in your own clear,
simplified words - don't just paste snippets back at the user. Treat
this the way a careful person would: verify before stating something
confidently, especially for anything technical (commands, version
numbers, whether a method is still current).

When the user asks for photos or pictures (or seeing images would clearly help),
use search_images - the photos appear in the chat by themselves, so don't
paste image links. For anything that could show violence, injury, death,
destruction or other distressing scenes (attacks, bombings, wars, accidents,
disasters), set sensitive=true and give a SHORT warning saying what the
photos may show - the app blurs them and shows your warning on each one so
Karachi can decide whether to open them. In your reply, say briefly that
they're blurred and why, mention which sites the photos came from, and
remind him that photos found on the web are often from other dates or other
events - never claim a photo shows the specific event he asked about unless
its source says so. Do your written research with web_search as usual; the
photos are an addition to it, not a replacement.

Some commands require the user's password (via sudo) and you cannot type
a password yourself. For those, use copy_to_clipboard to put the exact
command on the user's clipboard, and tell them to paste it into their
own terminal and enter their password there - don't attempt to run
sudo-requiring commands yourself via run_command, since they'll just
hang waiting for a password you can't provide.
And after pasting the content in clip you are to give feedback
on wether you were successful in pasting in clip.

You can also send emails the using email_helper.py script to send emails for the user."""

BLOCKED_PATTERNS = [
    "rm -rf /",
    "rm -rf /*",
    "mkfs",
    "dd if=",
    "> /dev/sda",
    ":(){:|:&};:",
    "chmod -R 000 /",
    "chown -R",
]

def is_blocked(command: str) -> bool:
    lowered = command.lower().replace(" ", "")
    return any(p.replace(" ", "") in lowered for p in BLOCKED_PATTERNS)

class _ProviderSwitched(Exception):
    """Internal signal only - means 'Gemini's quota ran out, we've already
    switched to the fallback, retry this same request with it.' Never
    surfaced to the user."""
    pass

class AIRIS:
    """AIRIS - Artificial Intelligence for Robotic Integrating System.

    ALPHA's background system-integrity layer. Originally just the
    Gemini <-> Groq provider-switching logic (see Agent._start_airis
    below, which still owns that half since it needs live access to the
    running Agent's state), AIRIS's scope now also covers:

      - heal_history(): repairing corrupted or structurally broken
        conversation JSON (mismatched roles, orphaned tool calls) so a
        bad save never permanently breaks ALPHA's memory.
      - trim_for_provider(): keeping a request's size within whatever
        provider is currently serving it, since Groq's free tier can't
        take the same payload Gemini can.

    Both of these are pure functions (messages in, messages out) so
    they're kept here rather than as Agent methods - nothing about them
    depends on a live agent instance.
    """

    @staticmethod
    def heal_history(messages):
        """Ensures strict adherence to the alternating role sequence,
        without breaking legitimate multi-tool-call turns (which produce
        several consecutive 'tool' messages on purpose - one per tool
        called)."""
        if not messages: return []

        validated = [messages[0]] # Keep the system prompt
        for i in range(1, len(messages)):
            current = messages[i]
            last = validated[-1]

            if current.get("role") == last.get("role") and current.get("role") != "tool":
                # Two user or two assistant turns back-to-back is a real
                # corruption sign - collapse to the newest.
                validated[-1] = current
            else:
                # Consecutive 'tool' messages are valid (multi-tool-call
                # turns) and must all be kept, not collapsed.
                validated.append(current)

        # Guard against dangling turns left at the start of the window after
        # a trim cuts mid-conversation (e.g. a tool_call with no preceding
        # user turn, or assistant commentary that only makes sense following
        # a tool result that's since been trimmed away). A valid conversation
        # must begin with a user turn right after the system prompt - keep
        # stripping leading junk until it does.
        while len(validated) > 1 and validated[1].get("role") != "user":
            entry = validated[1]
            if entry.get("role") == "assistant" and entry.get("tool_calls"):
                # Drop the tool_call and its matching tool response(s) together
                call_ids = {c["id"] for c in entry["tool_calls"]}
                j = 2
                while j < len(validated) and validated[j].get("role") == "tool" and validated[j].get("tool_call_id") in call_ids:
                    j += 1
                validated = [validated[0]] + validated[j:]
            else:
                # Orphaned assistant text or a stray tool response with no
                # matching call - drop just this one entry.
                validated = [validated[0]] + validated[2:]

        return validated

    @staticmethod
    def trim_for_provider(messages, budget_tokens):
        """Keeps a conversation within budget_tokens for whatever provider
        is about to receive it - Groq's free tier caps far lower than
        Gemini's, so the same full history that's fine for Gemini can
        fail outright on Groq. Keeps the system prompt plus as many of
        the most recent messages as fit, then heals the result in case
        the trim boundary orphaned a tool call/response pair."""
        system_msg = messages[0] if messages and messages[0].get("role") == "system" else None
        rest = messages[1:] if system_msg else messages

        # ~4 chars/token is a rough but standard heuristic for English text -
        # no tokenizer dependency needed for a soft safety budget like this.
        budget_chars = budget_tokens * 4
        used = len(str(system_msg.get("content", ""))) if system_msg else 0

        kept = []
        for msg in reversed(rest):
            size = len(str(msg.get("content", ""))) + len(str(msg.get("tool_calls", "")))
            if used + size > budget_chars and kept:
                break
            kept.insert(0, msg)
            used += size

        trimmed = ([system_msg] if system_msg else []) + kept
        return AIRIS.heal_history(trimmed)

def load_memory():
    os.makedirs(MEMORY_DIR, exist_ok=True)
    if os.path.exists(MEMORY_FILE):
        try:
            with open(MEMORY_FILE, "r") as f:
                messages = json.load(f)
        except json.JSONDecodeError:
            os.rename(MEMORY_FILE, MEMORY_FILE + ".corrupted")
            return [{"role": "system", "content": SYSTEM_PROMPT}]

        # HEALING: Validate structure on load
        cleaned = AIRIS.heal_history(messages)
        if not cleaned or cleaned[0].get("role") != "system":
            cleaned.insert(0, {"role": "system", "content": SYSTEM_PROMPT})
        return cleaned
    return [{"role": "system", "content": SYSTEM_PROMPT}]

def save_memory(messages):
    # HEALING: Validate structure before saving
    messages = AIRIS.heal_history(messages)

    system_msgs = [m for m in messages if m.get("role") == "system"]
    rest = [m for m in messages if m.get("role") != "system"]
    budget = max(MAX_REMEMBERED_MESSAGES - len(system_msgs), 0)
    trimmed = system_msgs + rest[-budget:]

    # ATOMIC SAVE: To prevent corruption
    tmp_file = MEMORY_FILE + ".tmp"
    with open(tmp_file, "w") as f:
        json.dump(trimmed, f, indent=2)
    os.replace(tmp_file, MEMORY_FILE)

def load_long_term_memory():
    return brain_manager.load_db().get('facts', [])

def save_long_term_memory_store(entries):
    data = brain_manager.load_db()
    data['facts'] = entries
    brain_manager.save_db(data)


class Agent:
    def __init__(self, api_key, confirm_callback, on_rate_limit=None, groq_api_key=None,
                 on_provider_switch=None, on_usage_update=None, on_model_update=None):
        self.client = OpenAI(
            base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
            api_key=api_key,
            timeout=60.0,  # Gemini 3.x Flash models think before answering (several seconds to first token) - 20s was cutting them off
            max_retries=0,  # we do our own retry logic below - don't double-retry silently
        )
        self.confirm = confirm_callback
        self.on_rate_limit = on_rate_limit
        self.on_provider_switch = on_provider_switch
        self.on_usage_update = on_usage_update
        self.on_model_update = on_model_update
        self._current_on_images = None   # set for the duration of one send() - pushes galleries to the GUI
        self.allowed_image_urls = set()  # full-size image URLs from galleries we showed - the only ones the GUI may fetch
        self.allowed_page_urls = set()   # source pages from those galleries - the only ones the GUI may open
        self.messages = load_memory()
        self._lock = threading.Lock()
        self._api_key = api_key  # kept for the native google-genai client (video understanding isn't documented on the OpenAI-compat layer)

        self.active_provider = "gemini"  # or "groq" while Gemini's daily quota is exhausted
        self._switch_reason = None  # "quota" or "overload" - set whenever active_provider flips to "groq"
        self.groq_client = None
        if groq_api_key:
            self.groq_client = OpenAI(
                base_url="https://api.groq.com/openai/v1",
                api_key=groq_api_key,
                timeout=20.0,
                max_retries=0,
            )
            self._start_airis()

    def _start_airis(self):
        """Starts the live half of AIRIS - the background loop that
        watches over which model ALPHA is currently running on, and
        decides when to switch between Gemini and the Groq fallback. It
        checks every few minutes whether Gemini's daily quota has reset
        while running on the fallback. AIRIS only ever acts when the
        agent is genuinely idle - it needs the same lock send() holds
        while processing a message, so if a conversation is mid-turn it
        simply skips that cycle and tries again later rather than
        interrupting anything.

        This is a method here (not on the AIRIS class above) because it
        needs live access to this running Agent's state - the healing
        and trimming logic doesn't, so that stays in AIRIS as pure
        functions instead."""
        def airis_loop():
            while True:
                time.sleep(300)  # check every 5 minutes
                if self.active_provider != "groq":
                    continue
                if not self._lock.acquire(blocking=False):
                    continue  # agent is busy - AIRIS never switches mid-conversation
                try:
                    # A minimal, throwaway probe - not added to real history -
                    # just to check whether Gemini will accept a request again.
                    # Probe with the LAST (cheapest, biggest-allowance) Gemini
                    # model that still has quota - a ping must never burn one
                    # of the ~20 daily requests of the smart models.
                    candidates = [m for m in [MODEL] + FALLBACK_MODELS if not USAGE.is_exhausted(m)]
                    if not candidates:
                        continue  # every Gemini model is out until the daily reset
                    probe = candidates[-1]
                    self.client.chat.completions.create(
                        model=probe,
                        messages=[{"role": "user", "content": "ping"}],
                    )
                    USAGE.record(probe)
                    self.active_provider = "gemini"
                    self._notify_usage()
                    if self.on_provider_switch:
                        self.on_provider_switch("restored", probe)
                except Exception as e:
                    pass  # still exhausted (or some other transient hiccup) - just try again next cycle
                finally:
                    self._lock.release()
        threading.Thread(target=airis_loop, daemon=True).start()

    def _run_command(self, command, explanation):
        if is_blocked(command):
            return f"BLOCKED: '{command}' matches a hard safety rule and was not run."
        if not self.confirm("run_command", {"command": command, "explanation": explanation}):
            return "User denied this command. Do not attempt it again this session."
        result = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=120)
        output = (result.stdout or "") + (result.stderr or "")
        return output.strip() or "(command ran with no output)"

    @staticmethod
    def _get_youtube_metadata(url):
        """Gemini's video understanding only perceives what's actually IN
        the video (frames + audio) - it has no access to YouTube's page
        metadata, so the real title isn't something it can reliably know
        unless it's spoken or shown on-screen. This pulls the real title
        and channel name from YouTube's public oEmbed endpoint (no API
        key needed) so we can ground the model with facts instead of
        letting it guess."""
        try:
            oembed_url = "https://www.youtube.com/oembed?url=" + urllib.parse.quote(url, safe="") + "&format=json"
            with urllib.request.urlopen(oembed_url, timeout=10) as response:
                data = json.loads(response.read().decode("utf-8"))
            return data.get("title", ""), data.get("author_name", "")
        except Exception:
            return "", ""  # fall back silently - video analysis still works, just without a confirmed title

    def _watch_youtube(self, url, question, explanation):
        if not self.confirm("watch_youtube_video", {"path": url, "explanation": explanation}):
            return "User denied watching this YouTube video."
        if "youtube.com/watch" not in url and "youtu.be/" not in url:
            return "That doesn't look like a valid YouTube video URL."
        try:
            from google import genai
            from google.genai import types
        except ImportError:
            return ("Can't watch YouTube videos yet - the 'google-genai' package "
                     "isn't installed. Run: pip install google-genai")

        real_title, real_channel = self._get_youtube_metadata(url)

        try:
            client = genai.Client(api_key=self._api_key)
            prompt = question or "Describe what happens in this video in detail, including anything important said."
            if real_title:
                prompt = (f"(For reference: this video's actual title is \"{real_title}\", "
                           f"from the channel \"{real_channel}\". Use this exact title if you "
                           f"mention it - don't guess or paraphrase your own.)\n\n{prompt}")
            response = client.models.generate_content(
                model=VISION_MODEL,
                contents=types.Content(parts=[
                    types.Part(text=prompt),
                    types.Part(file_data=types.FileData(file_uri=url)),
                ]),
            )
            USAGE.record(VISION_MODEL)
            self._notify_usage()
            result = response.text or "(no response from video analysis)"
            if real_title:
                result = f'"{real_title}" (by {real_channel})\n\n{result}'
            return result
        except Exception as e:
            return f"Error watching YouTube video: {e}"

    def _read_file(self, path, explanation):
        if not self.confirm("read_file", {"path": path, "explanation": explanation}):
            return "User denied reading this file."
        try:
            with open(os.path.expanduser(path), "r", errors="replace") as f:
                return f.read()[:10000]
        except Exception as e:
            return f"Error reading file: {e}"

    def _write_file(self, path, content, explanation):
        if not self.confirm("write_file", {"path": path, "explanation": explanation}):
            return "User denied writing this file."
        try:
            with open(os.path.expanduser(path), "w") as f:
                f.write(content)
            return f"Successfully wrote to {path}"
        except Exception as e:
            return f"Error writing file: {e}"

    def _list_directory(self, path, explanation):
        if not self.confirm("list_directory", {"path": path, "explanation": explanation}):
            return "User denied listing this directory."
        try:
            entries = os.listdir(os.path.expanduser(path))
            return "\n".join(entries) if entries else "(empty directory)"
        except Exception as e:
            return f"Error listing directory: {e}"

    def _web_search(self, query, explanation):
        if not self.confirm("web_search", {"path": query, "explanation": explanation}):
            return "User denied this web search."
        config_file = os.path.join(MEMORY_DIR, "config.json")
        api_key = None
        if os.path.exists(config_file):
            try:
                with open(config_file, "r") as f:
                    api_key = json.load(f).get("serper_api_key", "")
            except Exception:
                pass
        api_key = api_key or os.environ.get("SERPER_API_KEY", "")
        if not api_key:
            return ("No Serper API key configured. Add 'serper_api_key' to "
                     "personal_brain/config.json, then try again.")
        try:
            url = "https://google.serper.dev/search"
            payload = json.dumps({"q": query, "num": 8}).encode("utf-8")
            req = urllib.request.Request(url, data=payload, headers={
                "X-API-KEY": api_key,
                "Content-Type": "application/json",
            })
            with urllib.request.urlopen(req, timeout=15) as response:
                data = json.loads(response.read().decode("utf-8"))
            results = data.get("organic", [])[:5]
            if not results:
                return "No search results found."
            formatted = []
            for r in results:
                formatted.append(
                    f"- {r.get('title', '')}\n  {r.get('link', '')}\n  {r.get('snippet', '')}"
                )
            return "\n\n".join(formatted)
        except Exception as e:
            return f"Web search error: {e}"

    def _search_images(self, query, explanation, sensitive=False, warning="", count=6):
        if not self.confirm("search_images", {"path": query, "explanation": explanation}):
            return "User denied this image search."
        config_file = os.path.join(MEMORY_DIR, "config.json")
        api_key = None
        if os.path.exists(config_file):
            try:
                with open(config_file, "r") as f:
                    api_key = json.load(f).get("serper_api_key", "")
            except Exception:
                pass
        api_key = api_key or os.environ.get("SERPER_API_KEY", "")
        if not api_key:
            return ("No Serper API key configured. Add 'serper_api_key' to "
                    "personal_brain/config.json, then try again.")
        try:
            results = image_search.search_serper_images(api_key, query, count)
            if not results:
                return "No images found for that search."
            tiles = image_search.build_gallery(results, want=count)
        except Exception as e:
            return f"Image search error: {e}"
        if not tiles:
            return "Found image results, but none of them could be downloaded safely. Try different search terms."

        blur, reason = image_search.decide_blur(query, sensitive, warning)
        for t in tiles:
            if t["full_url"]:
                self.allowed_image_urls.add(t["full_url"])
            if t["page_url"]:
                self.allowed_page_urls.add(t["page_url"])

        payload = {"query": query, "blurred": blur, "reason": reason, "images": tiles}
        if self._current_on_images:
            try:
                self._current_on_images(payload)
            except Exception as e:
                print(f"[ALPHA] Could not show image gallery: {e}")

        lines = [f"Showed {len(tiles)} photo(s) for \"{query}\" to Karachi in a gallery in the chat."]
        if blur:
            lines.append(f"They are BLURRED until he clicks each one, with this note on every image: \"{reason}\". "
                         "Tell him briefly in your reply that they're blurred and why, so he can decide whether to open them.")
        lines.append("Sources: " + "; ".join(
            f"{t['title'] or 'untitled'} ({t['source'] or 'unknown site'})" for t in tiles))
        lines.append("Remind him that photos found on the web are often from other dates or other events - "
                     "don't claim any of them shows the specific event unless its source says so.")
        return "\n".join(lines)

    def _save_long_term_memory(self, text, explanation):
        if not self.confirm("save_long_term_memory", {"path": text, "explanation": explanation}):
            return "User denied saving this to long-term memory."
        try:
            # Use brain_manager.add_fact() rather than appending a raw string -
            # entries are {content, tags, timestamp, importance_score} objects
            # since the migration in brain_manager.load_db(). Appending a bare
            # string here mixed types in the same list and silently broke
            # search_facts()/the memory panel for anything saved this way.
            brain_manager.add_fact(text)
            return "Saved to long-term memory."
        except Exception as e:
            return f"Error saving long-term memory: {e}"

    def _search_long_term_memory(self, query, explanation):
        try:
            # brain_manager.search_facts() already does keyword + fuzzy
            # matching against the real object format - the old isinstance(e,
            # str) filter here never matched anything post-migration.
            matches = brain_manager.search_facts(query)
            if not matches:
                return "No relevant long-term memories found for that."
            return "\n".join(f"- {m}" for m in matches)
        except Exception as e:
            return f"Error searching long-term memory: {e}"

    def _send_email(self, recipient, subject, body, explanation):
        if not self.confirm("send_email", {"path": f"To: {recipient} / Subject: {subject}", "explanation": explanation}):
            return "User denied sending this email."
        try:
            try:
                from personal_brain import email_helper
            except ImportError:
                import email_helper
        except ImportError as e:
            return f"Could not find email_helper.py to send this email: {e}"
        try:
            email_helper.send_email(recipient, subject, body)
            return f"Email sent to {recipient}."
        except Exception as e:
            return f"Error sending email: {e}"

    def _copy_to_clipboard(self, text, explanation):
        if not self.confirm("copy_to_clipboard", {"path": text, "explanation": explanation}):
            return "User denied copying this to clipboard."
        try:
            try:
                subprocess.run(["wl-copy"], input=text, text=True, check=True, capture_output=True)
            except (FileNotFoundError, subprocess.CalledProcessError):
                subprocess.run(["xclip", "-selection", "clipboard"], input=text,
                                text=True, check=True, capture_output=True)
            return "Copied to clipboard. Paste it into your own terminal and enter your password there."
        except Exception as e:
            return (f"Could not copy to clipboard automatically ({e}). "
                    f"Here's the exact text to copy yourself:\n\n{text}")

    def _tools_schema(self):
        tools = self._all_tools_schema()
        if ALLOWED_TOOLS is not None:
            tools = [t for t in tools if t["function"]["name"] in ALLOWED_TOOLS]
        return tools

    def _all_tools_schema(self):
        return [
            {"type": "function", "function": {
                "name": "run_command",
                "description": "Run a shell command on the user's Linux machine.",
                "parameters": {"type": "object", "properties": {
                    "command": {"type": "string"}, "explanation": {"type": "string"}},
                    "required": ["command", "explanation"]}}},
            {"type": "function", "function": {
                "name": "read_file",
                "description": "Read the contents of a file.",
                "parameters": {"type": "object", "properties": {
                    "path": {"type": "string"}, "explanation": {"type": "string"}},
                    "required": ["path", "explanation"]}}},
            {"type": "function", "function": {
                "name": "write_file",
                "description": "Write content to a file (creates or overwrites it).",
                "parameters": {"type": "object", "properties": {
                    "path": {"type": "string"}, "content": {"type": "string"},
                    "explanation": {"type": "string"}},
                    "required": ["path", "content", "explanation"]}}},
            {"type": "function", "function": {
                "name": "list_directory",
                "description": "List the contents of a directory.",
                "parameters": {"type": "object", "properties": {
                    "path": {"type": "string"}, "explanation": {"type": "string"}},
                    "required": ["path", "explanation"]}}},
            {"type": "function", "function": {
                "name": "watch_youtube_video",
                "description": "Watch and analyze a YouTube video - understands both the visuals and the audio. Use when the user shares a YouTube link and wants a summary, wants to know what's in it, or has a specific question about its content.",
                "parameters": {"type": "object", "properties": {
                    "url": {"type": "string", "description": "The YouTube video URL"},
                    "question": {"type": "string", "description": "What to find out about the video, e.g. 'summarize this' or 'what does the presenter say about X'"},
                    "explanation": {"type": "string"}},
                    "required": ["url", "question", "explanation"]}}},
            {"type": "function", "function": {
                "name": "web_search",
                "description": "Search the web for current information.",
                "parameters": {"type": "object", "properties": {
                    "query": {"type": "string"}, "explanation": {"type": "string"}},
                    "required": ["query", "explanation"]}}},
            {"type": "function", "function": {
                "name": "search_images",
                "description": ("Find photos on the web and show them to the user as a gallery inside the chat. "
                                "Use when the user asks for photos/pictures/images, or when seeing images would clearly help. "
                                "If the photos could show violence, injury, death, destruction, disasters or other disturbing "
                                "scenes, set sensitive=true and give a short warning saying what they may show."),
                "parameters": {"type": "object", "properties": {
                    "query": {"type": "string"},
                    "explanation": {"type": "string"},
                    "sensitive": {"type": "boolean", "description": "true if the photos may be graphic or distressing"},
                    "warning": {"type": "string", "description": "Max ~12 words, plain language, e.g. 'may show bomb damage and victims'. Shown on each blurred photo."},
                    "count": {"type": "integer", "description": "How many photos, 1-8 (default 6)"}},
                    "required": ["query", "explanation"]}}},
            {"type": "function", "function": {
                "name": "save_long_term_memory",
                "description": "Save a durable fact worth remembering forever - e.g. user preferences, project details, key decisions.",
                "parameters": {"type": "object", "properties": {
                    "text": {"type": "string", "description": "The fact to remember, written clearly and self-contained"},
                    "explanation": {"type": "string"}},
                    "required": ["text", "explanation"]}}},
            {"type": "function", "function": {
                "name": "search_long_term_memory",
                "description": "Search long-term memory for something from further back than the recent conversation, or when the user asks you to recall something.",
                "parameters": {"type": "object", "properties": {
                    "query": {"type": "string"}, "explanation": {"type": "string"}},
                    "required": ["query", "explanation"]}}},
            {"type": "function", "function": {
                "name": "copy_to_clipboard",
                "description": "Copy text (usually a command that needs sudo/a password) to the user's clipboard, since you can't type a password yourself.",
                "parameters": {"type": "object", "properties": {
                    "text": {"type": "string"}, "explanation": {"type": "string"}},
                    "required": ["text", "explanation"]}}},
            {"type": "function", "function": {
                "name": "send_email",
                "description": "Send an email on the user's behalf using their configured Gmail account.",
                "parameters": {"type": "object", "properties": {
                    "recipient": {"type": "string"}, "subject": {"type": "string"},
                    "body": {"type": "string"}, "explanation": {"type": "string"}},
                    "required": ["recipient", "subject", "body", "explanation"]}}},
        ]

    DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

    @staticmethod
    def _extract_docx_text(path):
        """.docx is a zipped bundle of XML, not plain text or an image -
        python-docx unzips it and pulls out the real paragraph/table text."""
        try:
            import docx
        except ImportError:
            return ("[Can't read this .docx file - the 'python-docx' package "
                     "isn't installed. Run: pip install python-docx]")
        try:
            document = docx.Document(os.path.expanduser(path))
            parts = [p.text for p in document.paragraphs if p.text.strip()]
            for table in document.tables:
                for row in table.rows:
                    parts.append(" | ".join(cell.text for cell in row.cells))
            return "\n".join(parts)[:10000]
        except Exception as e:
            return f"[Error reading .docx file: {e}]"

    @staticmethod
    def _is_text_attachment(path):
        """Plain text files (.txt, .md, code, .json, etc.) make no sense
        sent as an image_url - there's nothing to 'look at'. This tells
        _send_locked when to read a file as real text instead."""
        mime_type, _ = mimetypes.guess_type(path)
        if not mime_type:
            return False
        return mime_type.startswith("text/") or mime_type in (
            "application/json", "application/xml", "application/x-yaml", "application/x-sh",
        )

    @staticmethod
    def _encode_image(image_path):
        mime_type, _ = mimetypes.guess_type(image_path)
        mime_type = mime_type or "image/png"
        with open(os.path.expanduser(image_path), "rb") as f:
            encoded = base64.b64encode(f.read()).decode("utf-8")
        return f"data:{mime_type};base64,{encoded}"

    @staticmethod
    def _describe_tool_call(func_name, args):
        """Human-readable one-liner for the GUI's tool activity feed -
        kept here since this is the one place that already knows each
        tool's argument shape."""
        if func_name == "run_command":
            return f"Running: {args.get('command', '')}"
        if func_name == "read_file":
            return f"Reading file — {args.get('path', '')}"
        if func_name == "write_file":
            return f"Writing file — {args.get('path', '')}"
        if func_name == "list_directory":
            return f"Listing directory — {args.get('path', '')}"
        if func_name == "web_search":
            return f'Running web search — "{args.get("query", "")}"'
        if func_name == "search_images":
            return f'Searching for images — "{args.get("query", "")}"'
        if func_name == "watch_youtube_video":
            return f"Watching YouTube video — {args.get('url', '')}"
        if func_name == "save_long_term_memory":
            return "Saving to long-term memory"
        if func_name == "search_long_term_memory":
            return f'Searching long-term memory — "{args.get("query", "")}"'
        if func_name == "copy_to_clipboard":
            return "Copying to clipboard"
        if func_name == "send_email":
            return f"Sending email to {args.get('recipient', '')}"
        return f"Running {func_name}"

    def _refresh_system_prompt(self):
        system_msg = {"role": "system", "content": SYSTEM_PROMPT}
        if self.messages and self.messages[0].get("role") == "system":
            self.messages[0] = system_msg
        else:
            self.messages.insert(0, system_msg)

    def send(self, user_text, image_paths=None, on_tool_result=None, on_images=None):
        with self._lock:
            self._current_on_images = on_images
            try:
                return self._send_locked(user_text, image_paths=image_paths, on_tool_result=on_tool_result)
            finally:
                self._current_on_images = None

    def _needs_vision(self, path):
        """True only for attachments that actually have to be *looked at* -
        real images and PDFs. Text files and .docx get converted to plain
        text before they ever reach the model, so they have nothing to do
        with vision capability and work fine even on a text-only fallback."""
        mime_type, _ = mimetypes.guess_type(path)
        if mime_type == self.DOCX_MIME or self._is_text_attachment(path):
            return False
        return True

    def _send_locked(self, user_text, image_paths=None, on_tool_result=None):
        if image_paths and self.active_provider == "groq":
            vision_files = [os.path.basename(p) for p in image_paths if self._needs_vision(p)]
            if vision_files:
                # Backend safety net - the GUI is supposed to block this
                # before it ever gets here, but never trust the frontend
                # as the only guard. Only genuine images/PDFs are the
                # problem here - text files and .docx don't need vision
                # at all, so this only blocks when one of those is present.
                names = ", ".join(vision_files)
                return (f"Can't process {names} right now - Gemini's daily "
                        "limit is temporarily used up, so ALPHA is running "
                        "on a text-only fallback model that can't see "
                        "images or PDFs. Resend without those, or wait for "
                        "Gemini to be restored.")

        if image_paths and len(image_paths) > MAX_ATTACHMENTS:
            # Reject clearly rather than silently sending only the first few -
            # a silently-truncated attachment set is a worse surprise than
            # just being told the limit up front.
            return (f"That's {len(image_paths)} files - ALPHA accepts up to "
                     f"{MAX_ATTACHMENTS} attachments per message (more than "
                     "that burns through a lot of quota at once). Try "
                     "sending them in a couple of smaller batches instead.")

        if image_paths:
            content = [{"type": "text", "text": user_text}]
            for path in image_paths:
                filename = os.path.basename(path)
                mime_type, _ = mimetypes.guess_type(path)
                if mime_type == self.DOCX_MIME:
                    doc_text = self._extract_docx_text(path)
                    content[0]["text"] += (
                        f"\n\n--- Attached file: {filename} ---\n"
                        f"{doc_text}\n--- End of {filename} ---"
                    )
                elif self._is_text_attachment(path):
                    # A text file isn't something to "look at" - read its
                    # real content and inline it as text, same cap as the
                    # read_file tool uses, rather than mislabeling it as
                    # an image the model can't actually understand.
                    try:
                        with open(os.path.expanduser(path), "r", errors="replace") as f:
                            file_text = f.read()[:10000]
                        content[0]["text"] += (
                            f"\n\n--- Attached file: {filename} ---\n"
                            f"{file_text}\n--- End of {filename} ---"
                        )
                    except Exception as e:
                        content[0]["text"] += f"\n\n[Could not read attached file {filename}: {e}]"
                else:
                    # Images and PDFs both genuinely work through this path -
                    # Gemini reads PDFs the same way it reads images.
                    content.append({"type": "image_url", "image_url": {"url": self._encode_image(path)}})
        else:
            content = user_text

        self._refresh_system_prompt()
        self.messages.append({"role": "user", "content": content})

        tool_funcs = {
            "run_command": self._run_command,
            "read_file": self._read_file,
            "write_file": self._write_file,
            "list_directory": self._list_directory,
            "web_search": self._web_search,
            "search_images": self._search_images,
            "watch_youtube_video": self._watch_youtube,
            "save_long_term_memory": self._save_long_term_memory,
            "search_long_term_memory": self._search_long_term_memory,
            "copy_to_clipboard": self._copy_to_clipboard,
            "send_email": self._send_email,
        }
        if ALLOWED_TOOLS is not None:
            tool_funcs = {k: v for k, v in tool_funcs.items() if k in ALLOWED_TOOLS}

        while True:
            try:
                response, model_id = self._call_with_fallback()
            except _ProviderSwitched:
                continue  # Gemini's out for today - we've switched to the fallback, try again immediately

            if self.on_model_update:
                self.on_model_update(self.active_provider, model_id)

            USAGE.record(model_id)  # one successful request against this model's daily quota
            self._notify_usage()

            msg = response.choices[0].message

            if not msg.content and not msg.tool_calls:
                # If we get an empty response, don't leave the user hanging
                if self.messages and self.messages[-1].get("role") == "user":
                    self.messages.pop()
                raise RuntimeError("Empty response received from AI - please try again.")

            # Record assistant action
            clean_msg = {"role": "assistant"}
            if msg.content: clean_msg["content"] = msg.content
            if msg.tool_calls:
                clean_msg["tool_calls"] = [c.model_dump(exclude_none=True) for c in msg.tool_calls]
            self.messages.append(clean_msg)

            if not msg.tool_calls:
                save_memory(self.messages)
                return msg.content

            # Process all tool calls
            for call in msg.tool_calls:
                func_name = call.function.name
                try:
                    args = json.loads(call.function.arguments)
                    if on_tool_result:
                        on_tool_result(self._describe_tool_call(func_name, args))
                    func = tool_funcs.get(func_name)
                    result = func(**args) if func else f"Unknown tool: {func_name}"
                except Exception as e:
                    result = f"Error running {func_name}: {e}"

                self.messages.append({
                    "role": "tool",
                    "tool_call_id": call.id,
                    "name": func_name,
                    "content": str(result),
                })

    def usage_snapshot(self):
        """Everything the GUI's requests-left meter needs, in one dict."""
        chain = [MODEL] + FALLBACK_MODELS
        if self.active_provider == "groq" and self.groq_client:
            provider, active = "groq", GROQ_MODEL
        else:
            # The model the NEXT request will go to: first one with quota left.
            provider = "gemini"
            active = next((m for m in chain if not USAGE.is_exhausted(m)), chain[-1])
        models = [dict(USAGE.entry(m), provider="gemini") for m in chain]
        if self.groq_client:
            models.append(dict(USAGE.entry(GROQ_MODEL), provider="groq"))
        return {
            "provider": provider,
            "active": active,
            "models": models,
            "resets_in": USAGE.seconds_until_reset(),
        }

    def _notify_usage(self):
        if self.on_usage_update:
            try:
                self.on_usage_update(self.usage_snapshot())
            except Exception:
                pass  # a GUI hiccup must never break a reply

    def _current_client_and_models(self):
        if self.active_provider == "groq" and self.groq_client:
            return self.groq_client, [GROQ_MODEL]
        return self.client, [MODEL] + FALLBACK_MODELS

    # Groq's free/on_demand tier throttles at 8,000 tokens/minute TOTAL
    # (input + output combined) - far below what a real conversation with
    # Gemini needs. Budget conservatively so there's room left for the
    # actual reply, not just the prompt.
    GROQ_SAFE_INPUT_TOKENS = 5000

    def _messages_for_request(self):
        """Full history for Gemini. For Groq, delegate to AIRIS to trim
        down to a safe token budget instead of sending everything and
        failing on every single request."""
        if self.active_provider != "groq":
            return self.messages
        return AIRIS.trim_for_provider(self.messages, self.GROQ_SAFE_INPUT_TOKENS)

    def _call_with_fallback(self):
        client, models_to_try = self._current_client_and_models()
        errors = []
        for model_id in models_to_try:
            if self.active_provider == "gemini" and USAGE.is_exhausted(model_id):
                continue  # already known to be out for today - don't waste a call finding out again
            attempt = 0
            while attempt < 2:  # one retry max for a genuinely transient blip
                attempt += 1
                try:
                    response = client.chat.completions.create(
                        model=model_id,
                        messages=self._messages_for_request(),
                        tools=self._tools_schema(),
                    )
                    return response, model_id
                except Exception as e:
                    text = str(e)
                    if self.active_provider == "gemini" and self._is_daily_quota_exhausted(text):
                        # Gemini quotas are per MODEL: this one is done for the
                        # day, but the next model in the chain has its own
                        # allowance. Only when EVERY Gemini model is out do we
                        # hand off to Groq (checked after the loop).
                        USAGE.mark_exhausted(model_id)
                        self._notify_usage()
                        break
                    wait_seconds = self._extract_retry_delay(text)
                    if wait_seconds is not None and wait_seconds <= 30 and attempt < 2:
                        # A short, genuinely temporary rate limit - worth
                        # one quick retry. Anything longer than 30s isn't
                        # worth silently sleeping through; move on instead.
                        if self.on_rate_limit:
                            self.on_rate_limit(wait_seconds)
                        time.sleep(wait_seconds)
                        continue
                    errors.append(f"[{model_id}] {e}")
                    break
        if self.active_provider == "gemini" and all(USAGE.is_exhausted(m) for m in models_to_try):
            if self.groq_client:
                # Don't just fail - hand off to the fallback and let the
                # caller retry immediately with it.
                self.active_provider = "groq"
                self._switch_reason = "quota"
                self._notify_usage()
                if self.on_provider_switch:
                    self.on_provider_switch("switched", GROQ_MODEL, reason="quota")
                raise _ProviderSwitched()
            # No fallback configured - fail clearly.
            raise RuntimeError(
                "Every Gemini model has used up its daily quota. "
                "This resets at midnight Pacific time - no need to keep "
                "retrying right now."
            )

        combined = "\n\n".join(errors)
        if self.active_provider == "groq":
            why = ("Gemini's daily limit was reached" if self._switch_reason == "quota"
                   else "Gemini's servers were overloaded")
            is_auth_error = any(
                "401" in e or "invalid_api_key" in e.lower() for e in errors
            )
            if is_auth_error:
                advice = ("This is an auth failure, not a temporary outage - retrying "
                           "won't help. Check that GROQ_API_KEY in personal_brain/config.json "
                           "is current and active at console.groq.com.")
            else:
                advice = "Both are unavailable right now - try again in a few minutes."
            raise RuntimeError(
                f"AIRIS already switched ALPHA to the Groq fallback because "
                f"{why}, but the fallback just failed too:\n\n{combined}\n\n{advice}"
            )

        # Every Gemini model in the chain failed - if it was all transient
        # overload (503, "high demand") rather than quota exhaustion, that's
        # still worth falling back to Groq for: Gemini being overloaded says
        # nothing about how much of the day's quota is left. Only do this
        # once the whole chain has failed, not on the first model's hiccup -
        # the chain itself is already a soft retry.
        if self.groq_client and errors and all(self._is_transient_overload(e) for e in errors):
            self.active_provider = "groq"
            self._switch_reason = "overload"
            if self.on_provider_switch:
                self.on_provider_switch("switched", GROQ_MODEL, reason="overload")
            raise _ProviderSwitched()

        raise RuntimeError(f"All models failed:\n\n{combined}")

    @staticmethod
    def _is_daily_quota_exhausted(error_text):
        """
        Distinguishes 'you're out of requests for the whole day' from a
        brief per-minute rate limit. Google's quota errors mention the
        specific limit that was hit - a per-day limit means retrying (even
        with a fallback model on the same key) can't possibly succeed
        until it resets, so there's no point burning more attempts on it.
        """
        lowered = error_text.lower()
        if "429" not in error_text and "resource_exhausted" not in lowered:
            return False
        return "per_day" in lowered or "perday" in lowered or "daily" in lowered

    @staticmethod
    def _is_transient_overload(error_text):
        """Google's 'model is currently experiencing high demand' error -
        a 503, not a 429. Distinct from quota exhaustion: this says nothing
        about how much of the day's quota is left, it's the server being
        busy right now, so it's worth an immediate Groq fallback rather
        than failing outright."""
        lowered = error_text.lower()
        return "503" in error_text and (
            "unavailable" in lowered or "overloaded" in lowered or "high demand" in lowered
        )

    @staticmethod
    def _extract_retry_delay(error_text):
        """Returns the number of seconds Google's API says to wait before
        retrying, if this error is a rate limit (429) with that info -
        otherwise returns None."""
        if "429" not in error_text and "RESOURCE_EXHAUSTED" not in error_text:
            return None
        match = re.search(r"'retryDelay':\s*'(\d+)s'", error_text)
        if match:
            return int(match.group(1))
        return 20  # sensible fallback if we can't parse the exact delay
