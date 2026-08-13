# rag_memory.py - LIGHTWEIGHT VERSION (No heavy AI models)
import json
import os
import numpy as np
from datetime import datetime

# Fallback: No heavy imports to keep memory low
STORAGE_DIR = "/data" if os.path.exists("/data") and os.access("/data", os.W_OK) else os.getcwd()
MEMORY_FILE = os.path.join(STORAGE_DIR, "beta_rag_memory.json")

class VectorMemoryStore:
    def __init__(self, max_memories=100):
        self.memories = []
        self.max_memories = max_memories
        self.load()

    def load(self):
        if os.path.exists(MEMORY_FILE):
            try:
                with open(MEMORY_FILE, 'r') as f:
                    self.memories = json.load(f)
            except: self.memories = []

    def save(self):
        with open(MEMORY_FILE, 'w') as f:
            json.dump(self.memories, f, indent=2)

    def add(self, text, confidence=0.6, metadata=None):
        # Keyword-based memory (Lightweight)
        for mem in self.memories:
            if text.lower() == mem['text'].lower():
                mem['access_count'] += 1
                self.save()
                return False 

        memory = {
            "text": text,
            "confidence": confidence,
            "access_count": 1,
            "timestamp": datetime.now().isoformat(),
            "metadata": metadata or {}
        }
        
        self.memories.append(memory)
        
        if len(self.memories) > self.max_memories:
            self.memories.sort(key=lambda x: x['confidence'] * x['access_count'])
            self.memories.pop(0)
            
        self.save()
        return True

    def search(self, query, top_k=3):
        # Keyword/Substring search (Super efficient)
        q = query.lower()
        results = []
        for mem in self.memories:
            if q in mem['text'].lower():
                results.append(mem)
        return results[:top_k]
