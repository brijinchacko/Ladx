"""
LADX - Database Models
SQLAlchemy ORM models for users, conversations, messages, project lifecycle, and usage tracking.
"""

from datetime import datetime, date
from sqlalchemy import (
    Column, Integer, String, Text, Boolean, DateTime, Date,
    ForeignKey, JSON, Float
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()

# ===========================================
# Stage definitions
# ===========================================
STAGE_ORDER = ["planning", "execution", "testing", "completed"]

STAGE_LABELS = {
    "planning": "Project Planning",
    "execution": "Project Execution",
    "testing": "Testing & Validation",
    "completed": "Project Completed",
}


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    username = Column(String(100), nullable=False)
    full_name = Column(String(200), nullable=True)
    company = Column(String(200), nullable=True)
    company_logo = Column(String(500), nullable=True)  # filepath to uploaded logo
    profile_picture = Column(String(500), nullable=True)  # filepath to profile picture
    phone = Column(String(50), nullable=True)
    job_title = Column(String(200), nullable=True)
    password_hash = Column(String(255), nullable=False)
    tier = Column(String(20), nullable=False, default="free")
    is_active = Column(Boolean, default=True)
    email_confirmed = Column(Boolean, default=False)
    confirm_token = Column(String(255), nullable=True)
    reset_token = Column(String(255), nullable=True)
    reset_token_expires = Column(DateTime, nullable=True)

    # Private LLM settings
    use_private_llm = Column(Boolean, default=False)
    private_llm_provider = Column(String(50), nullable=True)       # openrouter, openai, anthropic, custom
    private_llm_api_key = Column(String(512), nullable=True)       # encrypted in production
    private_llm_base_url = Column(String(512), nullable=True)      # custom endpoint URL
    private_llm_model = Column(String(200), nullable=True)         # model name override

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    conversations = relationship("Conversation", back_populates="user", cascade="all, delete-orphan")
    usage_records = relationship("UsageTracking", back_populates="user", cascade="all, delete-orphan")
    skills = relationship("SkillAssessment", back_populates="user", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<User(id={self.id}, email='{self.email}', tier='{self.tier}')>"


class Conversation(Base):
    __tablename__ = "conversations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    title = Column(String(255), default="New Project")
    platform = Column(String(50), default="siemens")
    software_version = Column(String(100), nullable=True)
    description = Column(Text, nullable=True)
    is_archived = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # ---- Lifecycle fields ----
    current_stage = Column(String(50), default="planning")
    cpu_model = Column(String(100), nullable=True)       # e.g. "S7-1500"
    cpu_variant = Column(String(200), nullable=True)      # e.g. "CPU 1516-3 PN/DP"
    io_modules = Column(Text, nullable=True)              # JSON string: list of IO modules
    network_type = Column(String(100), nullable=True)     # e.g. "PROFINET"
    safety_required = Column(Boolean, default=False)
    architecture_notes = Column(Text, nullable=True)      # Free-text notes about system architecture
    fds_content = Column(Text, nullable=True)             # Generated or parsed FDS
    io_list_content = Column(Text, nullable=True)         # Generated IO list (JSON)

    # Relationships
    user = relationship("User", back_populates="conversations")
    messages = relationship("Message", back_populates="conversation", cascade="all, delete-orphan",
                            order_by="Message.created_at")
    documents = relationship("ProjectDocument", back_populates="conversation", cascade="all, delete-orphan")
    stages = relationship("ProjectStage", back_populates="conversation", cascade="all, delete-orphan",
                          order_by="ProjectStage.id")
    generated_docs = relationship("GeneratedDocument", back_populates="conversation", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Conversation(id={self.id}, title='{self.title}', stage='{self.current_stage}')>"


class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    conversation_id = Column(Integer, ForeignKey("conversations.id"), nullable=False, index=True)
    role = Column(String(20), nullable=False)
    content = Column(Text, nullable=False)
    tool_calls = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    conversation = relationship("Conversation", back_populates="messages")

    def __repr__(self):
        return f"<Message(id={self.id}, role='{self.role}')>"


class ProjectStage(Base):
    """Tracks each stage's start/end for timeline and progress."""
    __tablename__ = "project_stages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    conversation_id = Column(Integer, ForeignKey("conversations.id"), nullable=False, index=True)
    stage_name = Column(String(50), nullable=False)       # planning, execution, testing, completed
    status = Column(String(20), default="pending")         # pending, active, completed
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)

    conversation = relationship("Conversation", back_populates="stages")

    def __repr__(self):
        return f"<ProjectStage(conv={self.conversation_id}, stage='{self.stage_name}', status='{self.status}')>"


class GeneratedDocument(Base):
    """Documents generated by AI at each stage (FDS, IO list, code, FAT, SAT)."""
    __tablename__ = "generated_documents"

    id = Column(Integer, primary_key=True, autoincrement=True)
    conversation_id = Column(Integer, ForeignKey("conversations.id"), nullable=False, index=True)
    doc_type = Column(String(50), nullable=False)          # FDS, IO_LIST, PLC_CODE, FAT, SAT
    stage = Column(String(50), nullable=False)             # planning, execution, testing
    title = Column(String(255), nullable=True)
    content = Column(Text, nullable=True)                  # The actual document content (markdown/text)
    filepath = Column(String(512), nullable=True)          # If exported to file
    version = Column(Integer, default=1)
    generated_at = Column(DateTime, default=datetime.utcnow)

    conversation = relationship("Conversation", back_populates="generated_docs")

    def __repr__(self):
        return f"<GeneratedDocument(conv={self.conversation_id}, type='{self.doc_type}', v{self.version})>"


class ProjectDocument(Base):
    """User-uploaded documents."""
    __tablename__ = "project_documents"

    id = Column(Integer, primary_key=True, autoincrement=True)
    conversation_id = Column(Integer, ForeignKey("conversations.id"), nullable=False, index=True)
    filename = Column(String(255), nullable=False)
    filepath = Column(String(512), nullable=False)
    file_type = Column(String(50), nullable=True)
    file_size = Column(Integer, default=0)
    uploaded_at = Column(DateTime, default=datetime.utcnow)

    conversation = relationship("Conversation", back_populates="documents")

    def __repr__(self):
        return f"<ProjectDocument(id={self.id}, filename='{self.filename}')>"


class SkillAssessment(Base):
    __tablename__ = "skill_assessments"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    skill_name = Column(String(100), nullable=False)
    skill_level = Column(Float, nullable=False, default=0)
    assessed_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="skills")


class UsageTracking(Base):
    __tablename__ = "usage_tracking"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    date = Column(Date, nullable=False, default=date.today)
    messages_count = Column(Integer, default=0)

    user = relationship("User", back_populates="usage_records")
