import os
import json
import httpx
from rag_memory import format_profile_for_system_prompt, update_user_profile

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
MODEL = "llama-3.1-70b-versatile"

class Brain:
    async def chat(self, user_message):
        if "my name is" in user_message.lower():
            name = user_message.split("my name is")[-1].strip().split(".")[0]
            update_user_profile({"name": name})
        
        profile_context = format_profile_for_system_prompt()
        system_prompt = f"You are B.E.T.A., a helpful AI assistant. {profile_context} Keep responses concise and use a friendly tone."
        
        async with httpx.AsyncClient() as client:
            try:
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
                response.raise_for_status()
                data = response.json()
                
                # FIX: Check if 'choices' exists before accessing
                if 'choices' in data and len(data['choices']) > 0:
                    reply = data['choices'][0]['message']['content']
                    return {"response": reply}
                else:
                    return {"response": "I'm having trouble thinking right now. (Groq error)"}
            except Exception as e:
                return {"response": f"Error: {str(e)}"}

brain = Brain()
