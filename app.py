import os
import json
import re
import asyncio
import threading
import tempfile
import requests
import warnings
from datetime import datetime
import edge_tts
from rag_memory import VectorMemoryStore

warnings.filterwarnings('ignore')

# --- API Configuration ---
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
GROQ_MODEL = "llama-3.3-70b-versatile"

# --- Storage Configuration ---
# Use /data if it exists (Render Persistent Disk), otherwise use local directory
STORAGE_DIR = "/data" if os.path.exists("/data") and os.access("/data", os.W_OK) else os.getcwd()
MEMORY_FILE = os.path.join(STORAGE_DIR, "beta_facts.json")

# --- Initialize Long-Term Memory ---
# VectorMemoryStore handles the "searchable" past conversations
rag_memory = VectorMemoryStore()

class BetaBrain:
    def __init__(self):
        self.durable_facts = self.load_durable_facts()
        self.short_term_history = []  # Recent messages in the current session

    def load_durable_facts(self):
        if os.path.exists(MEMORY_FILE):
            try:
                with open(MEMORY_FILE, 'r') as f:
                    return json.load(f)
            except:
                return {}
        return {"user_name": "User", "facts": [], "preferences": {}}

    def save_durable_facts(self):
        try:
            with open(MEMORY_FILE, 'w') as f:
                json.dump(self.durable_facts, f, indent=2)
        except Exception as e:
            print(f"Error saving facts: {e}")

    def get_context(self, user_query):
        """Finds relevant long-term memories and facts for the current query."""
        context = ""
        
        # 1. Add structured facts
        if self.durable_facts.get("user_name"):
            context += f"User's name is {self.durable_facts['user_name']}.\n"
        
        # 2. Search long-term vector memory
        relevant_memories = rag_memory.search(user_query, top_k=3)
        if relevant_memories:
            context += "\nRelevant things you've told me before:\n"
            for mem in relevant_memories:
                context += f"- {mem['text']}\n"
        
        return context

    async def speak(self, text):
        """Converts text to an audio file path."""
        if not text or len(text) < 2: return None
        try:
            voice = "en-US-BrianMultilingualNeural"
            # Clean text for speech (remove markdown)
            clean_text = re.sub(r'[*#_`-]', '', text)
            with tempfile.NamedTemporaryFile(delete=False, suffix='.mp3', dir="static") as tmp:
                output_path = tmp.name
                communicate = edge_tts.Communicate(clean_text[:500], voice)
                await communicate.save(output_path)
                return f"/static/{os.path.basename(output_path)}"
        except Exception as e:
            print(f"TTS Error: {e}")
            return None

    def call_llm(self, system_prompt, messages):
        if not GROQ_API_KEY:
            return "Error: No GROQ_API_KEY found in environment."
        
        try:
            payload = {
                "model": GROQ_MODEL,
                "messages": [{"role": "system", "content": system_prompt}] + messages,
                "temperature": 0.7,
                "max_tokens": 1024
            }
            response = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
                json=payload,
                timeout=30
            )
            if response.status_code == 200:
                return response.json()['choices'][0]['message']['content']
            return f"Error from Groq: {response.text}"
        except Exception as e:
            return f"Error: {str(e)}"

    async def chat(self, user_message):
        # 1. Get Memory Context
        memory_context = self.get_context(user_message)
        
        # 2. Build System Prompt
        system_prompt = f"""You are BETA (Best Everyday Technical Assistant).
Your creator is INJAN Technologies.
Current User Context:
{memory_context}

Be helpful, concise, and friendly. Use markdown for formatting.

At the end of your response, if you learned any NEW facts about the user (name, age, likes, project details), 
add a single line starting with 'MEMORY_EXTRACT:' followed by a JSON object of those facts. 
Example: MEMORY_EXTRACT: {{"user_name": "Karachi", "likes": ["coding", "linux"]}}
Do not show this line to the user if nothing was learned."""

        # 3. Manage Short-term history (last 6 messages)
        self.short_term_history.append({"role": "user", "content": user_message})
        if len(self.short_term_history) > 6:
            self.short_term_history = self.short_term_history[-6:]

        # 4. Get LLM Response
        full_response = self.call_llm(system_prompt, self.short_term_history)
        
        # 5. Extract Memories and Clean Response
        clean_response = full_response
        if "MEMORY_EXTRACT:" in full_response:
            parts = full_response.split("MEMORY_EXTRACT:")
            clean_response = parts[0].strip()
            try:
                new_facts = json.loads(parts[1].strip())
                self.update_memory(new_facts, user_message)
            except:
                pass

        self.short_term_history.append({"role": "assistant", "content": clean_response})
        
        # 6. Generate Voice
        audio_url = await self.speak(clean_response)
        
        return {
            "response": clean_response,
            "audio_url": audio_url
        }

    def update_memory(self, new_facts, user_message):
        """Updates the durable facts and vector memory."""
        # Save to durable JSON
        if "user_name" in new_facts:
            self.durable_facts["user_name"] = new_facts["user_name"]
        
        for key, value in new_facts.items():
            if key != "user_name":
                self.durable_facts["preferences"][key] = value
        
        self.save_durable_facts()
        
        # Save to Vector RAG memory for semantic search later
        rag_memory.add(f"User said: {user_message}")

# Create a single instance of the brain
brain = BetaBrain()
