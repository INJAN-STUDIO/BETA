import os
import httpx
from supabase import create_client, Client
from rag_memory import format_profile_for_system_prompt, update_user_profile

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
SERPER_API_KEY = os.getenv("SERPER_API_KEY")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# Initialize Supabase
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
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
    def load_history(self):
        # Fetch last 8 messages from Supabase, ordered by created_at
        response = supabase.table("chat_history") \
            .select("*") \
            .order("created_at", desc=True) \
            .limit(8) \
            .execute()
        
        # Reverse because we want oldest to newest for the prompt
        history = response.data[::-1]
        return [{"role": item["role"], "content": item["content"]} for item in history]

    def save_message(self, role, content):
        supabase.table("chat_history").insert({
            "role": role,
            "content": content
        }).execute()

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
        
        messages = [{"role": "system", "content": system_prompt}] + history + [{"role": "user", "content": user_message}]
        
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
                    json={"model": MODEL, "messages": messages},
                    timeout=20.0
                )
                
                data = response.json()
                if 'choices' in data:
                    ai_reply = data['choices'][0]['message']['content']
                    
                    # Save both to Supabase
                    self.save_message("user", user_message)
                    self.save_message("assistant", ai_reply)
                    
                    return {"response": ai_reply}
                return {"response": "I couldn't process that right now."}
            except Exception as e:
                return {"response": f"System Error: {str(e)}"}

brain = Brain()
