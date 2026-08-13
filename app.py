import os
import json
import re
import requests
import warnings
from rag_memory import VectorMemoryStore

warnings.filterwarnings('ignore')

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
GROQ_MODEL = "llama-3.3-70b-versatile"
rag_memory = VectorMemoryStore()

class BetaBrain:
    def __init__(self):
        self.filler_patterns = [
            r"hi", r"hello", r"how are you", r"what can you do", 
            r"thank you", r"thanks", r"good morning", r"good evening"
        ]

    def is_worth_remembering(self, text):
        if len(text) < 20: return False
        for pattern in self.filler_patterns:
            if re.search(pattern, text.lower()): return False
        return True

    def call_llm(self, system_prompt, message):
        payload = {
            "model": GROQ_MODEL,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": message}
            ],
            "temperature": 0.7
        }
        r = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
            json=payload
        )
        return r.json()['choices'][0]['message']['content']

    async def chat(self, user_message):
        # 1. Distill and Remember (The "Gate")
        if self.is_worth_remembering(user_message):
            # Check for force-pin
            if user_message.lower().startswith("remember:"):
                fact = user_message.split("remember:")[1].strip()
                rag_memory.add(fact, confidence=1.0)
            else:
                rag_memory.add(user_message, confidence=0.6)

        # 2. Retrieve context
        context = "\n".join([m['text'] for m in rag_memory.search(user_message)])
        
        system_prompt = f"You are BETA. Use this context if relevant: {context}"
        
        response = self.call_llm(system_prompt, user_message)
        
        return {"response": response, "audio_url": None}

brain = BetaBrain()
