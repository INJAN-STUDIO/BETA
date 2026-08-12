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
    # Using an absolute path to ensure Render finds the file correctly
    file_path = os.path.join(os.path.dirname(__file__), "static", "index.html")
    return FileResponse(file_path)

# Root route for API health check
@app.get("/api/health")
async def health():
    return {"status": "online", "system": "B.E.T.A ready"}
