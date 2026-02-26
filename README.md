# LADX — Your AI Partner for PLC Programming

An AI agent that generates PLC code, troubleshoots faults, converts between platforms, and integrates with Siemens TIA Portal. Built by Brijin.

## Supported Platforms

- **Siemens TIA Portal** (S7-1200, S7-1500) — SCL/Structured Text
- **Allen-Bradley Studio 5000** (ControlLogix, CompactLogix) — Structured Text
- **CODESYS** — IEC 61131-3 Structured Text

## Quick Start (Mac)

```bash
# 1. Clone or download this project
cd ladx

# 2. Run the setup script
chmod +x setup.sh
./setup.sh

# 3. Add your Anthropic API key
nano .env
# Paste your key: ANTHROPIC_API_KEY=sk-ant-xxxxx

# 4. Start the web interface
source venv/bin/activate
python web_app.py

# 5. Open in browser
# http://localhost:8000
```

## Project Structure

```
ladx/
├── .env.example          # Environment config template
├── .env                  # Your API keys (create from .env.example)
├── requirements.txt      # Python dependencies
├── setup.sh             # Mac setup script
├── config.py            # Configuration loader
├── system_prompt.txt    # AI system prompt (your PLC expertise)
├── plc_agent.py         # Core agent (AI brain + tools)
├── web_app.py           # Web interface server
├── build_knowledge_base.py  # Knowledge base builder
├── knowledge/           # Your PLC documentation & examples
│   ├── siemens/
│   ├── allen_bradley/
│   ├── standards/
│   └── templates/       # Code templates (examples included)
├── output/              # Generated PLC code saved here
├── web/
│   └── templates/
│       └── index.html   # Chat interface
└── tia_bridge/
    └── tia_bridge_server.py  # Windows TIA Portal bridge
```

## Two Ways to Use

### 1. Web Interface (Recommended)
```bash
python web_app.py
# Open http://localhost:8000
```

### 2. Command Line
```bash
python plc_agent.py
# Type your requests directly in the terminal
```

## Features

| Feature | What It Does |
|---------|-------------|
| Code Generation | Natural language → compilable SCL/ST code |
| Troubleshooting | Describe the problem → get diagnosis & fix |
| Code Conversion | Siemens ↔ Allen-Bradley automatic conversion |
| Code Explanation | Paste code → get detailed analysis |
| Tag List Generator | Describe system → get importable tag list |
| TIA Portal Bridge | Send code directly to TIA Portal (optional) |

## Adding Your Knowledge Base

The agent works out of the box, but gets much better when you add your own documentation:

```bash
# Add your files to knowledge/
cp ~/my-plc-manuals/*.pdf knowledge/siemens/manuals/
cp ~/my-best-code/*.scl knowledge/siemens/examples/

# Build the searchable database
python build_knowledge_base.py
```

## TIA Portal Bridge (Optional)

To send code directly to TIA Portal from your Mac:

1. Copy `tia_bridge/tia_bridge_server.py` to your Windows PC
2. Install Flask: `pip install flask`
3. Run: `python tia_bridge_server.py`
4. Update `.env` on your Mac with the Windows PC's IP address

## Getting Your API Key

1. Go to https://console.anthropic.com
2. Create an account
3. Go to API Keys → Create Key
4. Copy the key into your `.env` file
