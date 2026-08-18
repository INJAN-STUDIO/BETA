from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
import os
from brain_logic import brain  # Import from brain_logic instead of app

# Create the FastAPI app
app = FastAPI(title="B.E.T.A. Backend")

# Mount the static directory
STATIC_DIR = os.path.join(os.getcwd(), "static")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

@app.get("/")
async def read_index():
    return FileResponse("static/index.html")

# New API endpoint for the chat
@app.post("/api/chat")
async def chat_endpoint(request: Request):
    data = await request.json()
    user_message = data.get("message", "")
    show_thinking = bool(data.get("show_thinking", False))
    
    if not user_message:
        return JSONResponse({"error": "No message provided"}, status_code=400)
    
    # Call the brain
    result = await brain.chat(user_message, show_thinking=show_thinking)
    
    return JSONResponse(result)

# Root route for API health check
@app.get("/api/health")
async def health():
    return {"status": "online", "system": "B.E.T.A brain active"}
