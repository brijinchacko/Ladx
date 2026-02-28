"""
LADX - Database Connection
SQLite engine, session factory, and initialization.
"""

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker
from config import DATABASE_URL
from db.models import Base

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db():
    """Create all tables. If tables are missing new columns, recreate them."""
    try:
        inspector = inspect(engine)
        tables = inspector.get_table_names()
        needs_rebuild = False

        # Check users table for required columns
        if "users" in tables:
            columns = [col["name"] for col in inspector.get_columns("users")]
            required = ["email_confirmed", "confirm_token", "reset_token", "reset_token_expires",
                        "full_name", "company", "company_logo", "phone", "job_title",
                        "profile_picture",
                        "use_private_llm", "private_llm_provider", "private_llm_api_key",
                        "private_llm_base_url", "private_llm_model"]
            if any(col not in columns for col in required):
                needs_rebuild = True

        # Check conversations table for lifecycle columns
        if "conversations" in tables:
            columns = [col["name"] for col in inspector.get_columns("conversations")]
            required = ["software_version", "description", "current_stage", "cpu_model",
                        "cpu_variant", "io_modules", "network_type", "safety_required",
                        "architecture_notes", "fds_content", "io_list_content"]
            if any(col not in columns for col in required):
                needs_rebuild = True

        # Check for all required tables
        required_tables = ["project_documents", "skill_assessments",
                           "project_stages", "generated_documents"]
        if any(t not in tables for t in required_tables):
            needs_rebuild = True

        if needs_rebuild:
            print("[DB] Schema outdated — dropping and recreating all tables...")
            Base.metadata.drop_all(bind=engine)

        Base.metadata.create_all(bind=engine)
        print("[DB] Database initialized successfully.")

    except Exception as e:
        print(f"[DB] Error during init, recreating tables: {e}")
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)
        print("[DB] Database recreated successfully.")


def get_db():
    """Dependency for FastAPI - yields a database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
