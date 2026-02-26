"""
LADX - Web Application
================================
Run with: python web_app.py
Then open: http://localhost:8000
"""

import os
import httpx
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from typing import Optional

from config import HOST, PORT, TIA_BRIDGE_URL, OUTPUT_DIR
from plc_agent import PLCAgent

# ===========================================
# Initialize
# ===========================================
app = FastAPI(title="LADX", version="1.0.0")

# Templates
templates = Jinja2Templates(directory="web/templates")

# Static files (if you add CSS/JS files later)
static_dir = Path("web/static")
static_dir.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory="web/static"), name="static")

# Agent instance (one per server for now)
agent = PLCAgent()


# ===========================================
# Request Models
# ===========================================
class ChatRequest(BaseModel):
    message: str
    platform: str = "siemens"


# ===========================================
# Routes
# ===========================================

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """Serve the main chat interface."""
    return templates.TemplateResponse("index.html", {"request": request})


@app.post("/api/chat")
async def chat(req: ChatRequest):
    """Handle chat messages from the web interface."""
    try:
        # Prepend platform context to the message
        platform_prefix = f"[Target Platform: {req.platform}] "
        full_message = platform_prefix + req.message

        # Get response from agent
        response = agent.chat(full_message)

        # Check if any files were saved
        files_saved = []
        output_dir = OUTPUT_DIR
        if output_dir.exists():
            # Get files modified in the last 10 seconds
            import time
            now = time.time()
            for f in output_dir.iterdir():
                if f.is_file() and (now - f.stat().st_mtime) < 10:
                    files_saved.append(f.name)

        return JSONResponse({
            "response": response,
            "files_saved": files_saved,
            "history_length": agent.get_history_length()
        })

    except Exception as e:
        return JSONResponse(
            {"error": str(e)},
            status_code=500
        )


@app.post("/api/reset")
async def reset_chat():
    """Clear conversation history."""
    agent.reset()
    return JSONResponse({"status": "ok", "message": "Chat history cleared"})


@app.get("/api/bridge-status")
async def bridge_status():
    """Check if the TIA Portal bridge is reachable."""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{TIA_BRIDGE_URL}/api/status",
                timeout=3.0
            )
            return JSONResponse({
                "connected": True,
                "details": response.json()
            })
    except Exception:
        return JSONResponse({
            "connected": False,
            "details": "Bridge not reachable"
        })


@app.get("/api/output-files")
async def list_output_files():
    """List all generated files in the output directory."""
    files = []
    if OUTPUT_DIR.exists():
        for f in sorted(OUTPUT_DIR.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True):
            if f.is_file():
                files.append({
                    "name": f.name,
                    "size": f.stat().st_size,
                    "modified": f.stat().st_mtime
                })
    return JSONResponse({"files": files})


@app.get("/api/output-files/{filename}")
async def get_output_file(filename: str):
    """Download a generated file."""
    filepath = OUTPUT_DIR / filename
    if filepath.exists() and filepath.is_file():
        content = filepath.read_text(encoding="utf-8")
        return JSONResponse({"filename": filename, "content": content})
    return JSONResponse({"error": "File not found"}, status_code=404)


# ===========================================
# Run Server
# ===========================================

if __name__ == "__main__":
    import uvicorn

    print("=" * 60)
    print("  LADX - Web Interface")
    print(f"  Open in browser: http://localhost:{PORT}")
    print("=" * 60)

    uvicorn.run(
        "web_app:app",
        host=HOST,
        port=PORT,
        reload=True
    )
