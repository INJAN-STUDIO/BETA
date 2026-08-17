import os
import json
import httpx
import logging
import datetime
from supabase import create_client, Client
from rag_memory import format_profile_for_system_prompt, update_user_profile

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
SERPER_API_KEY = os.getenv("SERPER_API_KEY")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
MODEL = "qwen/qwen3.6-27b"

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Search the live web for current information.",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_user_profile",
            "description": "Save personal info about the user.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "location": {"type": "string"},
                    "bio": {"type": "string"}
                }
            },
        },
    }
]

async def perform_google_search(query: str) -> str:
    if not SERPER_API_KEY: return "Search not configured."
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://google.serper.dev/search",
            headers={"X-API-KEY": SERPER_API_KEY, "Content-Type": "application/json"},
            json={"q": query, "num": 3},
            timeout=10.0,
        )
        data = response.json()
        results = data.get("organic", [])
        return "\n\n".join([f"{r['title']}: {r.get('snippet')}" for r in results[:3]])

class Brain:
    def load_history(self):
        try:
            response = supabase.table("chat_history").select("*").order("created_at", desc=True).limit(8).execute()
            history = response.data[::-1]
            return [{"role": item["role"], "content": item["content"]} for item in history if item.get("content")]
        except: return []

    def save_message(self, role, content):
        try: supabase.table("chat_history").insert({"role": role, "content": content}).execute()
        except Exception as e: logger.error(f"Save failed: {e}")

    async def _call_groq(self, messages, client, allow_tools=True):
        payload = {"model": MODEL, "messages": messages}
        if allow_tools:
            payload["tools"] = TOOLS
            payload["tool_choice"] = "auto"
        response = await client.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
            json=payload,
            timeout=20.0,
        )
        response.raise_for_status()
        return response.json()

    async def chat(self, user_message):
        history = self.load_history()
        profile_context = format_profile_for_system_prompt()
        system_prompt = (
            f"You are B.E.T.A. Always be helpful and friendly. "
            f"If you need to use a tool, do so silently in the background. "
            f"Do not show <think> tags or internal processes to the user. "
            f"{profile_context} Keep responses concise."
        )
        messages = [{"role": "system", "content": system_prompt}] + history + [{"role": "user", "content": user_message}]

        async with httpx.AsyncClient() as client:
            data = await self._call_groq(messages, client)
            message = data["choices"][0]["message"]
            
            if message.get("tool_calls"):
                messages.append(message)
                for call in message["tool_calls"]:
                    func_name = call["function"]["name"]
                    args = json.loads(call["function"]["arguments"])
                    if func_name == "web_search":
                        result = await perform_google_search(args["query"])
                    elif func_name == "update_user_profile":
                        update_user_profile(args)
                        result = "Profile updated."
                    messages.append({"role": "tool", "tool_call_id": call["id"], "name": func_name, "content": result})
                
                final_data = await self._call_groq(messages, client, allow_tools=False)
                ai_reply = final_data["choices"][0]["message"]["content"]
            else:
                ai_reply = message.get("content")

            # Clean up the output in case the model ignored instructions and outputted <think>
            if "<think>" in ai_reply:
                ai_reply = ai_reply.split("</think>")[-1].strip()

            self.save_message("user", user_message)
            self.save_message("assistant", ai_reply)
            return {"response": ai_reply}

brain = Brain()
