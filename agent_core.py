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
# so Flash-Lite is the safety net at the end. gemini-3.1-flash-lite is chosen
# as the main model here because of its high quota allowance and fast latency.
MODEL = "gemini-3.1-flash-lite"
FALLBACK_MODELS = ["gemini-3.8-flash", "gemini-3.7-flash", "gemini-3.6-flash", "gemini-3.5-flash"]
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
                validated.pop(1)

        return validated

    @staticmethod
    def trim_for_provider(messages, max_tokens):
        """Prunes conversation history from the top down (leaving system-prompt
        and newest turns intact) until it fits within max_tokens. Simple
        character-heuristic approximation (1 token ≈ 4 characters)."""
        system = messages[0]
        history = messages[1:]
        sys_len = len(json.dumps(system)) // 4

        while history:
            tot = sys_len + (len(json.dumps(history)) // 4)
            if tot <= max_tokens or len(history) <= 1:
                break
            # Remove oldest turn. If it's assistant with tool results, remove both.
            entry = history[0]
            if entry.get("role") == "assistant" and entry.get("tool_calls"):
                call_ids = {c["id"] for c in entry["tool_calls"]}
                history.pop(0)
                while history and history[0].get("role") == "tool" and history[0].get("tool_call_id") in call_ids:
                    history.pop(0)
            else:
                history.pop(0)

        # Ensure history still starts with user-turn after top pruning
        while history and history[0].get("role") != "user":
            history.pop(0)

        return [system] + history


class Agent:
    def __init__(self, output_callback=None, tool_callback=None, progress_callback=None):
        self.output_callback = output_callback
        self.tool_callback = tool_callback
        self.progress_callback = progress_callback

        self.messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        self.active_provider = "gemini"  # or "groq" while Gemini's daily quota is exhausted
        self._current_job_id = None
        self._cancel_flag = False

        # Build tools registry
        self.tools_registry = {}
        for name in dir(self):
            if name.startswith("tool_"):
                self.tools_registry[name[5:]] = getattr(self, name)

        # Sync from storage
        self.load_history()

        # Init SDK Clients using our system environment
        # Both endpoints point to OpenAI-compatible wrappers so one client pattern rules both
        gemini_key = os.environ.get("GEMINI_API_KEY", "").strip()
        groq_key = os.environ.get("GROQ_API_KEY", "").strip()

        self.gemini_client = OpenAI(
            api_key=gemini_key if gemini_key else "missing",
            base_url="https://generativelanguage.googleapis.com/v1beta/openai/"
        )
        self.groq_client = OpenAI(
            api_key=groq_key if groq_key else "missing",
            base_url="https://api.groq.com/openai/v1"
        )

    def load_history(self):
        try:
            data = storage.STORE.get("conversation_memory")
            if data and isinstance(data, list):
                # Put the live system prompt at index 0, then import the saved history
                self.messages = [{"role": "system", "content": SYSTEM_PROMPT}] + data
                self.messages = AIRIS.heal_history(self.messages)
        except Exception as e:
            self.log(f"Failed loading history: {e}")

    def save_history(self):
        try:
            # We save ONLY the conversational turns (omitting index 0 system prompt)
            # keeping history trimmed to the cloud limit.
            history = self.messages[1:]
            if len(history) > MAX_REMEMBERED_MESSAGES:
                history = AIRIS.trim_for_provider([self.messages[0]] + history, CONTEXT_WINDOW_TOKENS["gemini"])[1:]
            storage.STORE.set("conversation_memory", history)
            storage.STORE.flush()
        except Exception as e:
            self.log(f"Failed saving history: {e}")

    def log(self, text, flush=True):
        if self.output_callback:
            self.output_callback(text + ("\n" if flush else ""))
        else:
            print(text, end="\n" if flush else "", flush=True)

    def clear_chat(self):
        self.messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        self.save_history()
        self.log("[B.E.T.A.] Chat cleared.")

    # -- AIRIS switching & client request dispatch ----------------------
    def _is_daily_quota_exhausted(self, error_message: str) -> bool:
        """Determines if a returned SDK error is a daily quota depletion."""
        msg = error_message.lower()
        # "ResourceExhausted" (429) can mean rate limit OR daily quota limit.
        # Rates reset in seconds; daily resets at Pacific Midnight.
        # Standard indicators for daily block:
        return "quota" in msg or "daily" in msg or "exhausted" in msg

    def _start_airis(self, models_to_try, messages, active_tool_schemas):
        """AIRIS live dispatch loop. Attempts our model stack one-by-one.
        If a daily quota exception is raised, it marks that model exhausted
        and cascades to the next. If all Gemini options fail, it flips
        provider to Groq."""
        last_err = None

        if self.active_provider == "gemini":
            for model_id in models_to_try:
                if USAGE.is_exhausted(model_id):
                    continue

                self.log(f"[AIRIS] Directing request to {model_id}...", flush=True)
                try:
                    # Render the payload
                    response = self.gemini_client.chat.completions.create(
                        model=model_id,
                        messages=messages,
                        tools=active_tool_schemas if active_tool_schemas else None,
                        temperature=0.2,
                    )
                    # Success -> record metrics and return
                    USAGE.record(model_id)
                    return response, model_id
                except Exception as e:
                    err_text = str(e)
                    self.log(f"[AIRIS] {model_id} failed: {err_text}")
                    if self._is_daily_quota_exhausted(err_text):
                        self.log(f"[AIRIS] Daily limit hit. Marking {model_id} as exhausted.")
                        USAGE.mark_exhausted(model_id)
                    last_err = e

            # If we reached here, Gemini tier is completely down or exhausted.
            self.log("[AIRIS] Gemini service exhausted. Switching active provider to GROQ.")
            self.active_provider = "groq"

        if self.active_provider == "groq":
            self.log(f"[AIRIS] Directing request to {GROQ_MODEL} on Groq...", flush=True)
            # Crop the messages to fit Groq context budget
            groq_messages = AIRIS.trim_for_provider(messages, CONTEXT_WINDOW_TOKENS["groq"])
            try:
                response = self.groq_client.chat.completions.create(
                    model=GROQ_MODEL,
                    messages=groq_messages,
                    tools=active_tool_schemas if active_tool_schemas else None,
                    temperature=0.2,
                )
                USAGE.record(GROQ_MODEL)
                return response, GROQ_MODEL
            except Exception as e:
                self.log(f"[AIRIS] Groq fallback failed: {e}")
                last_err = e

        raise last_err if last_err else RuntimeError("All providers unavailable")

    # -- execution loop --------------------------------------------------
    def send(self, prompt: str, attachments=None, job_id=None):
        """Main non-blocking execution block."""
        self._current_job_id = job_id
        self._cancel_flag = False

        if attachments:
            content_nodes = [{"type": "text", "text": prompt}]
            for path in attachments:
                # Resolve MIME
                mime, _ = mimetypes.guess_type(path)
                if not mime: mime = "application/octet-stream"

                try:
                    with open(path, "rb") as f:
                        b64_data = base64.b64encode(f.read()).decode("utf-8")
                    content_nodes.append({
                        "type": "image_url",
                        "image_url": {"url": f"data:{mime};base64,{b64_data}"}
                    })
                except Exception as e:
                    self.log(f"[B.E.T.A.] Failed reading attachment {os.path.basename(path)}: {e}")
            self.messages.append({"role": "user", "content": content_nodes})
        else:
            self.messages.append({"role": "user", "content": prompt})

        # Keep a copy of tools filtered to our ALLOWED_TOOLS list
        active_tool_schemas = []
        for name, fn in self.tools_registry.items():
            if ALLOWED_TOOLS is None or name in ALLOWED_TOOLS:
                doc = fn.__doc__ or ""
                # Parse docstring for schema definition
                schema_block = {}
                for line in doc.splitlines():
                    if line.strip().startswith("SCHEMA:"):
                        try:
                            schema_block = json.loads(line.replace("SCHEMA:", ""))
                        except Exception:
                            pass
                if schema_block:
                    active_tool_schemas.append(schema_block)

        # Loop processing model-tool cycles
        max_turns = 10
        chain = [MODEL] + FALLBACK_MODELS

        for turn in range(max_turns):
            if self._cancel_flag:
                self.log("[B.E.T.A.] Operation cancelled by user.")
                break

            try:
                # Dispatch query using active providers
                response, model_used = self._start_airis(chain, self.messages, active_tool_schemas)
                choice = response.choices[0]
                msg = choice.message
                tool_calls = msg.tool_calls

                # Append assistant thoughts/tool-requests
                assistant_record = {"role": "assistant"}
                if msg.content:
                    assistant_record["content"] = msg.content
                if tool_calls:
                    # Standardize tool call records
                    tc_list = []
                    for tc in tool_calls:
                        tc_list.append({
                            "id": tc.id,
                            "type": "function",
                            "function": {"name": tc.function.name, "arguments": tc.function.arguments}
                        })
                    assistant_record["tool_calls"] = tc_list

                self.messages.append(assistant_record)

                if msg.content:
                    self.log(msg.content, flush=True)

                if not tool_calls:
                    # Final turn response is reached
                    break

                # Execute requested tools
                for tc in tool_calls:
                    if self._cancel_flag:
                        break

                    name = tc.function.name
                    args_text = tc.function.arguments or "{}"
                    try:
                        args = json.loads(args_text)
                    except Exception:
                        args = {}

                    self.log(f"\n[Tool Request] Calling tool '{name}' with arguments: {args_text}")
                    if ALLOWED_TOOLS is not None and name not in ALLOWED_TOOLS:
                        # Safety override check
                        out = f"Error: Tool '{name}' is not allowed in this environment."
                    elif name in self.tools_registry:
                        try:
                            # Invoke tool
                            out = self.tools_registry[name](**args)
                        except Exception as e:
                            out = f"Error executing tool: {e}"
                    else:
                        out = f"Error: Unknown tool '{name}'."

                    self.messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "name": name,
                        "content": str(out)
                    })

                    # Display truncated tool results in client callback
                    display_out = str(out)
                    if len(display_out) > 500:
                        display_out = display_out[:500] + "\n...[truncated]..."
                    self.log(f"[Tool Response] Result: {display_out}\n")

            except Exception as e:
                self.log(f"\n[B.E.T.A.] Critical failure: {e}")
                # Remove final user prompt on failure so we don't pollute the retry history
                if self.messages and self.messages[-1]["role"] == "user":
                    self.messages.pop()
                break

        # Save history upon healthy loop completion
        self.save_history()
        self._current_job_id = None

    def cancel(self):
        self._cancel_flag = True

    # -- tools definitions -----------------------------------------------
    def tool_web_search(self, query: str) -> str:
        """Runs a web search using Serper API.
        SCHEMA:{"type":"function","function":{"name":"web_search","description":"Search the web for current information.","parameters":{"type":"OBJECT","properties":{"query":{"type":"STRING"}},"required":["query"]}}}"""
        if self.tool_callback:
            self.tool_callback("web_search", {"query": query})
        return image_search.web_search(query)

    def tool_search_images(self, query: str, count: int = 6, sensitive: bool = False, warning: str = "") -> str:
        """Finds photos on the web.
        SCHEMA:{"type":"function","function":{"name":"search_images","description":"Find photos on the web and show them to the user.","parameters":{"type":"OBJECT","properties":{"query":{"type":"STRING"},"count":{"type":"INTEGER"},"sensitive":{"type":"BOOLEAN"},"warning":{"type":"STRING"}},"required":["query"]}}}"""
        if self.tool_callback:
            self.tool_callback("search_images", {"query": query, "count": count, "sensitive": sensitive, "warning": warning})
        return f"Image search completed for: {query}"

    def tool_watch_youtube_video(self, url: str, question: str) -> str:
        """Watch and analyze a YouTube video.
        SCHEMA:{"type":"function","function":{"name":"watch_youtube_video","description":"Watch and analyze a YouTube video.","parameters":{"type":"OBJECT","properties":{"url":{"type":"STRING"},"question":{"type":"STRING"}},"required":["url","question"]}}}"""
        if self.tool_callback:
            self.tool_callback("watch_youtube_video", {"url": url, "question": question})
        return image_search.watch_youtube_video(url, question)

    def tool_save_long_term_memory(self, text: str) -> str:
        """Save a durable fact worth remembering forever.
        SCHEMA:{"type":"function","function":{"name":"save_long_term_memory","description":"Save a durable fact worth remembering forever.","parameters":{"type":"OBJECT","properties":{"text":{"type":"STRING"}},"required":["text"]}}}"""
        brain_manager.save_memory(text)
        return "Fact saved successfully."

    def tool_search_long_term_memory(self, query: str) -> str:
        """Search long-term memory.
        SCHEMA:{"type":"function","function":{"name":"search_long_term_memory","description":"Search long-term memory.","parameters":{"type":"OBJECT","properties":{"query":{"type":"STRING"}},"required":["query"]}}}"""
        return brain_manager.search_memory(query)


import storage
