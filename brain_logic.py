import os
import json
import httpx
import logging
from supabase import create_client, Client
from rag_memory import format_profile_for_system_prompt, update_user_profile

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
SERPER_API_KEY = os.getenv("SERPER_API_KEY")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
MODEL = "qwen/qwen3.6-27b"

# ----------------------------------------------------------------
# Web search - this was completely missing before. Without this,
# there was no code path that ever reached out to the internet,
# regardless of what the GUI or model implied was possible.
# ----------------------------------------------------------------
SEARCH_TRIGGER_WORDS = [
    "current", "latest", "recent", "today", "this week", "this month",
    "this year", "who is", "what is", "price", "cost", "score", "news",
    "update", "release", "version", "2024", "2025", "2026",
]


def should_search(message: str) -> bool:
    lower = message.lower()
    return any(trigger in lower for trigger in SEARCH_TRIGGER_WORDS)


async def web_search(query: str, num_results: int = 5):
    """Returns formatted search result text, or None if search isn't
    configured/available/failed. Never raises - a failed search should
    never break the chat turn."""
    if not SERPER_API_KEY:
        logger.warning("SERPER_API_KEY not set - web_search called but skipped")
        return None

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://google.serper.dev/search",
                json={"q": query, "num": num_results},
                headers={"X-API-KEY": SERPER_API_KEY, "Content-Type": "application/json"},
                timeout=15.0,
            )
            data = response.json()
            results = data.get("organic", [])
            if not results:
                return None

            text = "\n\n**Web search results:**\n"
            for i, item in enumerate(results[:num_results], 1):
                title = item.get("title", "")
                snippet = item.get("snippet", "")
                link = item.get("link", "")
                text += f"{i}. {title}\n{snippet}\n{link}\n\n"
            return text
    except Exception as e:
        logger.error(f"Web search failed: {e}")
        return None


def get_recent_summaries():
    try:
        response = supabase.table("conversation_summaries").select("summary").order("created_at", desc=True).limit(3).execute()
        return [item["summary"] for item in response.data]
    except: return []

class Brain:
    def load_history(self):
        try:
            res = supabase.table("chat_history").select("*").order("created_at", desc=True).limit(8).execute()
            history = res.data[::-1]
            chat_msgs = [{"role": item["role"], "content": item["content"]} for item in history if item.get("content")]
            
            summaries = get_recent_summaries()
            if summaries:
                summary_text = "\n".join([f"- {s}" for s in summaries])
                chat_msgs.insert(0, {"role": "system", "content": f"Use these memories to answer: {summary_text}"})
            return chat_msgs
        except: return []

    def save_message(self, role, content):
        try: supabase.table("chat_history").insert({"role": role, "content": content}).execute()
        except Exception as e: logger.error(f"Save failed: {e}")

    async def chat(self, user_message, show_thinking: bool = False):
        messages = self.load_history()

        # Search BEFORE building the final user message, so results are
        # part of what the model actually sees and reasons over.
        full_user_content = user_message
        if should_search(user_message):
            logger.info(f"Searching for: {user_message}")
            search_results = await web_search(user_message)
            if search_results:
                full_user_content += search_results

        messages.append({"role": "user", "content": full_user_content})
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
                json={"model": MODEL, "messages": messages},
                timeout=30.0,
            )
            data = response.json()
            full_content = data["choices"][0]["message"]["content"]
            
            # Split the thinking process from the actual response
            if "<think>" in full_content and "</think>" in full_content:
                parts = full_content.split("</think>")
                thought = parts[0].replace("<think>", "").strip()
                ai_reply = parts[1].strip()
            else:
                thought = None
                ai_reply = full_content
            
            if "my name is" in user_message.lower():
                update_user_profile({"name": user_message.split("my name is")[-1].strip()})
            
            self.save_message("user", user_message)
            self.save_message("assistant", ai_reply)
            
            # Only send the thought to the frontend if the Think toggle is
            # on. This is a deliberate second line of defense: even if the
            # GUI has a bug and renders unconditionally, the backend simply
            # won't hand it a thought to render when the toggle is off.
            return {
                "thought": thought if show_thinking else None,
                "response": ai_reply,
            }

brain = Brain()
