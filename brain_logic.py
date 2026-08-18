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

SEARCH_TRIGGER_WORDS = [
    "current", "latest", "recent", "today", "this week", "this month",
    "this year", "who is", "what is", "price", "cost", "score", "news",
    "update", "release", "version", "2024", "2025", "2026",
]

def should_search(message: str) -> bool:
    lower = message.lower()
    return any(trigger in lower for trigger in SEARCH_TRIGGER_WORDS)

async def web_search(query: str, num_results: int = 5):
    if not SERPER_API_KEY:
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
            if not results: return None
            text = "\n\n**Web search results:**\n"
            for i, item in enumerate(results[:num_results], 1):
                text += f"{i}. {item.get('title', '')}\n{item.get('snippet', '')}\n{item.get('link', '')}\n\n"
            return text
    except Exception as e:
        logger.error(f"Web search failed: {e}")
        return None

class Brain:
    def load_history(self):
        try:
            res = supabase.table("chat_history").select("*").order("created_at", desc=True).limit(8).execute()
            history = res.data[::-1]
            chat_msgs = [{"role": item["role"], "content": item["content"]} for item in history if item.get("content")]
            return chat_msgs
        except: return []

    def save_message(self, role, content):
        try: supabase.table("chat_history").insert({"role": role, "content": content}).execute()
        except Exception as e: logger.error(f"Save failed: {e}")

    async def chat(self, user_message, show_thinking=False):
        messages = self.load_history()
        
        # Automatic Web Search logic
        if should_search(user_message):
            search_results = await web_search(user_message)
            if search_results:
                messages.append({"role": "system", "content": f"User's request requires live info. Use these results: {search_results}"})
        
        messages.append({"role": "user", "content": user_message})
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
                json={"model": MODEL, "messages": messages},
                timeout=30.0,
            )
            data = response.json()
            full_content = data["choices"][0]["message"]["content"]
            
            thought = None
            ai_reply = full_content
            if "<think>" in full_content and "</think>" in full_content:
                parts = full_content.split("</think>")
                if show_thinking:
                    thought = parts[0].replace("<think>", "").strip()
                ai_reply = parts[1].strip()
            
            self.save_message("user", user_message)
            self.save_message("assistant", ai_reply)
            
            return {"thought": thought, "response": ai_reply}

brain = Brain()
