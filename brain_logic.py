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

    async def chat(self, user_message):
        messages = self.load_history()
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
            
            # Return structured JSON for the frontend
            return {"thought": thought, "response": ai_reply}

brain = Brain()
