"""
LADX - Auth Routes
Register, login, user profile, dashboard, and skill assessment endpoints.
"""

import re
import traceback
import shutil
import uuid
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from db.database import get_db
from db.models import User, SkillAssessment, Conversation
from auth.password import hash_password, verify_password
from auth.jwt_handler import create_token
from auth.dependencies import get_current_user
from auth.rate_limiter import check_rate_limit, TIER_LIMITS

router = APIRouter(prefix="/api/auth", tags=["auth"])


# --- Request/Response Schemas ---

class RegisterRequest(BaseModel):
    email: str
    username: str
    password: str
    full_name: Optional[str] = None


class LoginRequest(BaseModel):
    email: str
    password: str


class ForgotPasswordRequest(BaseModel):
    email: str


class ResetPasswordRequest(BaseModel):
    token: str
    password: str


class SkillItem(BaseModel):
    skill_name: str
    skill_level: float  # 0-5


class SkillAssessmentRequest(BaseModel):
    skills: List[SkillItem]


# --- Endpoints ---

@router.post("/register")
async def register(req: RegisterRequest, db: Session = Depends(get_db)):
    """Create a new user account."""
    try:
        # Validate email format
        if not re.match(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$", req.email):
            raise HTTPException(status_code=400, detail="Invalid email format")

        # Validate password strength
        if len(req.password) < 6:
            raise HTTPException(status_code=400, detail="Password must be at least 6 characters")

        # Check if email exists
        existing = db.query(User).filter(User.email == req.email.lower().strip()).first()
        if existing:
            raise HTTPException(status_code=409, detail="Email already registered")

        # Create user (no email confirmation for now)
        user = User(
            email=req.email.lower().strip(),
            username=req.username.strip(),
            full_name=(req.full_name or "").strip() or None,
            password_hash=hash_password(req.password),
            tier="free",
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        # Generate JWT token
        token = create_token(user.id, user.email, user.tier)

        return JSONResponse({
            "token": token,
            "user": {
                "id": user.id,
                "email": user.email,
                "username": user.username,
                "full_name": user.full_name,
                "tier": user.tier,
            },
            "email_confirmed": True,
        })

    except HTTPException:
        raise
    except Exception as e:
        print(f"[LADX] Register error: {e}")
        traceback.print_exc()
        return JSONResponse({"detail": f"Registration failed: {str(e)}"}, status_code=500)


@router.post("/login")
async def login(req: LoginRequest, db: Session = Depends(get_db)):
    """Authenticate and return a JWT token."""
    try:
        user = db.query(User).filter(User.email == req.email.lower().strip()).first()

        if not user or not verify_password(req.password, user.password_hash):
            raise HTTPException(status_code=401, detail="Invalid email or password")

        if not user.is_active:
            raise HTTPException(status_code=403, detail="Account is deactivated")

        token = create_token(user.id, user.email, user.tier)

        return JSONResponse({
            "token": token,
            "user": {
                "id": user.id,
                "email": user.email,
                "username": user.username,
                "full_name": user.full_name,
                "tier": user.tier,
            },
            "email_confirmed": True,
        })

    except HTTPException:
        raise
    except Exception as e:
        print(f"[LADX] Login error: {e}")
        traceback.print_exc()
        return JSONResponse({"detail": f"Login failed: {str(e)}"}, status_code=500)


@router.post("/forgot-password")
async def forgot_password(req: ForgotPasswordRequest, db: Session = Depends(get_db)):
    """Placeholder - email not configured yet."""
    return {"message": "Password reset is not available yet. Email configuration pending."}


@router.post("/reset-password")
async def reset_password(req: ResetPasswordRequest, db: Session = Depends(get_db)):
    """Placeholder - email not configured yet."""
    return {"message": "Password reset is not available yet. Email configuration pending."}


@router.get("/confirm/{token}", response_class=HTMLResponse)
async def confirm_email(token: str, db: Session = Depends(get_db)):
    """Placeholder - email not configured yet."""
    return HTMLResponse("<html><body><h2>Email confirmation not configured yet.</h2></body></html>")


@router.post("/resend-confirmation")
async def resend_confirmation():
    """Placeholder - email not configured yet."""
    return {"message": "Email confirmation not configured yet."}


class ProfileUpdate(BaseModel):
    full_name: Optional[str] = None
    username: Optional[str] = None
    company: Optional[str] = None
    phone: Optional[str] = None
    job_title: Optional[str] = None
    # Private LLM settings
    use_private_llm: Optional[bool] = None
    private_llm_provider: Optional[str] = None
    private_llm_api_key: Optional[str] = None
    private_llm_base_url: Optional[str] = None
    private_llm_model: Optional[str] = None


@router.get("/profile")
async def get_profile(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get current user's profile and usage stats."""
    try:
        usage = check_rate_limit(db, user.id, user.tier)

        # Mask API key for display (show last 4 chars only)
        masked_key = ""
        if user.private_llm_api_key:
            k = user.private_llm_api_key
            masked_key = ("*" * max(0, len(k) - 4)) + k[-4:] if len(k) > 4 else "****"

        return {
            "id": user.id,
            "email": user.email,
            "username": user.username,
            "full_name": user.full_name,
            "company": user.company,
            "company_logo": user.company_logo,
            "phone": user.phone,
            "job_title": user.job_title,
            "profile_picture": user.profile_picture or "",
            "tier": user.tier,
            "email_confirmed": True,
            "created_at": user.created_at.isoformat(),
            "usage": usage,
            # LLM settings
            "use_private_llm": user.use_private_llm or False,
            "private_llm_provider": user.private_llm_provider or "openrouter",
            "private_llm_api_key_masked": masked_key,
            "private_llm_api_key_set": bool(user.private_llm_api_key),
            "private_llm_base_url": user.private_llm_base_url or "",
            "private_llm_model": user.private_llm_model or "",
        }
    except Exception as e:
        print(f"[LADX] Profile error: {e}")
        traceback.print_exc()
        return JSONResponse({"detail": str(e)}, status_code=500)


@router.put("/profile")
async def update_profile(
    req: ProfileUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update user profile fields."""
    try:
        for field in ["full_name", "username", "company", "phone", "job_title"]:
            val = getattr(req, field, None)
            if val is not None:
                setattr(user, field, val.strip())

        # Private LLM settings
        if req.use_private_llm is not None:
            user.use_private_llm = req.use_private_llm
        if req.private_llm_provider is not None:
            user.private_llm_provider = req.private_llm_provider.strip()
        if req.private_llm_api_key is not None:
            # Only update if the user sends a real key (not the masked version)
            key = req.private_llm_api_key.strip()
            if key and not key.startswith("*"):
                user.private_llm_api_key = key
            elif not key:
                user.private_llm_api_key = None
        if req.private_llm_base_url is not None:
            user.private_llm_base_url = req.private_llm_base_url.strip() or None
        if req.private_llm_model is not None:
            user.private_llm_model = req.private_llm_model.strip() or None

        user.updated_at = datetime.utcnow()
        db.commit()
        return {
            "status": "ok",
            "full_name": user.full_name,
            "username": user.username,
            "company": user.company,
            "phone": user.phone,
            "job_title": user.job_title,
            "use_private_llm": user.use_private_llm,
        }
    except Exception as e:
        print(f"[LADX] Profile update error: {e}")
        return JSONResponse({"detail": str(e)}, status_code=500)


@router.post("/profile/picture")
async def upload_profile_picture(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Upload a profile picture for the current user."""
    try:
        # Validate file type
        allowed = {".png", ".jpg", ".jpeg", ".webp"}
        ext = Path(file.filename).suffix.lower()
        if ext not in allowed:
            return JSONResponse({"detail": "Only PNG, JPG, and WEBP files are allowed."}, status_code=400)

        # Save file
        upload_dir = Path("uploads/avatars")
        upload_dir.mkdir(parents=True, exist_ok=True)
        unique_name = f"{user.id}_{uuid.uuid4().hex[:8]}{ext}"
        dest = upload_dir / unique_name

        with open(dest, "wb") as f:
            shutil.copyfileobj(file.file, f)

        # Update user record
        user.profile_picture = f"/static/avatars/{unique_name}"
        db.commit()

        # Symlink or copy to static for serving
        static_avatar_dir = Path("web/static/avatars")
        static_avatar_dir.mkdir(parents=True, exist_ok=True)
        static_dest = static_avatar_dir / unique_name
        if not static_dest.exists():
            shutil.copy2(str(dest), str(static_dest))

        return {"status": "ok", "profile_picture": user.profile_picture}
    except Exception as e:
        print(f"[LADX] Avatar upload error: {e}")
        return JSONResponse({"detail": str(e)}, status_code=500)


@router.get("/dashboard")
async def get_dashboard(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get full dashboard data: profile, skills, plan, usage, projects."""
    try:
        usage = check_rate_limit(db, user.id, user.tier)
        tier_info = TIER_LIMITS.get(user.tier, TIER_LIMITS["free"])

        # Get skills
        skills = db.query(SkillAssessment).filter(
            SkillAssessment.user_id == user.id
        ).all()
        skills_data = [
            {"skill_name": s.skill_name, "skill_level": s.skill_level,
             "assessed_at": s.assessed_at.isoformat() if s.assessed_at else None}
            for s in skills
        ]

        # Get conversations as projects
        conversations = db.query(Conversation).filter(
            Conversation.user_id == user.id,
            Conversation.is_archived == False,
        ).order_by(Conversation.updated_at.desc()).all()
        projects = [
            {"id": c.id, "title": c.title, "platform": c.platform,
             "created_at": c.created_at.isoformat(),
             "updated_at": c.updated_at.isoformat(),
             "message_count": len(c.messages)}
            for c in conversations
        ]

        return {
            "user": {
                "id": user.id,
                "email": user.email,
                "username": user.username,
                "full_name": user.full_name,
                "company": user.company,
                "company_logo": user.company_logo,
                "phone": user.phone,
                "job_title": user.job_title,
                "tier": user.tier,
                "created_at": user.created_at.isoformat(),
                "updated_at": user.updated_at.isoformat() if user.updated_at else None,
            },
            "skills": skills_data,
            "plan": {
                "tier": user.tier,
                "messages_per_day": tier_info["messages_per_day"],
                "max_conversations": tier_info["max_conversations"],
                "features": tier_info["features"],
            },
            "usage": usage,
            "projects": projects,
        }
    except Exception as e:
        print(f"[LADX] Dashboard error: {e}")
        traceback.print_exc()
        return JSONResponse({"detail": str(e)}, status_code=500)


@router.post("/skills")
async def save_skills(
    req: SkillAssessmentRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Save or update user skill assessments."""
    try:
        for item in req.skills:
            # Clamp level 0-5
            level = max(0.0, min(5.0, item.skill_level))
            existing = db.query(SkillAssessment).filter(
                SkillAssessment.user_id == user.id,
                SkillAssessment.skill_name == item.skill_name,
            ).first()

            if existing:
                existing.skill_level = level
                existing.assessed_at = datetime.utcnow()
            else:
                db.add(SkillAssessment(
                    user_id=user.id,
                    skill_name=item.skill_name,
                    skill_level=level,
                ))

        db.commit()

        # Return updated skills
        skills = db.query(SkillAssessment).filter(
            SkillAssessment.user_id == user.id
        ).all()

        return {
            "message": "Skills saved successfully",
            "skills": [
                {"skill_name": s.skill_name, "skill_level": s.skill_level}
                for s in skills
            ],
        }
    except Exception as e:
        print(f"[LADX] Skills save error: {e}")
        traceback.print_exc()
        return JSONResponse({"detail": str(e)}, status_code=500)
