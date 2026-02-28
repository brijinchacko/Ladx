"""
LADX - Web Application
================================
Run with: python web_app.py
Then open: http://localhost:8000
"""

import time
import httpx
from datetime import datetime
from pathlib import Path
from fastapi import FastAPI, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from typing import Optional
from sqlalchemy.orm import Session

from config import HOST, PORT, TIA_BRIDGE_URL, OUTPUT_DIR
from plc_agent import PLCAgent
from db.database import init_db, get_db
from db.models import User, Conversation, Message
from auth.dependencies import get_current_user
from auth.rate_limiter import check_rate_limit, increment_usage, get_allowed_features
from routes.auth import router as auth_router
from routes.conversations import router as conversations_router

# ===========================================
# Initialize
# ===========================================
app = FastAPI(title="LADX", version="2.0.0")

# Mount route modules
app.include_router(auth_router)
app.include_router(conversations_router)

# Templates
templates = Jinja2Templates(directory="web/templates")

# Static files
static_dir = Path("web/static")
static_dir.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory="web/static"), name="static")

# Uploads directory
uploads_dir = Path("uploads")
uploads_dir.mkdir(parents=True, exist_ok=True)

# Per-user agent instances: {user_id: {"agent": PLCAgent, "last_used": timestamp}}
agents = {}
AGENT_TIMEOUT = 1800  # 30 minutes


def get_agent(user_id: int, conversation_id: int = None, db: Session = None) -> PLCAgent:
    """Get or create a PLCAgent instance for a user."""
    key = f"{user_id}_{conversation_id}" if conversation_id else str(user_id)

    if key in agents:
        agents[key]["last_used"] = time.time()
        return agents[key]["agent"]

    # Create new agent
    agent = PLCAgent()

    # Load conversation history from DB if resuming
    if conversation_id and db:
        messages = (
            db.query(Message)
            .filter(Message.conversation_id == conversation_id)
            .order_by(Message.created_at)
            .all()
        )
        for msg in messages:
            agent.conversation_history.append({
                "role": msg.role,
                "content": msg.content,
            })

    agents[key] = {"agent": agent, "last_used": time.time()}
    return agent


def cleanup_agents():
    """Remove agent instances that haven't been used in 30 minutes."""
    now = time.time()
    expired = [k for k, v in agents.items() if now - v["last_used"] > AGENT_TIMEOUT]
    for k in expired:
        del agents[k]


# ===========================================
# Request Models
# ===========================================
class ChatRequest(BaseModel):
    message: str
    platform: str = "siemens"
    conversation_id: Optional[int] = None
    model: Optional[str] = None
    stage_context: Optional[str] = None


# ===========================================
# Startup
# ===========================================
@app.on_event("startup")
async def startup():
    init_db()
    print("[LADX] Database initialized.")


# ===========================================
# Public Routes
# ===========================================

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """Serve the main chat interface."""
    return templates.TemplateResponse("index.html", {"request": request})


# ===========================================
# Protected Routes (require JWT)
# ===========================================

@app.post("/api/chat")
async def chat(
    req: ChatRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Handle chat messages - protected, rate-limited, persisted."""
    try:
        # Check rate limit
        rate_info = check_rate_limit(db, user.id, user.tier)
        if not rate_info["allowed"]:
            return JSONResponse(
                {
                    "error": f"Daily message limit reached ({rate_info['limit']} messages). Upgrade your plan for more.",
                    "rate_limit": rate_info,
                },
                status_code=429,
            )

        # Create conversation if needed
        conversation_id = req.conversation_id
        if not conversation_id:
            convo = Conversation(
                user_id=user.id,
                title=req.message[:50] + ("..." if len(req.message) > 50 else ""),
                platform=req.platform,
            )
            db.add(convo)
            db.commit()
            db.refresh(convo)
            conversation_id = convo.id
        else:
            # Verify ownership
            convo = db.query(Conversation).filter(
                Conversation.id == conversation_id,
                Conversation.user_id == user.id,
            ).first()
            if not convo:
                return JSONResponse({"error": "Conversation not found"}, status_code=404)

        # Get agent for this user/conversation
        cleanup_agents()
        agent = get_agent(user.id, conversation_id, db)

        # Set model override if specified
        if req.model:
            agent.model_override = req.model

        # Filter tools based on tier
        allowed_features = get_allowed_features(user.tier)

        # Build context-aware message with project hardware info
        context_parts = [f"[Target Platform: {req.platform}]"]
        if convo:
            if convo.cpu_model:
                context_parts.append(f"[CPU: {convo.cpu_model}")
                if convo.cpu_variant:
                    context_parts[-1] += f" {convo.cpu_variant}"
                context_parts[-1] += "]"
            if convo.software_version:
                context_parts.append(f"[TIA Portal: {convo.software_version}]")
            if convo.network_type:
                context_parts.append(f"[Network: {convo.network_type}]")
            if getattr(convo, 'safety_required', False):
                context_parts.append("[Safety: F-CPU Required]")
            if getattr(convo, 'io_modules', None):
                try:
                    import json
                    modules = json.loads(convo.io_modules) if isinstance(convo.io_modules, str) else convo.io_modules
                    if modules:
                        context_parts.append(f"[IO Modules: {', '.join(modules)}]")
                except Exception:
                    pass
            if convo.current_stage:
                context_parts.append(f"[Stage: {convo.current_stage}]")
        full_message = " ".join(context_parts) + " " + req.message

        # Save user message to DB
        user_msg = Message(
            conversation_id=conversation_id,
            role="user",
            content=req.message,
        )
        db.add(user_msg)

        # Get response from agent
        response = agent.chat(full_message)

        # Save assistant response to DB
        assistant_msg = Message(
            conversation_id=conversation_id,
            role="assistant",
            content=response,
        )
        db.add(assistant_msg)

        # Update conversation timestamp
        convo = db.query(Conversation).filter(Conversation.id == conversation_id).first()
        if convo:
            convo.updated_at = datetime.utcnow()

        # Increment usage
        increment_usage(db, user.id)
        db.commit()

        # Check for saved files
        files_saved = []
        if OUTPUT_DIR.exists():
            now = time.time()
            for f in OUTPUT_DIR.iterdir():
                if f.is_file() and (now - f.stat().st_mtime) < 10:
                    files_saved.append(f.name)

        # Get updated usage
        updated_rate = check_rate_limit(db, user.id, user.tier)

        return JSONResponse({
            "response": response,
            "conversation_id": conversation_id,
            "files_saved": files_saved,
            "usage": updated_rate,
        })

    except Exception as e:
        return JSONResponse({"error": f"Error calling AI: {e}"}, status_code=500)


@app.post("/api/reset")
async def reset_chat(
    user: User = Depends(get_current_user),
):
    """Clear the current agent's conversation history."""
    # Remove all agents for this user
    expired = [k for k in agents if k.startswith(str(user.id))]
    for k in expired:
        del agents[k]
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


# ===========================================
# TIA Portal Proxy Endpoints
# ===========================================

async def _tia_proxy(method: str, endpoint: str, json_data: dict = None, timeout: float = 60.0):
    """Proxy a request to the TIA Bridge server."""
    try:
        async with httpx.AsyncClient() as client:
            if method == "GET":
                resp = await client.get(f"{TIA_BRIDGE_URL}{endpoint}", timeout=timeout)
            else:
                resp = await client.post(f"{TIA_BRIDGE_URL}{endpoint}", json=json_data or {}, timeout=timeout)
            return JSONResponse(resp.json())
    except (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout, httpx.TimeoutException, OSError):
        # Bridge not reachable - return offline status (not a 500 error)
        return JSONResponse({
            "success": False,
            "bridge": "offline",
            "dll_loaded": False,
            "tia_portal_connected": False,
            "project_open": False,
            "project_name": None,
            "message": f"Cannot reach TIA Bridge at {TIA_BRIDGE_URL}. Is tia_bridge_server.py running on Windows?"
        })
    except Exception as e:
        return JSONResponse({
            "success": False,
            "bridge": "error",
            "dll_loaded": False,
            "tia_portal_connected": False,
            "project_open": False,
            "message": f"Bridge error: {str(e)}"
        })


@app.get("/api/tia/status")
async def tia_status():
    """Get TIA Portal bridge and connection status."""
    return await _tia_proxy("GET", "/api/status", timeout=5.0)


@app.post("/api/tia/connect")
async def tia_connect(request: Request):
    """Connect to or launch TIA Portal."""
    data = await request.json() if request.headers.get("content-type") == "application/json" else {}
    return await _tia_proxy("POST", "/api/connect", data, timeout=120.0)


@app.post("/api/tia/disconnect")
async def tia_disconnect():
    """Disconnect from TIA Portal."""
    return await _tia_proxy("POST", "/api/disconnect")


@app.post("/api/tia/create-project")
async def tia_create_project(request: Request):
    """Create a new TIA Portal project."""
    data = await request.json()
    return await _tia_proxy("POST", "/api/create-project", data, timeout=120.0)


@app.post("/api/tia/open-project")
async def tia_open_project(request: Request):
    """Open an existing TIA Portal project."""
    data = await request.json()
    return await _tia_proxy("POST", "/api/open-project", data, timeout=60.0)


@app.get("/api/tia/project-info")
async def tia_project_info():
    """Get current TIA Portal project details."""
    return await _tia_proxy("GET", "/api/project-info")


@app.post("/api/tia/configure-hardware")
async def tia_configure_hardware(request: Request):
    """Configure PLC hardware (IO modules, network)."""
    data = await request.json()
    return await _tia_proxy("POST", "/api/configure-hardware", data)


@app.post("/api/tia/import-scl")
async def tia_import_scl(request: Request):
    """Import SCL code into TIA Portal."""
    data = await request.json()
    return await _tia_proxy("POST", "/api/import-scl", data)


@app.post("/api/tia/import-xml")
async def tia_import_xml(request: Request):
    """Import XML block (LAD/FBD) into TIA Portal."""
    data = await request.json()
    return await _tia_proxy("POST", "/api/import-xml", data)


@app.post("/api/tia/compile")
async def tia_compile():
    """Compile the TIA Portal project."""
    return await _tia_proxy("POST", "/api/compile", timeout=180.0)


@app.post("/api/tia/download")
async def tia_download(request: Request):
    """Download program to PLC."""
    data = await request.json()
    return await _tia_proxy("POST", "/api/download", data, timeout=120.0)


@app.post("/api/tia/go-online")
async def tia_go_online(request: Request):
    """Go online with PLC."""
    data = await request.json()
    return await _tia_proxy("POST", "/api/go-online", data)


@app.get("/api/tia/list-blocks")
async def tia_list_blocks():
    """List all program blocks in TIA Portal project."""
    return await _tia_proxy("GET", "/api/list-blocks")


@app.get("/api/tia/logs")
async def tia_logs():
    """Get bridge log entries."""
    return await _tia_proxy("GET", "/api/logs")


@app.get("/api/output-files")
async def list_output_files(user: User = Depends(get_current_user)):
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
async def get_output_file(filename: str, user: User = Depends(get_current_user)):
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
