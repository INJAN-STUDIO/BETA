import os
import json
import httpx
from rag_memory import format_profile_for_system_prompt, update_user_profile

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
MODEL = "llama-3.1-70b-versatile"

class Brain:
    def __init__(self):
        self.history = []

    async def chat(self, user_message):
        # 1. Update profile if user provides name/info (simple keyword check)
        if "my name is" in user_message.lower():
            name = user_message.split("my name is")[-1].strip().split(".")[0]
            update_user_profile({"name": name})
        
        # 2. Build context
        profile_context = format_profile_for_system_prompt()
        system_prompt = f"You are B.E.T.A., a helpful AI assistant. {profile_context} Keep responses concise and use a friendly tone."
        
        # 3. Call Groq
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
                json={
                    "model": MODEL,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_message}
                    ],
                    "stream": False
                },
                timeout=20.0
            )
            data = response.json()
            reply = data['choices'][0]['message']['content']
            
            return {"response": reply}

brain = Brain()
