# ====================================================================
# BETA 6.5 - CYBERPUNK EDITION (ORIGINAL + PWA FIX)
# Fixed TTS | Smooth Scrolling | Vibrant Colors | Animated Logo | Static Icons
# PWA: Custom icon support added
# Created by Favour Austin | INJAN Technologies
# ====================================================================

import subprocess
import sys
import os
import tempfile
import json
import warnings
import requests
import re
import asyncio
import urllib.request
import time
import base64
import threading
from datetime import datetime

# Install packages
def install(pkg):
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", pkg],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

required = ["requests", "beautifulsoup4", "edge-tts", "psutil", "PyPDF2", "python-docx", "numpy", "fastapi"]
for pkg in required:
    try:
        __import__(pkg.replace("-", "_"))
    except:
        install(pkg)

import gradio as gr
import edge_tts
import numpy as np
from bs4 import BeautifulSoup
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse  # ADDED for PWA

warnings.filterwarnings('ignore')

# Import RAG memory module
try:
    from rag_memory import VectorMemoryStore
    RAG_AVAILABLE = True
    print("✅ RAG Memory module loaded")
except ImportError:
    RAG_AVAILABLE = False
    VectorMemoryStore = None
    print("⚠️ RAG Memory module not found - using basic memory only")

print("=" * 60)
print("🤖 BETA 6.5 - CYBERPUNK EDITION (FIXED)")
print("🧠 RAG Memory | 🎤 Smooth Speech | 💎 Glass Morphism")
print("=" * 60)

# ====================================================================
# API KEYS
# ====================================================================
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
CEREBRAS_API_KEY = os.environ.get("CEREBRAS_API_KEY", "")
SERPER_KEY = os.environ.get("SERPER_API_KEY", "")

GROQ_MODEL = "llama-3.3-70b-versatile"
GROQ_VISION_MODEL = "llama-3.2-11b-vision-preview"
CEREBRAS_MODEL = "llama3.3-70b"

# ====================================================================
# STATIC FILES SETUP
# ====================================================================
STATIC_DIR = os.path.join(os.getcwd(), "static")
os.makedirs(STATIC_DIR, exist_ok=True)

# Copy icon files to static directory if they exist in root
for icon_file in ["beta_icon_512.jpg", "beta_icon_192.jpg"]:
    root_path = os.path.join(os.getcwd(), icon_file)
    static_path = os.path.join(STATIC_DIR, icon_file)
    if os.path.exists(root_path) and not os.path.exists(static_path):
        import shutil
        shutil.copy2(root_path, static_path)
        print(f"📁 Copied {icon_file} to static/")

BETA_LOGO_URL = "https://i.ibb.co/20NMjh7K/photo-6035158375441568409-y.jpg"
ICON_512_PATH = "/static/beta_icon_512.jpg"
ICON_192_PATH = "/static/beta_icon_192.jpg"

print(f"📁 Static directory: {STATIC_DIR}")
print(f"🖼️ Icon 512: {'Found' if os.path.exists(os.path.join(STATIC_DIR, 'beta_icon_512.jpg')) else 'Not found'}")
print(f"🖼️ Icon 192: {'Found' if os.path.exists(os.path.join(STATIC_DIR, 'beta_icon_192.jpg')) else 'Not found'}")

# ====================================================================
# PERSISTENT STORAGE SETUP
# ====================================================================
PERSISTENT_DIR = "/data"
LOCAL_DIR = os.getcwd()
STORAGE_DIR = PERSISTENT_DIR if os.path.exists(PERSISTENT_DIR) and os.access(PERSISTENT_DIR, os.W_OK) else LOCAL_DIR
NOTEBOOK_FILE = os.path.join(STORAGE_DIR, "beta_notebook.json")

print(f"💾 Storage: {STORAGE_DIR}")
print(f"📓 Notebook: {NOTEBOOK_FILE}")

# ====================================================================
# GLOBAL FLAGS
# ====================================================================
_introduction_given = False

# ====================================================================
# RATE LIMITER
# ====================================================================
class RateLimiter:
    def __init__(self, min_interval=2):
        self.min_interval = min_interval
        self.last_call_time = 0
        self._lock = threading.Lock()
    
    def wait(self):
        with self._lock:
            current_time = time.time()
            time_since_last = current_time - self.last_call_time
            if time_since_last < self.min_interval:
                time.sleep(self.min_interval - time_since_last)
            self.last_call_time = time.time()

rate_limiter = RateLimiter()

# ====================================================================
# FILE & IMAGE HELPERS
# ====================================================================
MAX_IMAGE_SIZE_MB = 5

def is_image_file(file_path):
    if not file_path:
        return False
    try:
        ext = os.path.splitext(str(file_path))[1].lower()
        return ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp']
    except:
        return False

def is_document_file(file_path):
    if not file_path:
        return False
    try:
        ext = os.path.splitext(str(file_path))[1].lower()
        return ext in ['.pdf', '.docx', '.doc', '.txt', '.md', '.csv', '.py', '.js', '.html', '.css', '.json']
    except:
        return False

def encode_image(image_path):
    try:
        if not os.path.exists(str(image_path)):
            return None
        file_size = os.path.getsize(str(image_path)) / (1024 * 1024)
        if file_size > MAX_IMAGE_SIZE_MB:
            print(f"⚠️ Image too large: {file_size:.1f}MB")
            return None
        with open(str(image_path), "rb") as f:
            image_data = f.read()
        if len(image_data) > 10 * 1024 * 1024:
            return None
        return base64.b64encode(image_data).decode('utf-8')
    except:
        return None

def read_file(file_path):
    if not file_path or not os.path.exists(str(file_path)):
        return None
    file_path = str(file_path)
    name = os.path.basename(file_path)
    ext = os.path.splitext(name)[1].lower()
    
    try:
        if ext in ['.py', '.js', '.html', '.css', '.json', '.txt', '.md', '.csv']:
            with open(file_path, 'r', errors='ignore') as f:
                return f.read()[:6000]
        elif ext == '.pdf':
            from PyPDF2 import PdfReader
            reader = PdfReader(file_path)
            pages_text = []
            for i, page in enumerate(reader.pages[:10]):
                text = page.extract_text()
                if text:
                    pages_text.append(f"--- Page {i+1} ---\n{text}")
            return '\n'.join(pages_text)[:6000]
        elif ext in ['.docx', '.doc']:
            from docx import Document
            doc = Document(file_path)
            paragraphs = [p.text for p in doc.paragraphs[:100]]
            return '\n'.join(paragraphs)[:6000]
        return f"[Unsupported file: {name}]"
    except Exception as e:
        return f"[Could not read: {name}]"

# ====================================================================
# SPEECH PRE-PROCESSOR - FIXED (No SSML, Natural Pauses)
# ====================================================================
def prepare_for_speech(text):
    """
    Transform AI response into natural-sounding speech.
    Uses natural punctuation pauses instead of SSML tags.
    """
    if not text or len(text) < 5:
        return text
    
    # Remove code blocks (replace with brief mention)
    text = re.sub(r'```.*?```', '. I have included code in the chat. ', text, flags=re.DOTALL)
    text = re.sub(r'`([^`]+)`', r' \1 ', text)
    
    # Remove URLs but keep description text
    text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)
    text = re.sub(r'https?://\S+', '', text)
    
    # Replace markdown headers with spoken transitions + ellipsis for natural pause
    text = re.sub(r'^###\s+(.+?)$', r'\1... ', text, flags=re.MULTILINE)
    text = re.sub(r'^##\s+(.+?)$', r'\1... ', text, flags=re.MULTILINE)
    text = re.sub(r'^#\s+(.+?)$', r'\1... ', text, flags=re.MULTILINE)
    
    # Bold headers to spoken with pause
    text = re.sub(r'\*\*(.+?)\*\*:', r'\1... ', text)
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
    
    # Add periods at line breaks for natural TTS pauses
    text = re.sub(r'\n\s*\n', '. ', text)
    text = re.sub(r'\n', '. ', text)
    
    # Clean up markdown
    text = re.sub(r'\*([^*]+)\*', r'\1', text)
    text = re.sub(r'~~([^~]+)~~', r'\1', text)
    text = re.sub(r'[>\-|•]', '', text)
    
    # Remove any SSML/HTML tags (safety - prevents "break time" being spoken)
    text = re.sub(r'<[^>]+>', '', text)
    
    # Remove emojis for cleaner speech
    text = re.sub(r'[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF\U0001F1E0-\U0001F1FF\u2600-\u26FF\u2700-\u27BF]', '', text)
    
    # Fix multiple punctuation
    text = re.sub(r'\.{2,}', '... ', text)
    text = re.sub(r'\.\s+\.', '. ', text)
    text = re.sub(r'\s+\.', '.', text)
    
    # Normalize whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    
    # Limit length for TTS
    text = text[:3000]
    
    return text

# ====================================================================
# TTS MANAGER
# ====================================================================
class TTSManager:
    def __init__(self):
        self.loop = None
        self._lock = threading.Lock()
    
    def get_loop(self):
        with self._lock:
            try:
                self.loop = asyncio.get_event_loop()
                if self.loop.is_closed():
                    self.loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(self.loop)
            except RuntimeError:
                self.loop = asyncio.new_event_loop()
                asyncio.set_event_loop(self.loop)
            return self.loop
    
    async def generate_speech(self, text, voice, output_path):
        communicate = edge_tts.Communicate(text, voice)
        await communicate.save(output_path)
    
    def speak(self, text, voice="en-US-BrianMultilingualNeural"):
        if not text or len(text) < 5:
            return None
        try:
            # Pre-process text for natural speech
            clean = prepare_for_speech(text)
            
            if len(clean) < 5:
                return None
            
            with tempfile.NamedTemporaryFile(delete=False, suffix='.mp3') as tmp:
                output_path = tmp.name
            
            loop = self.get_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(asyncio.run, self.generate_speech(clean, voice, output_path))
                    future.result()
            else:
                loop.run_until_complete(self.generate_speech(clean, voice, output_path))
            return output_path
        except Exception as e:
            print(f"TTS error: {e}")
            return None

tts_manager = TTSManager()

def speak(text):
    return tts_manager.speak(text)

# ====================================================================
# ERROR HANDLING
# ====================================================================
class ErrorResponse:
    @staticmethod
    def rate_limit():
        return "⚠️ Both providers are currently rate limited. Please wait and try again.", "none"
    @staticmethod
    def no_api_keys():
        return "❌ No API keys configured.", "none"
    @staticmethod
    def timeout():
        return "⏰ Request timed out. Please try again.", "none"
    @staticmethod
    def general_error(error_msg):
        return f"❌ Error: {error_msg[:100]}.", "none"
    @staticmethod
    def success(response, provider):
        return response, provider

# ====================================================================
# NOTEBOOK MEMORY (BACKUP)
# ====================================================================
def load_notebook():
    try:
        if os.path.exists(NOTEBOOK_FILE):
            with open(NOTEBOOK_FILE, 'r') as f:
                data = json.load(f)
                print(f"📓 Loaded notebook: {data.get('user_name', 'Unknown')}, {data.get('total_interactions', 0)} interactions")
                return data
    except:
        pass
    return {"user_name": "", "total_interactions": 0}

def save_notebook(notebook):
    try:
        os.makedirs(STORAGE_DIR, exist_ok=True)
        notebook["last_updated"] = datetime.now().isoformat()
        with open(NOTEBOOK_FILE, 'w') as f:
            json.dump(notebook, f, indent=2)
        return True
    except:
        return False

def forget_from_notebook(notebook, query):
    removed = 0
    for key in list(notebook.keys()):
        if query.lower() in str(notebook[key]).lower():
            if key not in ["user_name", "total_interactions", "last_updated"]:
                del notebook[key]
                removed += 1
    return notebook, removed

# ====================================================================
# INITIALIZE RAG MEMORY
# ====================================================================
rag_memory = VectorMemoryStore() if RAG_AVAILABLE and VectorMemoryStore else None

if rag_memory:
    stats = rag_memory.stats()
    print(f"🧠 RAG Memory ready: {stats['total_memories']} memories stored")
else:
    print("⚠️ Running without RAG memory")

# ====================================================================
# SESSION MEMORY
# ====================================================================
session_memory = {"topic": "", "recent_exchanges": []}

def update_session_memory(user_message, ai_response):
    global session_memory
    session_memory["recent_exchanges"].append({"user": user_message[:200], "ai": ai_response[:200]})
    if len(session_memory["recent_exchanges"]) > 4:
        session_memory["recent_exchanges"] = session_memory["recent_exchanges"][-4:]
    if not session_memory["topic"] and session_memory["recent_exchanges"]:
        first_msg = session_memory["recent_exchanges"][0]["user"].lower()
        topics = {"python": "Python", "javascript": "JavaScript", "code": "Programming",
                   "music": "Music", "help": "BETA features", "who": "About BETA"}
        for key, topic in topics.items():
            if key in first_msg:
                session_memory["topic"] = topic
                break
        if not session_memory["topic"]:
            session_memory["topic"] = "General conversation"

def get_session_context():
    global session_memory
    context = ""
    if session_memory["topic"]:
        context += f"Current topic: {session_memory['topic']}\n"
    if session_memory["recent_exchanges"]:
        context += "Recent conversation:\n"
        for ex in session_memory["recent_exchanges"][-3:]:
            context += f"User: {ex['user']}\nBETA: {ex['ai']}\n\n"
    return context.strip()

def clear_session():
    global session_memory
    session_memory = {"topic": "", "recent_exchanges": []}

def get_session_info():
    global session_memory
    return f"**Topic:** {session_memory['topic'] or 'None'}\n**Exchanges:** {len(session_memory['recent_exchanges'])}"

# ====================================================================
# NOTEBOOK DISPLAY
# ====================================================================
def get_notebook_summary(notebook):
    lines = [f"**Name:** {notebook.get('user_name', 'Unknown')}"]
    lines.append(f"**Interactions:** {notebook.get('total_interactions', 0)}")
    if rag_memory:
        stats = rag_memory.stats()
        lines.append(f"**RAG Memories:** {stats['total_memories']}")
    return "\n".join(lines)

# ====================================================================
# API CALL - GROQ PRIMARY, CEREBRAS FALLBACK
# ====================================================================
def call_llm_api(messages, system_prompt, use_vision=False, image_data=None):
    if not GROQ_API_KEY and not CEREBRAS_API_KEY:
        return ErrorResponse.no_api_keys()
    
    api_messages = [{"role": "system", "content": system_prompt}]
    
    if use_vision and image_data:
        api_messages.append({
            "role": "user",
            "content": [
                {"type": "text", "text": messages[-1]["content"] if messages else ""},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_data}"}}
            ]
        })
    else:
        api_messages.extend(messages)
    
    if GROQ_API_KEY:
        try:
            rate_limiter.wait()
            model = GROQ_VISION_MODEL if (use_vision and image_data) else GROQ_MODEL
            r = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
                json={"model": model, "messages": api_messages, "temperature": 0.7, "max_tokens": 1024, "top_p": 0.95},
                timeout=30
            )
            if r.status_code == 200:
                data = r.json()
                if "choices" in data and len(data["choices"]) > 0:
                    return ErrorResponse.success(data["choices"][0]["message"]["content"], "groq")
            elif r.status_code == 429:
                print("⚠️ Groq rate limited, trying Cerebras...")
            else:
                print(f"⚠️ Groq error {r.status_code}")
        except requests.exceptions.Timeout:
            return ErrorResponse.timeout()
        except Exception as e:
            print(f"⚠️ Groq exception: {str(e)[:100]}")
    
    if CEREBRAS_API_KEY:
        try:
            rate_limiter.wait()
            r = requests.post(
                "https://api.cerebras.ai/v1/chat/completions",
                headers={"Authorization": f"Bearer {CEREBRAS_API_KEY}", "Content-Type": "application/json"},
                json={"model": CEREBRAS_MODEL, "messages": api_messages, "temperature": 0.7, "max_tokens": 1024, "top_p": 0.95},
                timeout=30
            )
            if r.status_code == 200:
                data = r.json()
                if "choices" in data and len(data["choices"]) > 0:
                    return ErrorResponse.success(data["choices"][0]["message"]["content"], "cerebras")
            elif r.status_code == 429:
                return ErrorResponse.rate_limit()
            else:
                print(f"⚠️ Cerebras error {r.status_code}")
        except requests.exceptions.Timeout:
            return ErrorResponse.timeout()
        except Exception as e:
            print(f"⚠️ Cerebras exception: {str(e)[:100]}")
    
    return ErrorResponse.general_error("No response from any provider")

# ====================================================================
# MAIN AI FUNCTION - WITH RAG
# ====================================================================
def ask_beta(message, notebook, image_path=None):
    global _introduction_given
    
    # Get RAG context with better search queries
    rag_context = ""
    if rag_memory:
        relevant = rag_memory.search(f"{message}", top_k=3)
        if relevant:
            rag_context = "IMPORTANT - Use this information from past conversations:\n"
            for mem in relevant:
                rag_context += f"• {mem['text'][:300]}\n"
            rag_context += "\nReference this information naturally in your response.\n\n"
            print(f"🧠 RAG found {len(relevant)} relevant memories")
    
    session_context = get_session_context()
    
    full_message = ""
    if session_context:
        full_message += f"[Conversation context]:\n{session_context}\n\n"
    if rag_context:
        full_message += f"[Personal context from past conversations]:\n{rag_context}\n\n"
    full_message += f"[New message]: {message}\n\n"
    full_message += 'After your response, append a JSON block with any new personal facts: {"facts_extracted": {"name": "...", "facts": {...}, "preferences": {...}}}. If nothing new, use empty object.'
    
    if not _introduction_given:
        system_prompt = """You are BETA (Best Everyday Technical Assistant), created by INJAN Technologies.

IMPORTANT: This is our FIRST conversation. Introduce yourself ONCE: "Hi there! I am BETA, the Best Everyday Technical Assistant created by INJAN. How may I help you today?"

After introducing yourself, answer naturally as "Beta". Be helpful, friendly, and concise. Use markdown.

If the user uploaded a document, provide a helpful summary. If they uploaded an image, describe what you see.

CRITICAL: If personal context about the user is provided above, USE IT. Address the user by name if you know it. Reference their preferences and past conversations.

IMPORTANT: After your response, append a JSON block with any new personal facts. Do NOT mention this JSON."""
    else:
        system_prompt = """You are BETA (Best Everyday Technical Assistant), created by INJAN Technologies.

IMPORTANT: Do NOT introduce yourself again. Just answer directly and naturally as "Beta".

Be helpful, friendly, and concise. Use markdown.

If the user uploaded a document, provide a helpful summary. If they uploaded an image, describe what you see.

CRITICAL: If personal context about the user is provided above, USE IT. Address the user by name if you know it. Reference their preferences and past conversations.

IMPORTANT: After your response, append a JSON block with any new personal facts. Do NOT mention this JSON."""
    
    image_data = None
    use_vision = False
    if image_path and is_image_file(image_path):
        image_data = encode_image(image_path)
        if image_data:
            use_vision = True
            full_message = f"[The user has uploaded an image. Please describe it in detail.]\n\n{full_message}"
    
    messages = [{"role": "user", "content": full_message}]
    response, provider = call_llm_api(messages, system_prompt, use_vision, image_data)
    
    if not _introduction_given and response and provider != "none":
        _introduction_given = True
    
    # Extract hidden JSON
    facts_data = None
    if response and provider != "none":
        json_pattern = r'\{\s*"facts_extracted"\s*:.*?\}\s*$'
        json_match = re.search(json_pattern, response, re.DOTALL | re.IGNORECASE)
        if json_match:
            try:
                facts_data = json.loads(json_match.group())
                response = response[:json_match.start()].strip()
                if facts_data.get("facts_extracted"):
                    facts_data = facts_data["facts_extracted"]
            except:
                pass
    
    if provider == "cerebras":
        response += "\n\n*(via Cerebras backup)*"
    elif provider == "none":
        return response, None
    
    return response, facts_data

# ====================================================================
# WEB SEARCH
# ====================================================================
def search_web(query):
    if not SERPER_KEY:
        return ""
    try:
        r = requests.post("https://google.serper.dev/search",
                         json={"q": query, "num": 3},
                         headers={"X-API-KEY": SERPER_KEY}, timeout=10)
        if r.status_code == 200:
            results = r.json().get("organic", [])
            if results:
                txt = "**🔍 Search Results:**\n\n"
                for i, res in enumerate(results[:3], 1):
                    txt += f"**{i}. {res.get('title','')}**\n{res.get('snippet','')[:300]}...\n\n"
                return txt
    except:
        pass
    return ""

# ====================================================================
# MUSIC DESCRIPTION
# ====================================================================
def music_description(prompt):
    system_prompt = "You are a music producer. Create detailed music descriptions."
    messages = [{"role": "user", "content": f"Create a music description for: {prompt}. Include genre, tempo, instruments, mood. Keep under 150 words."}]
    response, _ = call_llm_api(messages, system_prompt)
    return f"🎵 **{prompt}**\n\n{response}"

# ====================================================================
# MAIN CHAT FUNCTION
# ====================================================================
def chat(message, search_on, file_path, notebook):
    if not message and not file_path:
        return "Please type or upload something!", None, notebook, get_session_info(), get_notebook_summary(notebook)
    
    msg = message.lower().strip() if message else ""
    
    # Forget command (RAG + Notebook)
    if msg.startswith("forget "):
        query = msg.replace("forget ", "").strip()
        if rag_memory:
            rag_memory.forget(query)
        notebook, _ = forget_from_notebook(notebook, query)
        save_notebook(notebook)
        return f"✅ Forgotten anything related to '{query}'.", None, notebook, get_session_info(), get_notebook_summary(notebook)
    
    # New conversation
    if msg in ["new conversation", "new chat", "clear conversation", "reset chat"]:
        clear_session()
        global _introduction_given
        _introduction_given = False
        return "🆕 Starting a fresh conversation! (Memories preserved)", None, notebook, get_session_info(), get_notebook_summary(notebook)
    
    # Music commands
    for kw in ["create music", "generate music", "make a song", "compose"]:
        if kw in msg:
            prompt = msg.replace(kw, "").strip() or "ambient electronic"
            resp = music_description(prompt)
            return resp, speak(resp), notebook, get_session_info(), get_notebook_summary(notebook)
    
    # Handle file upload
    image_path = None
    if file_path:
        print(f"📎 File: {file_path}")
        if is_image_file(file_path):
            image_path = file_path
            if not message:
                message = "What's in this image?"
        elif is_document_file(file_path):
            content = read_file(file_path)
            if content and not content.startswith("["):
                if not message:
                    message = f"I've uploaded a document. Please summarize it.\n\n[Document]:\n{content}"
                else:
                    message = f"{message}\n\n[Document]:\n{content}"
    
    # Handle search
    if search_on and not file_path:
        web = search_web(message)
        if web:
            message = f"{message}\n\n{web}"
    
    # Get AI response
    response, facts_data = ask_beta(message, notebook, image_path)
    
    if facts_data:
        print(f"📝 Facts extracted: {json.dumps(facts_data)[:200]}")
    else:
        print(f"📝 No facts extracted from this message")
    
    if response.startswith("❌") or response.startswith("⚠️") or response.startswith("⏰"):
        return response, None, notebook, get_session_info(), get_notebook_summary(notebook)
    
    update_session_memory(message, response)
    
    # Save to RAG memory
    if rag_memory and response:
        saved_count = 0
        
        if len(message) > 5:
            if rag_memory.add(f"User said: {message[:300]}"):
                saved_count += 1
        
        if facts_data:
            if facts_data.get("name"):
                if rag_memory.add(f"User's name is {facts_data['name']}"):
                    saved_count += 1
            if facts_data.get("preferences"):
                for k, v in facts_data["preferences"].items():
                    if rag_memory.add(f"User prefers {k}: {v}"):
                        saved_count += 1
            if facts_data.get("facts"):
                for k, v in facts_data["facts"].items():
                    if rag_memory.add(f"Fact about user: {k} = {v}"):
                        saved_count += 1
        
        print(f"🧠 RAG: {saved_count} new memories saved (total: {rag_memory.stats()['total_memories']})")
    
    # Notebook update (backup)
    if facts_data:
        if facts_data.get("name"):
            notebook["user_name"] = facts_data["name"]
        if facts_data.get("preferences"):
            for k, v in facts_data["preferences"].items():
                notebook[k] = v
    
    notebook["total_interactions"] = notebook.get("total_interactions", 0) + 1
    
    if notebook["total_interactions"] % 5 == 0:
        save_notebook(notebook)
    
    audio = speak(response)
    return response, audio, notebook, get_session_info(), get_notebook_summary(notebook)

# ====================================================================
# CREATE STATIC MANIFEST
# ====================================================================
static_manifest = {
    "name": "B.E.T.A",
    "short_name": "B.E.T.A",
    "description": "Best Everyday Technical Assistant by INJAN Technologies",
    "start_url": "/",
    "display": "standalone",
    "background_color": "#020818",
    "theme_color": "#00e5ff",
    "icons": [
        {
            "src": "/static/beta_icon_192.jpg",
            "sizes": "192x192",
            "type": "image/jpeg",
            "purpose": "any maskable"
        },
        {
            "src": "/static/beta_icon_512.jpg",
            "sizes": "512x512",
            "type": "image/jpeg",
            "purpose": "any maskable"
        }
    ]
}

with open(os.path.join(STATIC_DIR, "manifest.json"), "w") as f:
    json.dump(static_manifest, f, indent=2)

# Create simple service worker
with open(os.path.join(STATIC_DIR, "sw.js"), "w") as f:
    f.write('''
self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", () => clients.claim());
self.addEventListener("fetch", (e) => e.respondWith(fetch(e.request)));
''')

print("📱 PWA files created")

# ====================================================================
# CYBERPUNK BLUE UI CSS (ORIGINAL - UNCHANGED)
# ====================================================================
css = """
@import url('https://fonts.googleapis.com/css2?family=Orbitron:wght@400;700;900&family=Rajdhani:wght@300;400;500;600;700&family=Share+Tech+Mono&display=swap');

.gradio-container {
    background: #020818 !important;
    background-image: 
        radial-gradient(ellipse at 50% 0%, rgba(0, 180, 255, 0.15) 0%, transparent 60%),
        radial-gradient(ellipse at 80% 100%, rgba(0, 140, 255, 0.1) 0%, transparent 40%),
        radial-gradient(ellipse at 20% 50%, rgba(0, 200, 255, 0.08) 0%, transparent 30%),
        linear-gradient(180deg, #020818 0%, #061030 50%, #0a1840 100%) !important;
    font-family: 'Rajdhani', sans-serif !important;
}

.gradio-container::before {
    content: '';
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background-image: 
        linear-gradient(rgba(0, 180, 255, 0.06) 1px, transparent 1px),
        linear-gradient(90deg, rgba(0, 180, 255, 0.06) 1px, transparent 1px);
    background-size: 40px 40px;
    pointer-events: none;
    z-index: 0;
}

.gr-box, .gr-form, .panel, .gr-group {
    background: rgba(8, 18, 40, 0.55) !important;
    backdrop-filter: blur(20px) !important;
    -webkit-backdrop-filter: blur(20px) !important;
    border: 1px solid rgba(0, 200, 255, 0.25) !important;
    border-radius: 16px !important;
    box-shadow: 
        0 8px 32px rgba(0, 0, 0, 0.5),
        0 0 15px rgba(0, 180, 255, 0.08),
        inset 0 1px 0 rgba(255, 255, 255, 0.03) !important;
}

.gr-box:hover, .gr-group:hover {
    border-color: rgba(0, 220, 255, 0.5) !important;
    box-shadow: 
        0 8px 32px rgba(0, 0, 0, 0.5),
        0 0 25px rgba(0, 200, 255, 0.15),
        inset 0 1px 0 rgba(255, 255, 255, 0.05) !important;
}

.chatbot {
    border-radius: 16px !important;
    border: 1px solid rgba(0, 200, 255, 0.25) !important;
    background: rgba(4, 10, 25, 0.45) !important;
    backdrop-filter: blur(15px) !important;
    -webkit-backdrop-filter: blur(15px) !important;
    box-shadow: 
        0 8px 32px rgba(0, 0, 0, 0.5),
        0 0 20px rgba(0, 150, 255, 0.06),
        inset 0 1px 0 rgba(255, 255, 255, 0.02) !important;
    overflow-y: auto !important;
    scroll-behavior: smooth !important;
}

.message.user {
    background: linear-gradient(135deg, rgba(0, 170, 255, 0.35), rgba(0, 120, 220, 0.25)) !important;
    border: 1px solid rgba(0, 200, 255, 0.4) !important;
    border-radius: 18px 18px 4px 18px !important;
    padding: 12px 18px !important;
    color: #e8f4ff !important;
    font-size: 15px !important;
    margin: 8px 0 !important;
    backdrop-filter: blur(10px) !important;
    box-shadow: 0 4px 15px rgba(0, 140, 255, 0.15) !important;
}

.message.bot {
    background: linear-gradient(135deg, rgba(0, 220, 255, 0.2), rgba(0, 140, 220, 0.15)) !important;
    border: 1px solid rgba(0, 220, 255, 0.3) !important;
    border-radius: 18px 18px 18px 4px !important;
    padding: 14px 20px !important;
    color: #d0e8ff !important;
    font-size: 15px !important;
    margin: 8px 0 !important;
    backdrop-filter: blur(10px) !important;
    box-shadow: 0 4px 15px rgba(0, 180, 255, 0.1) !important;
}

input, textarea, .gr-textbox textarea, .gr-textbox input {
    background: rgba(6, 14, 30, 0.75) !important;
    color: #00e5ff !important;
    border: 1px solid rgba(0, 200, 255, 0.35) !important;
    border-radius: 25px !important;
    padding: 12px 20px !important;
    font-size: 15px !important;
    font-family: 'Share Tech Mono', 'Rajdhani', monospace !important;
    transition: all 0.3s ease !important;
    backdrop-filter: blur(10px) !important;
}

input:focus, textarea:focus, .gr-textbox textarea:focus {
    border-color: #00eeff !important;
    box-shadow: 
        0 0 25px rgba(0, 230, 255, 0.4),
        0 0 50px rgba(0, 180, 255, 0.2),
        0 0 75px rgba(0, 140, 255, 0.1) !important;
    outline: none !important;
    animation: glowPulse 2s ease-in-out infinite !important;
}

@keyframes glowPulse {
    0%, 100% { 
        box-shadow: 0 0 25px rgba(0, 230, 255, 0.4), 0 0 50px rgba(0, 180, 255, 0.2);
    }
    50% { 
        box-shadow: 0 0 40px rgba(0, 230, 255, 0.6), 0 0 70px rgba(0, 180, 255, 0.35), 0 0 100px rgba(0, 140, 255, 0.15);
    }
}

button, .gr-button {
    background: linear-gradient(135deg, rgba(0, 130, 220, 0.45), rgba(0, 180, 255, 0.25)) !important;
    border: 1px solid rgba(0, 210, 255, 0.45) !important;
    border-radius: 25px !important;
    color: #00e0ff !important;
    font-weight: 600 !important;
    font-family: 'Orbitron', 'Rajdhani', sans-serif !important;
    letter-spacing: 1px !important;
    padding: 10px 20px !important;
    cursor: pointer !important;
    transition: all 0.3s ease !important;
    backdrop-filter: blur(10px) !important;
    text-transform: uppercase !important;
    font-size: 13px !important;
}

button:hover, .gr-button:hover {
    background: linear-gradient(135deg, rgba(0, 170, 255, 0.55), rgba(0, 220, 255, 0.35)) !important;
    border-color: #00eeff !important;
    box-shadow: 
        0 0 30px rgba(0, 220, 255, 0.5),
        0 0 60px rgba(0, 180, 255, 0.25) !important;
    transform: translateY(-2px) !important;
    color: #ffffff !important;
}

button:active, .gr-button:active {
    transform: scale(0.97) !important;
    transition: transform 0.1s !important;
}

.gr-button-primary, #send_btn {
    background: linear-gradient(135deg, rgba(0, 170, 255, 0.55), rgba(0, 130, 255, 0.35)) !important;
    border-color: rgba(0, 230, 255, 0.6) !important;
    animation: buttonGlow 3s ease-in-out infinite !important;
}

@keyframes buttonGlow {
    0%, 100% { 
        box-shadow: 0 0 20px rgba(0, 220, 255, 0.4), 0 0 40px rgba(0, 160, 255, 0.2);
    }
    50% { 
        box-shadow: 0 0 35px rgba(0, 240, 255, 0.7), 0 0 70px rgba(0, 180, 255, 0.4), 0 0 100px rgba(0, 140, 255, 0.2);
    }
}

.gr-button-primary:hover, #send_btn:hover {
    background: linear-gradient(135deg, rgba(0, 210, 255, 0.65), rgba(0, 170, 255, 0.45)) !important;
}

label, .gr-label {
    color: #00d0f0 !important;
    font-weight: 500 !important;
    text-transform: uppercase !important;
    letter-spacing: 2px !important;
    font-size: 11px !important;
    font-family: 'Orbitron', sans-serif !important;
}

.toggle-btn {
    background: rgba(0, 170, 255, 0.25) !important;
    border: 1px solid rgba(0, 220, 255, 0.4) !important;
    font-size: 20px !important;
    padding: 8px 12px !important;
    min-width: 45px !important;
    border-radius: 12px !important;
    color: #00e8ff !important;
}

#audio_out {
    width: 1px !important;
    height: 1px !important;
    position: absolute !important;
    opacity: 0 !important;
}

.gr-file {
    border: none !important;
    background: transparent !important;
}

.gr-file .wrap {
    border: 2px dashed rgba(0, 200, 255, 0.4) !important;
    border-radius: 50% !important;
    width: 45px !important;
    height: 45px !important;
    display: flex !important;
    align-items: center !important;
    justify-content: center !important;
    transition: all 0.3s ease !important;
    background: rgba(0, 170, 255, 0.08) !important;
}

.gr-file .wrap:hover {
    border-color: #00e8ff !important;
    box-shadow: 0 0 25px rgba(0, 220, 255, 0.4) !important;
    background: rgba(0, 170, 255, 0.15) !important;
}

::-webkit-scrollbar {
    width: 5px;
}

::-webkit-scrollbar-track {
    background: rgba(6, 14, 30, 0.5);
    border-radius: 3px;
}

::-webkit-scrollbar-thumb {
    background: linear-gradient(180deg, #00d8ff, #0080e0);
    border-radius: 3px;
    box-shadow: 0 0 10px rgba(0, 200, 255, 0.4);
}

::-webkit-scrollbar-thumb:hover {
    background: linear-gradient(180deg, #00eeff, #00a0ff);
    box-shadow: 0 0 15px rgba(0, 220, 255, 0.6);
}

.message {
    animation: messageSlideIn 0.25s ease-out !important;
    will-change: transform !important;
    transform: translateZ(0) !important;
}

@keyframes messageSlideIn {
    from {
        opacity: 0;
        transform: translateY(8px);
    }
    to {
        opacity: 1;
        transform: translateY(0);
    }
}

footer {
    display: none !important;
}

.message.bot p, .message.bot h1, .message.bot h2, .message.bot h3,
.message.user p {
    margin: 4px 0 !important;
}

.message.bot code {
    background: rgba(0, 220, 255, 0.12) !important;
    padding: 2px 6px !important;
    border-radius: 4px !important;
    font-family: 'Share Tech Mono', monospace !important;
    color: #00e8ff !important;
}

.chatbot .wrap, .chatbot .messages {
    -webkit-overflow-scrolling: touch !important;
    transform: translateZ(0) !important;
    will-change: scroll-position !important;
}

@media (max-width: 768px) {
    .gradio-container {
        padding: 5px !important;
    }
    
    .message.user, .message.bot {
        font-size: 14px !important;
        padding: 10px 14px !important;
    }
    
    input, textarea {
        font-size: 14px !important;
        padding: 10px 15px !important;
    }
    
    button, .gr-button {
        font-size: 11px !important;
        padding: 8px 14px !important;
    }
    
    .chatbot {
        height: 55vh !important;
        border-radius: 12px !important;
    }
}

.memory-status {
    display: inline-block;
    width: 10px;
    height: 10px;
    background: #00e8ff;
    border-radius: 50%;
    margin-right: 8px;
    animation: statusPulse 2s ease-in-out infinite;
    box-shadow: 0 0 8px #00e8ff, 0 0 16px rgba(0, 220, 255, 0.5);
}

@keyframes statusPulse {
    0%, 100% { 
        opacity: 1; 
        box-shadow: 0 0 8px #00e8ff, 0 0 20px rgba(0, 220, 255, 0.4);
    }
    50% { 
        opacity: 0.6; 
        box-shadow: 0 0 15px #00eeff, 0 0 35px rgba(0, 230, 255, 0.6);
    }
}
"""

# ====================================================================
# ANIMATED LOGO TITLE HTML (ORIGINAL - UNCHANGED)
# ====================================================================
animated_header_html = f"""
<div style="text-align:center;padding:20px 20px 10px 20px;position:relative;z-index:1;">
    <div style="position:relative;display:inline-block;">
        <div style="position:absolute;inset:-5px;border-radius:25px;
                    background:linear-gradient(135deg,#00e8ff,#0060e0,#00e8ff);
                    background-size:200% 200%;
                    animation:logoRingRotate 4s linear infinite;
                    opacity:0.6;filter:blur(8px);"></div>
        <img src="{BETA_LOGO_URL}" alt="BETA Logo" 
             style="width:90px;height:90px;border-radius:22px;object-fit:cover;
                    box-shadow:0 0 35px rgba(0,220,255,0.7),0 0 70px rgba(0,160,255,0.35);
                    border:2px solid rgba(0,220,255,0.6);display:block;margin:0 auto;
                    position:relative;z-index:1;
                    animation: logoFloat 3s ease-in-out infinite;">
    </div>
    <h1 style="font-family:'Orbitron',sans-serif;font-size:2.4em;
               background:linear-gradient(135deg,#00eeff 0%,#00a0ff 30%,#00eeff 60%,#0060ff 100%);
               background-size:200% auto;
               -webkit-background-clip:text;background-clip:text;
               color:transparent;margin:10px 0 2px 0;
               letter-spacing:5px;
               animation: titleShine 3s linear infinite;
               filter:drop-shadow(0 0 15px rgba(0,200,255,0.5));">
        ⚡ B.E.T.A ⚡
    </h1>
    <p style="color:#00d0f0;font-size:13px;font-family:'Rajdhani',sans-serif;
              letter-spacing:3px;text-transform:uppercase;margin:0;
              text-shadow:0 0 10px rgba(0,200,255,0.4);">
        Best Everyday Technical Assistant
    </p>
    <p style="color:#6080c0;font-size:10px;font-family:'Share Tech Mono',monospace;margin:2px 0;
              letter-spacing:1px;">
        INJAN STUDIO
    </p>
    <div style="margin-top:6px;">
        <span class="memory-status"></span>
        <span style="color:#00c8f0;font-size:10px;font-family:'Share Tech Mono',monospace;
                     text-shadow:0 0 8px rgba(0,200,255,0.3);">
            RAG MEMORY ACTIVE
        </span>
    </div>
</div>

<style>
@keyframes logoRingRotate {{
    0% {{ background-position:0% 50%; }}
    50% {{ background-position:100% 50%; }}
    100% {{ background-position:0% 50%; }}
}}

@keyframes logoFloat {{
    0%, 100% {{ transform:translateY(0px); }}
    50% {{ transform:translateY(-5px); }}
}}

@keyframes titleShine {{
    0% {{ background-position:0% center; }}
    100% {{ background-position:200% center; }}
}}
</style>
"""

# ====================================================================
# INTERFACE (ORIGINAL - UNCHANGED except PWA head)
# ====================================================================
notebook = load_notebook()

# Create Gradio app with PWA support
demo = gr.Blocks(
    title="B.E.T.A",
    css=css,
    theme=gr.themes.Soft(),
    head=f"""
    <!-- PWA Support -->
    <link rel="manifest" href="/static/manifest.json">
    <meta name="theme-color" content="#00e5ff">
    <meta name="apple-mobile-web-app-capable" content="yes">
    <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
    <meta name="apple-mobile-web-app-title" content="B.E.T.A">
    <link rel="apple-touch-icon" sizes="192x192" href="{ICON_192_PATH}">
    <link rel="apple-touch-icon" sizes="512x512" href="{ICON_512_PATH}">
    <link rel="icon" type="image/jpeg" sizes="192x192" href="{ICON_192_PATH}">
    <link rel="icon" type="image/jpeg" sizes="512x512" href="{ICON_512_PATH}">
    <meta name="msapplication-TileImage" content="{ICON_512_PATH}">
    <meta name="msapplication-TileColor" content="#00e5ff">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <script>
        if ('serviceWorker' in navigator) {{
            navigator.serviceWorker.register('/static/sw.js');
        }}
    </script>
    """
)

with demo:
    # Animated Header
    gr.HTML(animated_header_html)
    
    with gr.Row(equal_height=False):
        with gr.Column(scale=0, min_width=55):
            toggle_btn = gr.Button("☰", elem_classes="toggle-btn", variant="primary")
            sidebar_visible = gr.State(True)
        
        with gr.Column(scale=1, elem_id="sidebar_column", visible=True) as sidebar_column:
            with gr.Group():
                gr.Markdown("### 💬 SESSION")
                session_info = gr.Markdown(get_session_info())
                new_chat_btn = gr.Button("🆕 New Conversation", size="sm")
                
                gr.Markdown("---")
                gr.Markdown("### 🧠 MEMORY")
                notebook_info = gr.Markdown(get_notebook_summary(notebook))
                
                with gr.Row():
                    forget_input = gr.Textbox(placeholder="What to forget...", lines=1, scale=2, show_label=False)
                    forget_btn = gr.Button("🗑️ Forget", size="sm", scale=1)
                
                clear_memory_btn = gr.Button("🧹 Clear All Memories", size="sm")
        
        with gr.Column(scale=3):
            chatbot = gr.Chatbot(height=480, show_label=False, elem_classes="chatbot")
            
            with gr.Row(equal_height=True):
                msg = gr.Textbox(placeholder="⌨️ Type your message here... [Enter to send]", lines=1, scale=5, show_label=False, container=True)
                file_upload = gr.File(label="", file_count="single", scale=0, min_width=45, elem_id="file_upload_btn")
            
            with gr.Row():
                send_btn = gr.Button("⚡ SEND", variant="primary", scale=3, elem_id="send_btn")
                search_btn = gr.Button("🔍 SEARCH: OFF", variant="secondary", scale=1)
            
            audio_out = gr.Audio(type="filepath", autoplay=True, visible=True, show_label=False, elem_id="audio_out")
    
    search_state = gr.State(False)
    notebook_state = gr.State(notebook)
    
    def toggle_search(state):
        new_state = not state
        return new_state, gr.update(value="🔍 ONLINE SEARCH: ON" if new_state else "🔍 ONLINE SEARCH: OFF", variant="primary" if new_state else "secondary")
    
    def toggle_sidebar(visible):
        return not visible, gr.update(visible=not visible)
    
    def respond(message, chat_history, search_on, file_path, nb):
        if not message and not file_path:
            return chat_history, None, "", nb, get_session_info(), get_notebook_summary(nb)
        response, audio, nb, session, note_summary = chat(message or "Analyze this", search_on, file_path, nb)
        chat_history = chat_history or []
        chat_history.append({"role": "user", "content": message or "[File uploaded]"})
        chat_history.append({"role": "assistant", "content": response})
        return chat_history, audio, "", nb, session, note_summary
    
    def new_conversation(nb):
        clear_session()
        global _introduction_given
        _introduction_given = False
        return [], None, "", nb, get_session_info(), get_notebook_summary(nb)
    
    def forget_command(query, nb):
        if not query:
            return nb, get_notebook_summary(nb)
        if rag_memory:
            rag_memory.forget(query)
        nb, _ = forget_from_notebook(nb, query)
        save_notebook(nb)
        return nb, get_notebook_summary(nb)
    
    def clear_all_memories(nb):
        if rag_memory:
            rag_memory.clear()
        nb = {"user_name": "", "total_interactions": 0}
        save_notebook(nb)
        clear_session()
        global _introduction_given
        _introduction_given = False
        return nb, get_notebook_summary(nb), get_session_info()
    
    toggle_btn.click(toggle_sidebar, [sidebar_visible], [sidebar_visible, sidebar_column])
    search_btn.click(toggle_search, [search_state], [search_state, search_btn])
    msg.submit(respond, [msg, chatbot, search_state, file_upload, notebook_state], [chatbot, audio_out, msg, notebook_state, session_info, notebook_info])
    send_btn.click(respond, [msg, chatbot, search_state, file_upload, notebook_state], [chatbot, audio_out, msg, notebook_state, session_info, notebook_info])
    file_upload.upload(respond, [msg, chatbot, search_state, file_upload, notebook_state], [chatbot, audio_out, msg, notebook_state, session_info, notebook_info])
    new_chat_btn.click(new_conversation, [notebook_state], [chatbot, audio_out, msg, notebook_state, session_info, notebook_info])
    forget_btn.click(forget_command, [forget_input, notebook_state], [notebook_state, notebook_info])
    clear_memory_btn.click(clear_all_memories, [notebook_state], [notebook_state, notebook_info, session_info])

# ====================================================================
# MOUNT STATIC FILES TO FASTAPI APP
# ====================================================================
app = demo.app

# Mount static directory
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# Add route for manifest
@app.get("/static/manifest.json")
async def serve_manifest():
    return FileResponse(os.path.join(STATIC_DIR, "manifest.json"), media_type="application/manifest+json")

# Add route for service worker
@app.get("/static/sw.js")
async def serve_sw():
    return FileResponse(os.path.join(STATIC_DIR, "sw.js"), media_type="application/javascript")

print("\n" + "=" * 60)
print("🚀 BETA 6.5 - CYBERPUNK EDITION (PWA FIXED)")
print("💎 Glass Morphism | 🔵 Vibrant Blue Theme")
print("🗣️ Smooth Natural Speech | 📱 Mobile Optimized")
print("✨ Animated Logo | 🧠 RAG Memory")
print("🖼️ Custom PWA Icons ENABLED")
print(f"💾 Storage: {STORAGE_DIR}")
print("=" * 60 + "\n")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 7860))
    demo.launch(server_name="0.0.0.0", server_port=port, show_error=True)