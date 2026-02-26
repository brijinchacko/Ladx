"""
TIA Portal Bridge Server
=========================
*** RUN THIS ON YOUR WINDOWS PC ***
*** (the one that has TIA Portal installed) ***

This is a small web server that lets your Mac-based AI agent
send commands to TIA Portal via the Openness API.

Setup:
1. Install Python on your Windows PC: python.org
2. pip install flask
3. Make sure TIA Portal Openness is enabled
4. Run: python tia_bridge_server.py

Your Mac agent connects to this server over your local network.
"""

import os
import sys
import json
import subprocess
import tempfile
from pathlib import Path
from datetime import datetime

try:
    from flask import Flask, request, jsonify
except ImportError:
    print("Flask is required. Install it with:")
    print("  pip install flask")
    sys.exit(1)

app = Flask(__name__)

# ===========================================
# Configuration
# ===========================================
TEMP_DIR = Path(tempfile.gettempdir()) / "plc_agent"
TEMP_DIR.mkdir(exist_ok=True)

# Path to your compiled TIA Bridge C# executable
# Update this after building the C# project
TIA_BRIDGE_EXE = os.environ.get(
    "TIA_BRIDGE_EXE",
    r"C:\PLCAgent\TIABridge\bin\Release\TIABridge.exe"
)

LOG_FILE = TEMP_DIR / "bridge_log.txt"


def log(message):
    """Log a message to file and console."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] {message}"
    print(line)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")


# ===========================================
# API Endpoints
# ===========================================

@app.route('/api/status', methods=['GET'])
def status():
    """Check if the bridge is running and TIA Portal is accessible."""
    tia_available = os.path.exists(TIA_BRIDGE_EXE)

    return jsonify({
        "bridge": "online",
        "tia_bridge_exe": TIA_BRIDGE_EXE,
        "tia_bridge_found": tia_available,
        "temp_dir": str(TEMP_DIR),
        "timestamp": datetime.now().isoformat()
    })


@app.route('/api/import-scl', methods=['POST'])
def import_scl():
    """Import SCL code into TIA Portal."""
    data = request.json
    block_name = data.get("block_name", "NewBlock")
    scl_code = data.get("scl_code", "")

    if not scl_code:
        return jsonify({"success": False, "message": "No SCL code provided"})

    log(f"Importing SCL block: {block_name}")

    # Save SCL to temp file
    scl_path = TEMP_DIR / f"{block_name}.scl"
    scl_path.write_text(scl_code, encoding="utf-8")

    # Call TIA Bridge
    try:
        result = subprocess.run(
            [TIA_BRIDGE_EXE, "import-block", "current", block_name, str(scl_path)],
            capture_output=True,
            text=True,
            timeout=60
        )

        success = result.returncode == 0
        message = result.stdout if success else result.stderr

        log(f"Import {'SUCCESS' if success else 'FAILED'}: {message}")

        return jsonify({
            "success": success,
            "message": message,
            "block_name": block_name,
            "file_path": str(scl_path)
        })

    except FileNotFoundError:
        msg = f"TIA Bridge executable not found at: {TIA_BRIDGE_EXE}"
        log(msg)
        return jsonify({"success": False, "message": msg})

    except subprocess.TimeoutExpired:
        msg = "TIA Portal operation timed out (60s)"
        log(msg)
        return jsonify({"success": False, "message": msg})


@app.route('/api/compile', methods=['POST'])
def compile_project():
    """Compile the current TIA Portal project."""
    data = request.json or {}
    block_name = data.get("block_name", "all")

    log(f"Compiling project (block: {block_name})")

    try:
        result = subprocess.run(
            [TIA_BRIDGE_EXE, "compile", "current"],
            capture_output=True,
            text=True,
            timeout=120
        )

        success = result.returncode == 0
        message = result.stdout if success else result.stderr

        log(f"Compile {'SUCCESS' if success else 'FAILED'}: {message}")

        return jsonify({
            "success": success,
            "message": message
        })

    except FileNotFoundError:
        msg = f"TIA Bridge executable not found at: {TIA_BRIDGE_EXE}"
        log(msg)
        return jsonify({"success": False, "message": msg})

    except subprocess.TimeoutExpired:
        msg = "Compilation timed out (120s)"
        log(msg)
        return jsonify({"success": False, "message": msg})


@app.route('/api/export-block', methods=['POST'])
def export_block():
    """Export a block from TIA Portal as XML."""
    data = request.json
    block_name = data.get("block_name", "")

    if not block_name:
        return jsonify({"success": False, "message": "No block name provided"})

    log(f"Exporting block: {block_name}")

    output_path = TEMP_DIR / f"{block_name}.xml"

    try:
        result = subprocess.run(
            [TIA_BRIDGE_EXE, "export-block", "current", block_name, str(output_path)],
            capture_output=True,
            text=True,
            timeout=30
        )

        success = result.returncode == 0

        if success and output_path.exists():
            xml_content = output_path.read_text(encoding="utf-8")
            log(f"Export SUCCESS: {block_name}")
            return jsonify({
                "success": True,
                "message": f"Exported {block_name}",
                "xml": xml_content
            })
        else:
            msg = result.stderr or "Export failed"
            log(f"Export FAILED: {msg}")
            return jsonify({"success": False, "message": msg})

    except FileNotFoundError:
        msg = f"TIA Bridge executable not found at: {TIA_BRIDGE_EXE}"
        log(msg)
        return jsonify({"success": False, "message": msg})


@app.route('/api/list-blocks', methods=['GET'])
def list_blocks():
    """List all blocks in the current TIA Portal project."""
    try:
        result = subprocess.run(
            [TIA_BRIDGE_EXE, "list-blocks", "current"],
            capture_output=True,
            text=True,
            timeout=30
        )

        if result.returncode == 0:
            blocks = result.stdout.strip().split("\n")
            return jsonify({"success": True, "blocks": blocks})
        else:
            return jsonify({"success": False, "message": result.stderr})

    except Exception as e:
        return jsonify({"success": False, "message": str(e)})


# ===========================================
# File-based mode (no TIA Bridge EXE needed)
# ===========================================

@app.route('/api/save-file', methods=['POST'])
def save_file():
    """
    Simple file-based mode: saves generated code to a shared folder.
    Use this if you haven't built the C# TIA Bridge yet.
    """
    data = request.json
    filename = data.get("filename", "generated_code.scl")
    content = data.get("content", "")
    save_dir = data.get("save_dir", str(TEMP_DIR))

    filepath = Path(save_dir) / filename
    filepath.parent.mkdir(parents=True, exist_ok=True)
    filepath.write_text(content, encoding="utf-8")

    log(f"File saved: {filepath}")

    return jsonify({
        "success": True,
        "message": f"Saved to {filepath}",
        "path": str(filepath)
    })


# ===========================================
# Run Server
# ===========================================

if __name__ == '__main__':
    print("=" * 60)
    print("  TIA Portal Bridge Server")
    print("  Run this on your WINDOWS PC")
    print("=" * 60)
    print(f"  Temp directory: {TEMP_DIR}")
    print(f"  TIA Bridge EXE: {TIA_BRIDGE_EXE}")
    print(f"  Log file: {LOG_FILE}")
    print()
    print("  Your Mac can connect to this server at:")
    print("  http://<THIS_PC_IP>:5050")
    print()
    print("  Find your IP with: ipconfig")
    print("=" * 60)

    app.run(
        host='0.0.0.0',  # Listen on all interfaces
        port=5050,
        debug=True
    )
