# rag_memory.py - UPGRADED MEMORY ENGINE
# Implementation of access-based eviction, confidence weighting, and semantic dedup

import json
import os
import numpy as np
from datetime import datetime
import warnings
warnings.filterwarnings('ignore')

STORAGE_DIR = "/data" if os.path.exists("/data") and os.access("/data", os.W_OK) else os.getcwd()
MEMORY_FILE = os.path.join(STORAGE_DIR, "beta_rag_memory.json")

try:
    from sentence_transformers import SentenceTransformer
    EMBEDDING_MODEL = SentenceTransformer('all-MiniLM-L6-v2')
    USE_TRANSFORMERS = True
    print("✅ RAG Memory: Using sentence-transformers")
except:
    USE_TRANSFORMERS = False
    print("⚠️ RAG Memory: Fallback mode (No embeddings)")

def cosine_similarity(a, b):
    return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))

class VectorMemoryStore:
    def __init__(self, max_memories=300):
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
        # 1. Semantic Deduplication (Similarity > 0.92)
        if USE_TRANSFORMERS:
            new_emb = EMBEDDING_MODEL.encode(text)
            for mem in self.memories:
                if cosine_similarity(new_emb, np.array(mem['embedding'])) > 0.92:
                    mem['access_count'] += 1 # Update existing
                    self.save()
                    return False 
            embedding = new_emb.tolist()
        else:
            embedding = []

        # 2. Add new memory
        memory = {
            "text": text,
            "embedding": embedding,
            "confidence": confidence,
            "access_count": 1,
            "timestamp": datetime.now().isoformat(),
            "metadata": metadata or {}
        }
        
        self.memories.append(memory)
        
        # 3. Access-based eviction if full
        if len(self.memories) > self.max_memories:
            # Sort by confidence * access_count (the 'value' of the memory)
            self.memories.sort(key=lambda x: x['confidence'] * x['access_count'])
            self.memories.pop(0)
            
        self.save()
        return True

    def search(self, query, top_k=3):
        if not self.memories or not USE_TRANSFORMERS: return []
        
        q_emb = EMBEDDING_MODEL.encode(query)
        scored = []
        for mem in self.memories:
            sim = cosine_similarity(q_emb, np.array(mem['embedding']))
            score = sim * mem['confidence'] # Weight by confidence
            scored.append((score, mem))
            mem['access_count'] += 0.1 # Soft increment on search
            
        scored.sort(key=lambda x: x[0], reverse=True)
        return [m[1] for m in scored[:top_k]]
