import os
import httpx
import json
from rag_memory import format_profile_for_system_prompt, update_user_profile

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
SERPER_API_KEY = os.getenv("SERPER_API_KEY") # Ensure this is set in Render env
MODEL = "llama-3.3-70b-versatile"

async def perform_google_search(query):
    if not SERPER_API_KEY:
        return "Search functionality not configured."
    
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://google.serper.dev/search",
            headers={"X-API-KEY": SERPER_API_KEY, "Content-Type": "application/json"},
            json={"q": query}
        )
        data = response.json()
        results = data.get("organic", [])
        return "\n".join([f"{r['title']}: {r.get('snippet', '')}" for r in results[:3]])

class Brain:
    async def chat(self, user_message):
        if "my name is" in user_message.lower():
            name = user_message.split("my name is")[-1].strip().split(".")[0]
            update_user_profile({"name": name})
        
        # Decide if we need to search
        search_results = ""
        if any(word in user_message.lower() for word in ["what is", "who is", "search for", "find out"]):
            search_results = f"\n\nSearch Context:\n{await perform_google_search(user_message)}"
        
        profile_context = format_profile_for_system_prompt()
        system_prompt = f"You are B.E.T.A., a helpful AI assistant. {profile_context} {search_results} Keep responses concise and use a friendly tone."
        
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
                
                data = response.json()
                if 'choices' in data and len(data['choices']) > 0:
                    return {"response": data['choices'][0]['message']['content']}
                return {"response": "I couldn't process that right now."}
            except Exception as e:
                return {"response": f"System Error: {str(e)}"}

brain = Brain()
