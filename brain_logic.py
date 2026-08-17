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

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
MODEL = "qwen/qwen3.6-27b"

# --- Memory Logic ---
def get_recent_summaries():
    try:
        response = supabase.table("conversation_summaries").select("summary").order("created_at", desc=True).limit(3).execute()
        return [item["summary"] for item in response.data]
    except: return []

async def summarize_history_if_needed():
    # Fetch last 20 messages to summarize
    try:
        msgs = supabase.table("chat_history").select("*").order("created_at", desc=True).limit(20).execute().data
        if len(msgs) < 20: return 
        
        # In a real app, we'd trigger a background task. 
        # For now, we'll keep it simple to ensure stability.
        pass 
    except Exception as e: logger.error(f"Summarization error: {e}")

class Brain:
    def load_history(self):
        # 1. Fetch recent messages
        try:
            res = supabase.table("chat_history").select("*").order("created_at", desc=True).limit(8).execute()
            history = res.data[::-1]
            chat_msgs = [{"role": item["role"], "content": item["content"]} for item in history if item.get("content")]
            
            # 2. Fetch long-term summaries
            summaries = get_recent_summaries()
            summary_context = "\n".join([f"- {s}" for s in summaries])
            
            if summaries:
                chat_msgs.insert(0, {"role": "system", "content": f"Long-term memory summaries:\n{summary_context}"})
            
            return chat_msgs
        except: return []

    # ... (Keeping existing chat/save methods, updated to use the new load_history)
    def save_message(self, role, content):
        try: supabase.table("chat_history").insert({"role": role, "content": content}).execute()
        except Exception as e: logger.error(f"Save failed: {e}")

    async def _call_groq(self, messages, client, allow_tools=False):
        response = await client.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
            json={"model": MODEL, "messages": messages},
            timeout=20.0,
        )
        response.raise_for_status()
        return response.json()

    async def chat(self, user_message):
        messages = self.load_history()
        messages.append({"role": "user", "content": user_message})
        
        async with httpx.AsyncClient() as client:
            data = await self._call_groq(messages, client)
            ai_reply = data["choices"][0]["message"]["content"]
            
            # Simple profile update logic (keeping it robust)
            if "my name is" in user_message.lower():
                update_user_profile({"name": user_message.split("my name is")[-1].strip()})
            
            self.save_message("user", user_message)
            self.save_message("assistant", ai_reply)
            return {"response": ai_reply}

brain = Brain()
