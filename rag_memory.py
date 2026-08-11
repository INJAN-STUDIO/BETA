# rag_memory.py
# Lightweight RAG Engine for BETA
# Uses sentence-transformers for real semantic embeddings
# Falls back to TF-IDF if sentence-transformers isn't available

import json
import os
import numpy as np
from datetime import datetime
import warnings
warnings.filterwarnings('ignore')

# --- Configuration ---
PERSISTENT_DIR = "/data"
LOCAL_DIR = os.getcwd()
STORAGE_DIR = PERSISTENT_DIR if os.path.exists(PERSISTENT_DIR) and os.access(PERSISTENT_DIR, os.W_OK) else LOCAL_DIR
MEMORY_FILE = os.path.join(STORAGE_DIR, "beta_rag_memory.json")

print(f"🧠 RAG Memory storage: {MEMORY_FILE}")

# Try to import sentence-transformers, fall back to simple TF-IDF if unavailable
try:
    from sentence_transformers import SentenceTransformer
    EMBEDDING_MODEL = SentenceTransformer('all-MiniLM-L6-v2')
    USE_TRANSFORMERS = True
    EMBEDDING_DIM = 384
    print("✅ Using sentence-transformers for high-quality embeddings")
except ImportError:
    USE_TRANSFORMERS = False
    EMBEDDING_DIM = 128
    print("⚠️ sentence-transformers not available, using TF-IDF fallback")

# --- 1. TF-IDF Fallback Embedding Generator ---
class TFIDFEmbedder:
    """Simple TF-IDF based embedding for when sentence-transformers isn't available"""
    def __init__(self, dim=128):
        self.vocabulary = {}
        self.idf = {}
        self.document_count = 0
        self.dim = dim
        
    def tokenize(self, text):
        """Simple tokenization"""
        import re
        return re.findall(r'\b\w+\b', text.lower())
    
    def fit(self, documents):
        """Build vocabulary and IDF from documents"""
        if not documents:
            return
            
        doc_freq = {}
        self.document_count = len(documents)
        
        for doc in documents:
            tokens = set(self.tokenize(doc))
            for token in tokens:
                doc_freq[token] = doc_freq.get(token, 0) + 1
        
        # Build vocabulary and compute IDF
        self.vocabulary = {word: idx for idx, word in enumerate(sorted(doc_freq.keys()))}
        for word, freq in doc_freq.items():
            self.idf[word] = np.log((self.document_count + 1) / (freq + 1)) + 1
    
    def transform(self, text):
        """Convert text to TF-IDF vector with dimensionality reduction"""
        if not self.vocabulary:
            # If no vocabulary, create a simple hash-based embedding
            tokens = self.tokenize(text)
            vec = np.zeros(self.dim)
            for token in tokens:
                idx = hash(token) % self.dim
                vec[idx] += 1
            norm = np.linalg.norm(vec)
            if norm > 0:
                vec = vec / norm
            return vec
        
        vec = np.zeros(len(self.vocabulary))
        tokens = self.tokenize(text)
        token_count = {}
        
        for token in tokens:
            token_count[token] = token_count.get(token, 0) + 1
        
        for token, count in token_count.items():
            if token in self.vocabulary:
                tf = count / len(tokens)
                vec[self.vocabulary[token]] = tf * self.idf.get(token, 1.0)
        
        # Reduce dimensionality if needed
        if len(vec) > self.dim:
            reduced = np.zeros(self.dim)
            chunk_size = len(vec) / self.dim
            for i in range(self.dim):
                start = int(i * chunk_size)
                end = int((i + 1) * chunk_size)
                reduced[i] = np.mean(vec[start:end]) if end > start else 0
            vec = reduced
        
        # Normalize
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec = vec / norm
        
        return vec

# --- 2. Embedding Generation ---
class EmbeddingGenerator:
    def __init__(self):
        self.tfidf = TFIDFEmbedder(dim=EMBEDDING_DIM)
        self.use_transformers = USE_TRANSFORMERS
        
    def get_embedding(self, text):
        """Generate embedding for text"""
        try:
            if self.use_transformers:
                # Use sentence-transformers
                embedding = EMBEDDING_MODEL.encode(text[:1000], show_progress_bar=False)
                return embedding
            else:
                # Use TF-IDF fallback
                return self.tfidf.transform(text)
        except Exception as e:
            print(f"Embedding generation error: {e}")
            # Ultimate fallback - hash-based but consistent embedding
            np.random.seed(abs(hash(text)) % (2**31 - 1))
            embedding = np.random.randn(EMBEDDING_DIM)
            embedding = embedding / np.linalg.norm(embedding)
            return embedding

# Initialize embedding generator
embedding_generator = EmbeddingGenerator()

# --- 3. Vector Memory Store ---
class VectorMemoryStore:
    def __init__(self, max_memories=500):
        self.memories = []
        self.max_memories = max_memories
        self.load()
        # Update TF-IDF with existing memories
        if not USE_TRANSFORMERS and self.memories:
            texts = [mem['text'] for mem in self.memories]
            embedding_generator.tfidf.fit(texts)

    def load(self):
        """Load memories from persistent JSON storage"""
        try:
            if os.path.exists(MEMORY_FILE):
                with open(MEMORY_FILE, 'r') as f:
                    data = json.load(f)
                
                loaded_count = 0
                for item in data:
                    if 'text' in item and item['text']:
                        # Convert embedding back to numpy array
                        if 'embedding' in item and item['embedding']:
                            try:
                                item['embedding'] = np.array(item['embedding'])
                                loaded_count += 1
                            except:
                                # Regenerate embedding if conversion fails
                                item['embedding'] = embedding_generator.get_embedding(item['text'])
                                loaded_count += 1
                        else:
                            # Generate embedding if missing
                            item['embedding'] = embedding_generator.get_embedding(item['text'])
                            loaded_count += 1
                        
                        # Add timestamp if missing
                        if 'timestamp' not in item:
                            item['timestamp'] = datetime.now().isoformat()
                        
                        self.memories.append(item)
                
                print(f"🧠 Loaded {loaded_count} RAG memories from storage")
        except Exception as e:
            print(f"RAG memory load error: {e}")
            self.memories = []

    def save(self):
        """Save memories to persistent JSON storage"""
        try:
            data_to_save = []
            for item in self.memories:
                item_copy = {
                    'text': item['text'],
                    'metadata': item.get('metadata', {}),
                    'timestamp': item.get('timestamp', datetime.now().isoformat())
                }
                # Convert numpy array to list for JSON serialization
                if 'embedding' in item and isinstance(item['embedding'], np.ndarray):
                    item_copy['embedding'] = item['embedding'].tolist()
                data_to_save.append(item_copy)

            os.makedirs(STORAGE_DIR, exist_ok=True)
            with open(MEMORY_FILE, 'w') as f:
                json.dump(data_to_save, f, indent=2)
            print(f"💾 Saved {len(self.memories)} RAG memories")
        except Exception as e:
            print(f"RAG memory save error: {e}")

    def add(self, text, metadata=None):
        """Add a memory with its embedding"""
        if not text or len(text.strip()) < 3:
            return False
        
        # Check for duplicates (exact match)
        text_stripped = text.strip()
        for existing in self.memories:
            if existing['text'].strip().lower() == text_stripped.lower():
                # Update timestamp for existing memory
                existing['timestamp'] = datetime.now().isoformat()
                self.save()
                return True
        
        # Generate embedding
        embedding = embedding_generator.get_embedding(text_stripped)
        if embedding is None:
            print(f"⚠️ Failed to generate embedding for: {text_stripped[:50]}...")
            return False

        memory = {
            "text": text_stripped,
            "embedding": embedding,
            "metadata": metadata or {},
            "timestamp": datetime.now().isoformat()
        }

        self.memories.append(memory)
        
        # Keep only the most recent memories if we exceed the limit
        if len(self.memories) > self.max_memories:
            # Sort by timestamp and keep newest
            self.memories.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
            self.memories = self.memories[:self.max_memories]
            print(f"📦 Trimmed memories to {self.max_memories} (max limit)")
        
        self.save()
        return True

    def search(self, query, top_k=3, threshold=0.2):
        """Find the most relevant memories using cosine similarity"""
        if not self.memories:
            return []

        query_embedding = embedding_generator.get_embedding(query)
        if query_embedding is None:
            # Fallback to keyword search
            results = []
            query_lower = query.lower()
            for mem in self.memories:
                if query_lower in mem['text'].lower():
                    results.append(mem)
            return results[:top_k]

        # Calculate similarities
        similarities = []
        for memory in self.memories:
            mem_embedding = memory.get('embedding')
            if mem_embedding is None:
                continue
            
            # Cosine similarity
            dot_product = np.dot(query_embedding, mem_embedding)
            norm_product = np.linalg.norm(query_embedding) * np.linalg.norm(mem_embedding)
            
            if norm_product > 0:
                similarity = dot_product / norm_product
                if similarity >= threshold:
                    similarities.append((similarity, memory))

        # Sort by similarity (highest first)
        similarities.sort(key=lambda x: x[0], reverse=True)
        
        # Return top-k results
        return [mem for _, mem in similarities[:top_k]]

    def forget(self, query):
        """Remove all memories related to a query"""
        query_lower = query.lower()
        original_count = len(self.memories)
        self.memories = [mem for mem in self.memories if query_lower not in mem['text'].lower()]
        removed = original_count - len(self.memories)
        self.save()
        print(f"🗑️ Forgotten {removed} memories related to '{query}'")
        return True

    def clear(self):
        """Wipe all memories"""
        count = len(self.memories)
        self.memories = []
        self.save()
        print(f"🧹 Cleared all {count} memories")
        return True

    def stats(self):
        """Get memory statistics"""
        if not self.memories:
            return {
                "total_memories": 0,
                "last_updated": "Never"
            }
        
        return {
            "total_memories": len(self.memories),
            "last_updated": self.memories[-1]['timestamp'] if self.memories else "Never",
            "embedding_type": "sentence-transformers" if USE_TRANSFORMERS else "TF-IDF"
        }

# Test if it works
if __name__ == "__main__":
    store = VectorMemoryStore()
    print(f"📊 Memory stats: {store.stats()}")
    
    # Test adding memories
    store.add("User's name is John")
    store.add("John loves Python programming")
    store.add("John's favorite color is blue")
    
    # Test search
    results = store.search("What programming language does John like?")
    print(f"\n🔍 Search results for 'programming':")
    for r in results:
        print(f"  - {r['text']}")
    
    print(f"\n📊 Updated stats: {store.stats()}")