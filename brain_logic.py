import os
import httpx
from rag_memory import format_profile_for_system_prompt, update_user_profile

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
# Switched from deprecated llama-3.1-70b-versatile to llama-3.3-70b-versatile
MODEL = "llama-3.3-70b-versatile"

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
                        ]
                    },
                    timeout=20.0
                )
                
                if response.status_code != 200:
                    return {"response": f"API Error: {response.status_code} - {response.text}"}
                
                data = response.json()
                
                if "error" in data:
                    return {"response": f"Groq Error: {data['error'].get('message', 'Unknown error')}"}
                
                if 'choices' in data and len(data['choices']) > 0:
                    reply = data['choices'][0]['message']['content']
                    return {"response": reply}
                else:
                    return {"response": f"Unexpected API format."}
            except Exception as e:
                return {"response": f"System Error: {str(e)}"}

brain = Brain()
