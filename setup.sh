#!/bin/bash
# ===========================================
# LADX - Mac Setup Script
# ===========================================
# Run this script on your Mac to install everything:
#   chmod +x setup.sh
#   ./setup.sh
# ===========================================

set -e  # Exit on error

echo "============================================"
echo "  LADX - Setup"
echo "============================================"
echo ""

# Check for Python
if command -v python3 &> /dev/null; then
    PYTHON_VERSION=$(python3 --version 2>&1)
    echo "✅ Python found: $PYTHON_VERSION"
else
    echo "❌ Python 3 not found!"
    echo "   Install it with: brew install python@3.12"
    echo "   Or download from: https://python.org"
    exit 1
fi

# Check for pip
if command -v pip3 &> /dev/null; then
    echo "✅ pip found"
else
    echo "❌ pip not found!"
    echo "   Usually comes with Python. Try: python3 -m ensurepip"
    exit 1
fi

# Create virtual environment
echo ""
echo "📦 Creating virtual environment..."
if [ ! -d "venv" ]; then
    python3 -m venv venv
    echo "   Created venv/"
else
    echo "   venv/ already exists"
fi

# Activate virtual environment
source venv/bin/activate
echo "✅ Virtual environment activated"

# Install dependencies
echo ""
echo "📦 Installing Python dependencies..."
echo "   This may take a few minutes on first run..."
pip install --upgrade pip
pip install -r requirements.txt

echo ""
echo "✅ All dependencies installed!"

# Create .env from example if it doesn't exist
if [ ! -f ".env" ]; then
    cp .env.example .env
    echo ""
    echo "📝 Created .env file from .env.example"
    echo "   IMPORTANT: Edit .env and add your Anthropic API key!"
    echo "   Open it with: nano .env"
else
    echo "✅ .env file already exists"
fi

# Create necessary directories
mkdir -p output
mkdir -p knowledge/{siemens/{manuals,examples},allen_bradley/{manuals,examples},standards,templates}
echo "✅ Directory structure created"

# Create .gitignore
cat > .gitignore << 'GITIGNORE'
# Environment
venv/
.env

# Knowledge base
chroma_db/
knowledge/

# Output
output/

# Python
__pycache__/
*.pyc
*.pyo
.pytest_cache/

# IDE
.vscode/
.idea/
*.swp
*.swo

# OS
.DS_Store
Thumbs.db
GITIGNORE
echo "✅ Created .gitignore"

echo ""
echo "============================================"
echo "  Setup Complete!"
echo "============================================"
echo ""
echo "  Next steps:"
echo ""
echo "  1. Add your API key:"
echo "     nano .env"
echo "     (paste your Anthropic API key)"
echo ""
echo "  2. Test the agent (CLI mode):"
echo "     source venv/bin/activate"
echo "     python plc_agent.py"
echo ""
echo "  3. Start the web interface:"
echo "     source venv/bin/activate"
echo "     python web_app.py"
echo "     (then open http://localhost:8000)"
echo ""
echo "  4. Add your PLC docs to knowledge/ and run:"
echo "     python build_knowledge_base.py"
echo ""
echo "============================================"
