"""
LADX - Project Lifecycle Routes
CRUD for projects, stage management, hardware config, document generation, and file uploads.
"""

import os
import json
import traceback
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import Optional, List
from db.database import get_db
from db.models import (
    User, Conversation, Message, ProjectDocument, ProjectStage,
    GeneratedDocument, STAGE_ORDER, STAGE_LABELS,
)
from auth.dependencies import get_current_user
from auth.rate_limiter import check_conversation_limit
from config import SIEMENS_CPU_MODELS, TIA_PORTAL_VERSIONS, IO_MODULE_TYPES, NETWORK_TYPES

router = APIRouter(prefix="/api/conversations", tags=["conversations"])

UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "uploads")
MAX_FILE_SIZE = 10 * 1024 * 1024
ALLOWED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".gif", ".txt", ".csv", ".stl", ".xml", ".json", ".scl"}


# ============================================================
# Schemas
# ============================================================

class ProjectCreate(BaseModel):
    title: str = "New Project"
    software_version: str = "V18"
    cpu_model: str = "S7-1500"
    cpu_variant: Optional[str] = None
    network_type: str = "PROFINET"
    safety_required: bool = False
    description: Optional[str] = None
    architecture_notes: Optional[str] = None
    io_modules: Optional[List[str]] = None


class ProjectUpdate(BaseModel):
    title: Optional[str] = None
    software_version: Optional[str] = None
    description: Optional[str] = None
    cpu_model: Optional[str] = None
    cpu_variant: Optional[str] = None
    network_type: Optional[str] = None
    safety_required: Optional[bool] = None
    architecture_notes: Optional[str] = None
    io_modules: Optional[List[str]] = None


class GenerateRequest(BaseModel):
    prompt: Optional[str] = None  # Extra user instructions


class HardwareUpdate(BaseModel):
    cpu_model: Optional[str] = None
    cpu_variant: Optional[str] = None
    software_version: Optional[str] = None
    network_type: Optional[str] = None
    safety_required: Optional[bool] = None
    io_modules: Optional[List[str]] = None
    architecture_notes: Optional[str] = None


# ============================================================
# Helpers
# ============================================================

def _convo_owner(db: Session, conversation_id: int, user_id: int) -> Conversation:
    convo = (
        db.query(Conversation)
        .filter(Conversation.id == conversation_id, Conversation.user_id == user_id)
        .first()
    )
    if not convo:
        raise HTTPException(status_code=404, detail="Project not found")
    return convo


def _init_stages(db: Session, convo: Conversation):
    """Create initial stage records for a new project."""
    for i, stage_name in enumerate(STAGE_ORDER):
        status = "active" if i == 0 else "pending"
        started = datetime.utcnow() if i == 0 else None
        stage = ProjectStage(
            conversation_id=convo.id,
            stage_name=stage_name,
            status=status,
            started_at=started,
        )
        db.add(stage)
    db.commit()


def _stage_dict(stage: ProjectStage) -> dict:
    return {
        "stage_name": stage.stage_name,
        "label": STAGE_LABELS.get(stage.stage_name, stage.stage_name),
        "status": stage.status,
        "started_at": stage.started_at.isoformat() if stage.started_at else None,
        "completed_at": stage.completed_at.isoformat() if stage.completed_at else None,
    }


def _gendoc_dict(d: GeneratedDocument) -> dict:
    return {
        "id": d.id,
        "doc_type": d.doc_type,
        "stage": d.stage,
        "title": d.title,
        "version": d.version,
        "generated_at": d.generated_at.isoformat() if d.generated_at else None,
        "has_content": d.content is not None and len(d.content) > 0,
        "has_docx": d.filepath is not None and os.path.exists(d.filepath) if d.filepath else False,
    }


# ============================================================
# Config endpoint (frontend needs hardware options)
# ============================================================

@router.get("/siemens-options")
async def get_siemens_options():
    """Return available Siemens hardware options for frontend dropdowns."""
    return {
        "cpu_models": {k: {"name": v["name"], "variants": v["variants"], "description": v["description"]}
                       for k, v in SIEMENS_CPU_MODELS.items()},
        "tia_versions": TIA_PORTAL_VERSIONS,
        "network_types": NETWORK_TYPES,
        "io_module_types": IO_MODULE_TYPES,
    }


# ============================================================
# Project CRUD
# ============================================================

@router.get("")
async def list_conversations(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    archived: bool = False,
):
    convos = (
        db.query(Conversation)
        .filter(Conversation.user_id == user.id, Conversation.is_archived == archived)
        .order_by(Conversation.updated_at.desc())
        .all()
    )
    return [
        {
            "id": c.id,
            "title": c.title,
            "platform": c.platform,
            "cpu_model": c.cpu_model,
            "software_version": c.software_version,
            "current_stage": c.current_stage,
            "created_at": c.created_at.isoformat(),
            "updated_at": c.updated_at.isoformat(),
            "message_count": len(c.messages),
            "document_count": len(c.documents),
        }
        for c in convos
    ]


@router.post("")
async def create_conversation(
    req: ProjectCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not check_conversation_limit(db, user.id, user.tier):
        raise HTTPException(status_code=403, detail=f"Project limit reached for {user.tier} tier.")

    convo = Conversation(
        user_id=user.id,
        title=req.title,
        platform="siemens",
        software_version=req.software_version,
        description=req.description,
        cpu_model=req.cpu_model,
        cpu_variant=req.cpu_variant,
        network_type=req.network_type,
        safety_required=req.safety_required,
        architecture_notes=req.architecture_notes,
        io_modules=json.dumps(req.io_modules) if req.io_modules else None,
        current_stage="planning",
    )
    db.add(convo)
    db.commit()
    db.refresh(convo)

    # Initialize stage records
    _init_stages(db, convo)

    return {
        "id": convo.id,
        "title": convo.title,
        "current_stage": convo.current_stage,
        "created_at": convo.created_at.isoformat(),
    }


@router.get("/{conversation_id}")
async def get_conversation(
    conversation_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    convo = _convo_owner(db, conversation_id, user.id)
    return {
        "id": convo.id,
        "title": convo.title,
        "platform": convo.platform,
        "software_version": convo.software_version,
        "description": convo.description,
        "current_stage": convo.current_stage,
        "cpu_model": convo.cpu_model,
        "cpu_variant": convo.cpu_variant,
        "network_type": convo.network_type,
        "safety_required": convo.safety_required,
        "io_modules": json.loads(convo.io_modules) if convo.io_modules else [],
        "architecture_notes": convo.architecture_notes,
        "created_at": convo.created_at.isoformat(),
        "updated_at": convo.updated_at.isoformat(),
        "messages": [
            {"id": m.id, "role": m.role, "content": m.content, "created_at": m.created_at.isoformat()}
            for m in convo.messages
        ],
        "documents": [
            {"id": d.id, "filename": d.filename, "file_type": d.file_type,
             "file_size": d.file_size, "uploaded_at": d.uploaded_at.isoformat() if d.uploaded_at else None}
            for d in convo.documents
        ],
    }


@router.put("/{conversation_id}")
async def update_conversation(
    conversation_id: int,
    req: ProjectUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    convo = _convo_owner(db, conversation_id, user.id)

    for field in ["title", "software_version", "description", "cpu_model", "cpu_variant",
                  "network_type", "architecture_notes"]:
        val = getattr(req, field, None)
        if val is not None:
            setattr(convo, field, val)
    if req.safety_required is not None:
        convo.safety_required = req.safety_required
    if req.io_modules is not None:
        convo.io_modules = json.dumps(req.io_modules)

    convo.updated_at = datetime.utcnow()
    db.commit()
    return {"status": "ok"}


@router.delete("/{conversation_id}")
async def archive_conversation(
    conversation_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    convo = _convo_owner(db, conversation_id, user.id)
    convo.is_archived = True
    db.commit()
    return {"message": "Project archived"}


# ============================================================
# Lifecycle Dashboard
# ============================================================

@router.get("/{conversation_id}/dashboard")
async def get_project_dashboard(
    conversation_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    convo = _convo_owner(db, conversation_id, user.id)

    messages = convo.messages
    user_msgs = [m for m in messages if m.role == "user"]
    assistant_msgs = [m for m in messages if m.role == "assistant"]

    code_blocks = sum(m.content.count("```") for m in assistant_msgs) // 2
    total_doc_size = sum(d.file_size or 0 for d in convo.documents)

    # Build stage info
    stages_info = []
    for s in convo.stages:
        stages_info.append(_stage_dict(s))
    if not stages_info:
        # Backwards compat: init stages if missing
        _init_stages(db, convo)
        for s in convo.stages:
            stages_info.append(_stage_dict(s))

    # Generated docs grouped by stage
    gen_docs = {}
    for d in convo.generated_docs:
        gen_docs.setdefault(d.stage, []).append(_gendoc_dict(d))

    return {
        "project": {
            "id": convo.id,
            "title": convo.title,
            "software_version": convo.software_version,
            "description": convo.description,
            "current_stage": convo.current_stage,
            "cpu_model": convo.cpu_model,
            "cpu_variant": convo.cpu_variant,
            "network_type": convo.network_type,
            "safety_required": convo.safety_required,
            "io_modules": json.loads(convo.io_modules) if convo.io_modules else [],
            "architecture_notes": convo.architecture_notes,
            "has_fds": convo.fds_content is not None and len(convo.fds_content or "") > 0,
            "has_io_list": convo.io_list_content is not None and len(convo.io_list_content or "") > 0,
            "created_at": convo.created_at.isoformat(),
            "updated_at": convo.updated_at.isoformat(),
        },
        "stages": stages_info,
        "generated_docs": gen_docs,
        "stats": {
            "total_messages": len(messages),
            "user_messages": len(user_msgs),
            "assistant_messages": len(assistant_msgs),
            "code_blocks": code_blocks,
            "document_count": len(convo.documents),
            "total_doc_size": total_doc_size,
        },
        "uploaded_documents": [
            {"id": d.id, "filename": d.filename, "file_type": d.file_type,
             "file_size": d.file_size, "uploaded_at": d.uploaded_at.isoformat() if d.uploaded_at else None}
            for d in convo.documents
        ],
    }


# ============================================================
# Hardware Config
# ============================================================

@router.put("/{conversation_id}/hardware")
async def update_hardware(
    conversation_id: int,
    req: HardwareUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    convo = _convo_owner(db, conversation_id, user.id)
    for field in ["cpu_model", "cpu_variant", "software_version", "network_type", "architecture_notes"]:
        val = getattr(req, field, None)
        if val is not None:
            setattr(convo, field, val)
    if req.safety_required is not None:
        convo.safety_required = req.safety_required
    if req.io_modules is not None:
        convo.io_modules = json.dumps(req.io_modules)
    convo.updated_at = datetime.utcnow()
    db.commit()
    return {"status": "ok"}


# ============================================================
# Stage Management
# ============================================================

@router.post("/{conversation_id}/stage/advance")
async def advance_stage(
    conversation_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    convo = _convo_owner(db, conversation_id, user.id)
    cur = convo.current_stage
    idx = STAGE_ORDER.index(cur) if cur in STAGE_ORDER else 0

    if idx >= len(STAGE_ORDER) - 1:
        raise HTTPException(status_code=400, detail="Project already completed")

    # Prerequisite checks
    if cur == "planning":
        if not convo.fds_content:
            raise HTTPException(status_code=400, detail="Generate or upload an FDS before advancing")
    elif cur == "execution":
        has_code = db.query(GeneratedDocument).filter(
            GeneratedDocument.conversation_id == conversation_id,
            GeneratedDocument.doc_type == "PLC_CODE",
        ).first()
        if not has_code:
            raise HTTPException(status_code=400, detail="Generate PLC code before advancing to testing")
    elif cur == "testing":
        has_fat = db.query(GeneratedDocument).filter(
            GeneratedDocument.conversation_id == conversation_id,
            GeneratedDocument.doc_type == "FAT",
        ).first()
        if not has_fat:
            raise HTTPException(status_code=400, detail="Generate FAT document before completing")

    # Mark current stage completed
    cur_stage = db.query(ProjectStage).filter(
        ProjectStage.conversation_id == conversation_id,
        ProjectStage.stage_name == cur,
    ).first()
    if cur_stage:
        cur_stage.status = "completed"
        cur_stage.completed_at = datetime.utcnow()

    # Activate next stage
    next_name = STAGE_ORDER[idx + 1]
    next_stage = db.query(ProjectStage).filter(
        ProjectStage.conversation_id == conversation_id,
        ProjectStage.stage_name == next_name,
    ).first()
    if next_stage:
        next_stage.status = "active"
        next_stage.started_at = datetime.utcnow()

    convo.current_stage = next_name
    convo.updated_at = datetime.utcnow()
    db.commit()

    return {"current_stage": next_name, "label": STAGE_LABELS.get(next_name)}


# ============================================================
# AI Document Generation
# ============================================================

@router.post("/{conversation_id}/generate/{doc_type}")
async def generate_document(
    conversation_id: int,
    doc_type: str,
    req: GenerateRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Generate a document (FDS, IO_LIST, PLC_CODE, FAT, SAT) using the AI agent."""
    convo = _convo_owner(db, conversation_id, user.id)
    doc_type = doc_type.upper()
    valid_types = {"FDS", "IO_LIST", "PLC_CODE", "FAT", "SAT"}
    if doc_type not in valid_types:
        raise HTTPException(status_code=400, detail=f"Invalid doc type. Use: {valid_types}")

    # Build context for AI
    hw_info = (
        f"CPU: {convo.cpu_model or 'S7-1500'} {convo.cpu_variant or ''}\n"
        f"TIA Portal: {convo.software_version or 'V18'}\n"
        f"Network: {convo.network_type or 'PROFINET'}\n"
        f"Safety: {'Yes' if convo.safety_required else 'No'}\n"
        f"IO Modules: {convo.io_modules or '[]'}\n"
        f"Architecture: {convo.architecture_notes or 'Not specified'}\n"
    )

    prompts = {
        "FDS": f"""Generate a detailed Functional Design Specification (FDS) for this Siemens PLC project.

Project: {convo.title}
Description: {convo.description or 'Not provided'}
{hw_info}
{f'Additional instructions: {req.prompt}' if req.prompt else ''}

Structure the FDS with these sections:
1. **Project Overview** — scope, objectives, system description
2. **Hardware Architecture** — CPU, IO modules, network topology
3. **Software Architecture** — program structure, function blocks, data blocks
4. **Functional Requirements** — detailed behavior per function
5. **IO Signal List Summary** — input/output signals overview
6. **Safety Requirements** — if applicable
7. **HMI Requirements** — operator interface needs
8. **Communication** — network, protocol details
9. **Alarm & Diagnostics** — fault handling strategy

Write in professional engineering format with clear numbered sections.""",

        "IO_LIST": f"""Generate a comprehensive IO List for this Siemens PLC project based on the FDS.

Project: {convo.title}
{hw_info}
FDS Content:
{convo.fds_content or 'No FDS available — generate based on project description: ' + (convo.description or '')}
{f'Additional instructions: {req.prompt}' if req.prompt else ''}

Create a structured IO list in markdown table format with these columns:
| Tag Name | Description | IO Type | Data Type | HW Address | Signal Range | Unit | Comment |

IO Types: DI (Digital In), DO (Digital Out), AI (Analog In), AO (Analog Out)
Include realistic Siemens addressing (e.g., %I0.0, %Q0.0, %IW64, %QW80).
Group by functional area. Include all signals needed for the project.""",

        "PLC_CODE": f"""Generate complete, production-ready Siemens SCL code for TIA Portal.

Project: {convo.title}
{hw_info}
FDS Summary:
{(convo.fds_content or '')[:3000]}

IO List:
{(convo.io_list_content or '')[:2000]}
{f'Additional instructions: {req.prompt}' if req.prompt else ''}

Generate complete SCL code including:
1. **Main OB (OB1)** — program cycle organization
2. **Function Blocks (FBs)** — one per major subsystem with IN/OUT/INOUT/STAT/TEMP vars
3. **Data Blocks (DBs)** — instance DBs and global DBs
4. **Functions (FCs)** — utility/helper functions
5. **Error handling** — diagnostic codes, fault bits
6. **Comments** — comprehensive inline documentation

Use Siemens TIA Portal SCL syntax. Make it compilable and complete.""",

        "FAT": f"""Generate a Factory Acceptance Test (FAT) document for this Siemens PLC project.

Project: {convo.title}
{hw_info}
FDS Summary:
{(convo.fds_content or '')[:2000]}
{f'Additional instructions: {req.prompt}' if req.prompt else ''}

Structure the FAT document with:
1. **Test Overview** — purpose, scope, references
2. **Test Environment** — hardware setup, software versions
3. **Pre-conditions** — what must be ready before testing
4. **Test Cases** — numbered test cases in table format:
   | Test ID | Description | Steps | Expected Result | Actual Result | Pass/Fail |
5. **IO Verification Tests** — verify all inputs/outputs
6. **Functional Tests** — verify each function per FDS
7. **Safety Tests** — emergency stop, interlocks (if applicable)
8. **Communication Tests** — network, HMI
9. **Performance Tests** — cycle time, response time
10. **Sign-off** — approval section""",

        "SAT": f"""Generate a Site Acceptance Test (SAT) document for this Siemens PLC project.

Project: {convo.title}
{hw_info}
FDS Summary:
{(convo.fds_content or '')[:2000]}
{f'Additional instructions: {req.prompt}' if req.prompt else ''}

Structure the SAT document with:
1. **Site Test Overview** — purpose, scope, site conditions
2. **Site Prerequisites** — power, utilities, mechanical completion
3. **Commissioning Checklist** — pre-start verification
4. **Integration Test Cases**:
   | Test ID | Description | Steps | Expected Result | Actual Result | Pass/Fail |
5. **Real-World Scenario Tests** — actual production scenarios
6. **Performance Benchmarks** — throughput, cycle times under load
7. **Safety System Validation** — on-site safety verification
8. **Operator Training Verification** — HMI, procedures
9. **Punch List** — outstanding items
10. **Customer Sign-off** — acceptance section""",
    }

    prompt = prompts[doc_type]

    # Determine stage
    stage_map = {"FDS": "planning", "IO_LIST": "planning", "PLC_CODE": "execution", "FAT": "testing", "SAT": "testing"}
    stage = stage_map[doc_type]

    try:
        # Use a fresh agent for document generation
        from plc_agent import PLCAgent
        agent = PLCAgent()
        content = agent.chat(prompt)

        # Save to DB
        version = db.query(GeneratedDocument).filter(
            GeneratedDocument.conversation_id == conversation_id,
            GeneratedDocument.doc_type == doc_type,
        ).count() + 1

        title = f"{doc_type.replace('_', ' ')} v{version}"

        # Generate .docx file for document types
        docx_path = None
        if doc_type in {"FDS", "IO_LIST", "FAT", "SAT"}:
            try:
                from docx_generator import markdown_to_docx
                hw_info = {
                    "CPU Model": convo.cpu_model or "N/A",
                    "CPU Variant": convo.cpu_variant or "N/A",
                    "TIA Portal": convo.software_version or "N/A",
                    "Network": convo.network_type or "N/A",
                    "Safety": "Required" if convo.safety_required else "Standard",
                }
                docx_path = markdown_to_docx(
                    content=content,
                    title=title,
                    doc_type=doc_type,
                    project_title=convo.title,
                    hardware_info=hw_info,
                )
            except Exception as docx_err:
                print(f"[LADX] DOCX generation failed (content still saved): {docx_err}")

        gen_doc = GeneratedDocument(
            conversation_id=conversation_id,
            doc_type=doc_type,
            stage=stage,
            title=title,
            content=content,
            filepath=docx_path,
            version=version,
        )
        db.add(gen_doc)

        # Store FDS/IO_LIST content on conversation for downstream use
        if doc_type == "FDS":
            convo.fds_content = content
        elif doc_type == "IO_LIST":
            convo.io_list_content = content

        convo.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(gen_doc)

        return {
            "id": gen_doc.id,
            "doc_type": doc_type,
            "title": gen_doc.title,
            "content": content,
            "version": version,
            "stage": stage,
            "has_docx": docx_path is not None,
        }

    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Generation failed: {str(e)}")


@router.get("/{conversation_id}/generated/{doc_id}")
async def get_generated_document(
    conversation_id: int,
    doc_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get a specific generated document's content."""
    _convo_owner(db, conversation_id, user.id)
    doc = db.query(GeneratedDocument).filter(
        GeneratedDocument.id == doc_id,
        GeneratedDocument.conversation_id == conversation_id,
    ).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return {
        "id": doc.id,
        "doc_type": doc.doc_type,
        "title": doc.title,
        "content": doc.content,
        "version": doc.version,
        "stage": doc.stage,
        "has_docx": doc.filepath is not None and os.path.exists(doc.filepath) if doc.filepath else False,
        "generated_at": doc.generated_at.isoformat() if doc.generated_at else None,
    }


@router.get("/{conversation_id}/generated/{doc_id}/download")
async def download_generated_document(
    conversation_id: int,
    doc_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Download a generated document as .docx."""
    _convo_owner(db, conversation_id, user.id)
    doc = db.query(GeneratedDocument).filter(
        GeneratedDocument.id == doc_id,
        GeneratedDocument.conversation_id == conversation_id,
    ).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    if not doc.filepath or not os.path.exists(doc.filepath):
        raise HTTPException(status_code=404, detail="DOCX file not available for this document")
    safe_name = f"{doc.doc_type}_v{doc.version}.docx"
    return FileResponse(doc.filepath, filename=safe_name,
                        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document")


# ============================================================
# Upload FDS (user has existing FDS)
# ============================================================

@router.post("/{conversation_id}/upload-fds")
async def upload_fds(
    conversation_id: int,
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Upload an existing FDS document and extract its content."""
    convo = _convo_owner(db, conversation_id, user.id)

    content_bytes = await file.read()
    if len(content_bytes) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="File too large (max 10MB)")

    # Save file
    conv_dir = os.path.join(UPLOAD_DIR, f"conv_{conversation_id}")
    os.makedirs(conv_dir, exist_ok=True)
    ts = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    stored_name = f"{ts}_FDS_{file.filename}"
    filepath = os.path.join(conv_dir, stored_name)
    with open(filepath, "wb") as f:
        f.write(content_bytes)

    # Save as uploaded doc
    doc = ProjectDocument(
        conversation_id=conversation_id,
        filename=file.filename or "FDS_upload",
        filepath=filepath,
        file_type=os.path.splitext(file.filename or "")[1].lstrip("."),
        file_size=len(content_bytes),
    )
    db.add(doc)

    # Try to extract text content (for txt/csv files)
    try:
        text_content = content_bytes.decode("utf-8", errors="replace")
    except Exception:
        text_content = f"[Binary file uploaded: {file.filename}]"

    convo.fds_content = text_content
    convo.updated_at = datetime.utcnow()

    # Also create a GeneratedDocument record for tracking
    gen_doc = GeneratedDocument(
        conversation_id=conversation_id,
        doc_type="FDS",
        stage="planning",
        title=f"FDS (Uploaded: {file.filename})",
        content=text_content,
        version=1,
    )
    db.add(gen_doc)
    db.commit()

    return {"status": "ok", "filename": file.filename, "content_preview": text_content[:500]}


# ============================================================
# Document Upload/Download (user files)
# ============================================================

@router.post("/{conversation_id}/documents")
async def upload_document(
    conversation_id: int,
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        convo = _convo_owner(db, conversation_id, user.id)
        ext = os.path.splitext(file.filename or "")[1].lower()
        if ext not in ALLOWED_EXTENSIONS:
            raise HTTPException(status_code=400, detail=f"File type {ext} not allowed")

        content = await file.read()
        if len(content) > MAX_FILE_SIZE:
            raise HTTPException(status_code=400, detail="File too large (max 10MB)")

        conv_dir = os.path.join(UPLOAD_DIR, f"conv_{conversation_id}")
        os.makedirs(conv_dir, exist_ok=True)
        ts = datetime.utcnow().strftime("%Y%m%d%H%M%S")
        stored_name = f"{ts}_{file.filename}"
        filepath = os.path.join(conv_dir, stored_name)
        with open(filepath, "wb") as f:
            f.write(content)

        doc = ProjectDocument(
            conversation_id=conversation_id,
            filename=file.filename or "unknown",
            filepath=filepath,
            file_type=ext.lstrip("."),
            file_size=len(content),
        )
        db.add(doc)
        db.commit()
        db.refresh(doc)

        return {
            "id": doc.id, "filename": doc.filename, "file_type": doc.file_type,
            "file_size": doc.file_size,
            "uploaded_at": doc.uploaded_at.isoformat() if doc.uploaded_at else None,
        }
    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")


@router.get("/{conversation_id}/documents")
async def list_documents(
    conversation_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    convo = _convo_owner(db, conversation_id, user.id)
    return [
        {"id": d.id, "filename": d.filename, "file_type": d.file_type,
         "file_size": d.file_size, "uploaded_at": d.uploaded_at.isoformat() if d.uploaded_at else None}
        for d in convo.documents
    ]


@router.get("/{conversation_id}/documents/{doc_id}/download")
async def download_document(
    conversation_id: int, doc_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _convo_owner(db, conversation_id, user.id)
    doc = db.query(ProjectDocument).filter(
        ProjectDocument.id == doc_id, ProjectDocument.conversation_id == conversation_id,
    ).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    if not os.path.exists(doc.filepath):
        raise HTTPException(status_code=404, detail="File not found on disk")
    return FileResponse(doc.filepath, filename=doc.filename)


@router.delete("/{conversation_id}/documents/{doc_id}")
async def delete_document(
    conversation_id: int, doc_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _convo_owner(db, conversation_id, user.id)
    doc = db.query(ProjectDocument).filter(
        ProjectDocument.id == doc_id, ProjectDocument.conversation_id == conversation_id,
    ).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    if os.path.exists(doc.filepath):
        os.remove(doc.filepath)
    db.delete(doc)
    db.commit()
    return {"message": "Document deleted"}
