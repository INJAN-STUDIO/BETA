from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import os

# Create the FastAPI app
app = FastAPI(title="B.E.T.A. System")

# Mount the static directory to serve HTML/CSS/JS
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
async def read_index():
    return FileResponse("static/index.html")

# Root route for API health check
@app.get("/api/health")
async def health():
    return {"status": "online", "system": "B.E.T.A ready"}

# We will add modular route imports here later:
# from app.routes import chat
# app.include_router(chat.router)
