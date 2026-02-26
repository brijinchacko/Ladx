"""
LADX - Configuration
Loads settings from .env file
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# ===========================================
# Paths
# ===========================================
BASE_DIR = Path(__file__).parent
KNOWLEDGE_DIR = Path(os.getenv("KNOWLEDGE_DIR", "./knowledge"))
CHROMA_DB_DIR = Path(os.getenv("CHROMA_DB_DIR", "./chroma_db"))
OUTPUT_DIR = Path(os.getenv("OUTPUT_DIR", "./output"))
SYSTEM_PROMPT_PATH = BASE_DIR / "system_prompt.txt"

# Create directories if they don't exist
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# ===========================================
# AI Settings (OpenRouter)
# ===========================================
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
AI_MODEL = os.getenv("AI_MODEL", "openrouter/free")
MAX_TOKENS = 8000
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

# ===========================================
# Database Settings
# ===========================================
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{BASE_DIR / 'ladx.db'}")

# ===========================================
# JWT Authentication
# ===========================================
JWT_SECRET = os.getenv("JWT_SECRET", "ladx-dev-secret-change-in-production")
JWT_EXPIRY_HOURS = int(os.getenv("JWT_EXPIRY_HOURS", "24"))

# ===========================================
# Server Settings
# ===========================================
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8000"))

# ===========================================
# TIA Portal Bridge
# ===========================================
TIA_BRIDGE_URL = os.getenv("TIA_BRIDGE_URL", "http://localhost:5050")

# ===========================================
# Email / SMTP (Namecheap Private Email)
# ===========================================
SMTP_HOST = os.getenv("SMTP_HOST", "mail.privateemail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "465"))
SMTP_USER = os.getenv("SMTP_USER", "hello@ladx.ai")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
FROM_EMAIL = os.getenv("FROM_EMAIL", "hello@ladx.ai")
APP_URL = os.getenv("APP_URL", "http://localhost:8000")

# ===========================================
# Load System Prompt
# ===========================================
def get_system_prompt() -> str:
    """Load the system prompt from file."""
    if SYSTEM_PROMPT_PATH.exists():
        return SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")
    return "You are a PLC programming assistant."


# ===========================================
# Platform Definitions (Siemens Only)
# ===========================================
PLATFORMS = {
    "siemens": {
        "name": "Siemens TIA Portal",
        "language": "SCL (Structured Control Language)",
        "file_ext": ".scl",
        "description": "Siemens S7-1200/1500 with TIA Portal"
    },
}

# Siemens hardware options
SIEMENS_CPU_MODELS = {
    "S7-1200": {
        "name": "SIMATIC S7-1200",
        "variants": ["CPU 1211C", "CPU 1212C", "CPU 1214C", "CPU 1215C", "CPU 1217C"],
        "description": "Compact controller for simple to medium automation tasks",
    },
    "S7-1500": {
        "name": "SIMATIC S7-1500",
        "variants": ["CPU 1511-1", "CPU 1513-1", "CPU 1515-2", "CPU 1516-3 PN/DP", "CPU 1517-3", "CPU 1518-4"],
        "description": "High-performance controller for demanding automation",
    },
    "S7-1500F": {
        "name": "SIMATIC S7-1500F (Fail-safe)",
        "variants": ["CPU 1511F-1", "CPU 1513F-1", "CPU 1515F-2", "CPU 1516F-3 PN/DP", "CPU 1518F-4"],
        "description": "Fail-safe controller for safety-critical applications",
    },
}

TIA_PORTAL_VERSIONS = ["V17", "V18", "V19", "V20"]

NETWORK_TYPES = ["PROFINET", "PROFIBUS", "MPI", "Ethernet/IP"]

IO_MODULE_TYPES = [
    "DI 16x24VDC",
    "DI 32x24VDC",
    "DQ 16x24VDC/0.5A",
    "DQ 32x24VDC/0.5A",
    "AI 8xU/I/RTD/TC",
    "AI 4xU/I/RTD/TC",
    "AQ 4xU/I",
    "AQ 2xU/I",
    "DI/DQ 16x24VDC Combo",
]
