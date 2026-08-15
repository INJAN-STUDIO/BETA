import os
import httpx
import json
from rag_memory import format_profile_for_system_prompt, update_user_profile

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
SERPER_API_KEY = os.getenv("SERPER_API_KEY")
MODEL = "llama-3.3-70b-versatile"
HISTORY_FILE = "chat_history.json"

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
    def load_history(self):
        if os.path.exists(HISTORY_FILE):
            try:
                with open(HISTORY_FILE, "r") as f:
                    return json.load(f)
            except:
                return []
        return []

    def save_history(self, history):
        # Keep only the last 4 exchanges (8 messages total: user/ai pairs)
        with open(HISTORY_FILE, "w") as f:
            json.dump(history[-8:], f)

    async def chat(self, user_message):
        history = self.load_history()

        if "my name is" in user_message.lower():
            name = user_message.split("my name is")[-1].strip().split(".")[0]
            update_user_profile({"name": name})
        
        search_results = ""
        if any(word in user_message.lower() for word in ["what is", "who is", "search for", "find out"]):
            search_results = f"\n\nSearch Context:\n{await perform_google_search(user_message)}"
        
        profile_context = format_profile_for_system_prompt()
        system_prompt = f"You are B.E.T.A., a helpful AI assistant. {profile_context} {search_results} Keep responses concise and use a friendly tone."
        
        # Prepare messages: System + History + Current
        messages = [{"role": "system", "content": system_prompt}]
        for msg in history:
            messages.append(msg)
        messages.append({"role": "user", "content": user_message})
        
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
                    json={
                        "model": MODEL,
                        "messages": messages
                    },
                    timeout=20.0
                )
                
                data = response.json()
                if 'choices' in data and len(data['choices']) > 0:
                    ai_reply = data['choices'][0]['message']['content']
                    
                    # Update history and save
                    history.append({"role": "user", "content": user_message})
                    history.append({"role": "assistant", "content": ai_reply})
                    self.save_history(history)
                    
                    return {"response": ai_reply}
                return {"response": "I couldn't process that right now."}
            except Exception as e:
                return {"response": f"System Error: {str(e)}"}

brain = Brain()
