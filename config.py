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
# AI Settings
# ===========================================
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
AI_MODEL = os.getenv("AI_MODEL", "claude-sonnet-4-5-20250929")
MAX_TOKENS = 8000

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
# Load System Prompt
# ===========================================
def get_system_prompt() -> str:
    """Load the system prompt from file."""
    if SYSTEM_PROMPT_PATH.exists():
        return SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")
    return "You are a PLC programming assistant."


# ===========================================
# Platform Definitions
# ===========================================
PLATFORMS = {
    "siemens": {
        "name": "Siemens TIA Portal",
        "language": "SCL (Structured Control Language)",
        "file_ext": ".scl",
        "description": "Siemens S7-1200/1500 with TIA Portal"
    },
    "allen_bradley": {
        "name": "Allen-Bradley Studio 5000",
        "language": "Structured Text",
        "file_ext": ".st",
        "description": "Rockwell ControlLogix/CompactLogix"
    },
    "codesys": {
        "name": "CODESYS",
        "language": "Structured Text (IEC 61131-3)",
        "file_ext": ".st",
        "description": "CODESYS V3 compatible PLCs"
    }
}
