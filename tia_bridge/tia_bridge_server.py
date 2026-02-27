"""
TIA Portal Bridge Server (Openness API)
=========================================
*** RUN THIS ON YOUR WINDOWS PC ***
*** (the one that has TIA Portal V19 installed) ***

This server exposes TIA Portal automation via a REST API.
Your Mac-based LADX agent connects to this over the local network.

Setup:
1. Follow setup_guide.md to enable TIA Openness
2. pip install -r requirements.txt
3. Run: python tia_bridge_server.py

Your Mac agent connects at: http://<THIS_PC_IP>:5050
"""

import os
import sys
import json
import traceback
import tempfile
from pathlib import Path
from datetime import datetime

try:
    from flask import Flask, request, jsonify
except ImportError:
    print("Flask is required. Install it with:")
    print("  pip install flask")
    sys.exit(1)

# Import the TIA Openness wrapper
try:
    from tia_openness import TIAHandler
    TIA_AVAILABLE = True
except ImportError as e:
    print(f"Warning: Could not import TIA Openness wrapper: {e}")
    print("TIA Portal automation will not be available.")
    print("Only file-based operations will work.")
    TIA_AVAILABLE = False

app = Flask(__name__)

# ===========================================
# Configuration
# ===========================================
TEMP_DIR = Path(tempfile.gettempdir()) / "ladx_tia"
TEMP_DIR.mkdir(exist_ok=True)
LOG_FILE = TEMP_DIR / "bridge_log.txt"

# Initialize TIA handler (global singleton)
tia_handler = None

if TIA_AVAILABLE:
    try:
        tia_handler = TIAHandler()
    except Exception as e:
        print(f"Warning: TIAHandler init failed: {e}")
        print("TIA Portal automation will not be available.")


def log(message):
    """Log a message to file and console."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] {message}"
    print(line)
    try:
        with open(LOG_FILE, "a") as f:
            f.write(line + "\n")
    except Exception:
        pass


# ===========================================
# Status & Connection Endpoints
# ===========================================

@app.route('/api/status', methods=['GET'])
def status():
    """Check bridge status and TIA Portal connection."""
    if tia_handler:
        result = tia_handler.get_status()
    else:
        result = {
            "bridge": "online",
            "dll_loaded": False,
            "tia_portal_connected": False,
            "project_open": False,
            "message": "TIA Openness not available. File-based mode only.",
            "timestamp": datetime.now().isoformat(),
        }
    return jsonify(result)


@app.route('/api/connect', methods=['POST'])
def connect():
    """Connect to or launch TIA Portal."""
    if not tia_handler:
        return jsonify({
            "success": False,
            "message": "TIA Openness not available. Install pythonnet and ensure DLL is accessible.",
        })

    data = request.json or {}
    with_ui = data.get("with_ui", True)

    log(f"Connect request (with_ui={with_ui})")
    result = tia_handler.connect_or_launch(with_ui=with_ui)
    log(f"Connect result: {result.get('message')}")
    return jsonify(result)


@app.route('/api/disconnect', methods=['POST'])
def disconnect():
    """Close TIA Portal connection."""
    if not tia_handler:
        return jsonify({"success": False, "message": "TIA Openness not available"})

    log("Disconnect request")
    result = tia_handler.close()
    return jsonify(result)


# ===========================================
# Project Management Endpoints
# ===========================================

@app.route('/api/create-project', methods=['POST'])
def create_project():
    """Create a new TIA Portal project."""
    if not tia_handler:
        return jsonify({"success": False, "message": "TIA Openness not available"})

    data = request.json
    if not data:
        return jsonify({"success": False, "message": "No JSON data provided"})

    name = data.get("name", f"LADX_Project_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
    cpu_model = data.get("cpu_model", "CPU 1214C DC/DC/DC")

    log(f"Create project: name={name}, cpu={cpu_model}")
    result = tia_handler.create_project(name, cpu_model)
    log(f"Create project result: {result.get('message')}")
    return jsonify(result)


@app.route('/api/open-project', methods=['POST'])
def open_project():
    """Open an existing TIA Portal project."""
    if not tia_handler:
        return jsonify({"success": False, "message": "TIA Openness not available"})

    data = request.json
    if not data or not data.get("project_path"):
        return jsonify({"success": False, "message": "project_path is required"})

    log(f"Open project: {data['project_path']}")
    result = tia_handler.open_project(data["project_path"])
    return jsonify(result)


@app.route('/api/project-info', methods=['GET'])
def project_info():
    """Get current project details."""
    if not tia_handler:
        return jsonify({"success": False, "message": "TIA Openness not available"})

    result = tia_handler.get_project_info()
    return jsonify(result)


# ===========================================
# Hardware Configuration Endpoints
# ===========================================

@app.route('/api/configure-hardware', methods=['POST'])
def configure_hardware():
    """Add IO modules and configure network."""
    if not tia_handler:
        return jsonify({"success": False, "message": "TIA Openness not available"})

    data = request.json or {}
    io_modules = data.get("io_modules", [])
    profinet_ip = data.get("profinet_ip")

    log(f"Configure hardware: modules={io_modules}, ip={profinet_ip}")
    result = tia_handler.configure_hardware(io_modules=io_modules, profinet_ip=profinet_ip)
    return jsonify(result)


# ===========================================
# Code Import/Export Endpoints
# ===========================================

@app.route('/api/import-scl', methods=['POST'])
def import_scl():
    """Import SCL code into TIA Portal."""
    data = request.json
    if not data:
        return jsonify({"success": False, "message": "No JSON data provided"})

    block_name = data.get("block_name", "NewBlock")
    scl_code = data.get("scl_code", "")

    if not scl_code:
        return jsonify({"success": False, "message": "No SCL code provided"})

    log(f"Importing SCL block: {block_name}")

    # Always save the file (works even without TIA)
    scl_path = TEMP_DIR / f"{block_name}.scl"
    scl_path.write_text(scl_code, encoding="utf-8")

    if tia_handler and tia_handler.portal:
        # Import via TIA Openness
        result = tia_handler.import_scl_block(block_name, scl_code)
        result["file_path"] = str(scl_path)
        return jsonify(result)
    else:
        # File-based fallback
        log(f"TIA not connected — saved SCL to file: {scl_path}")
        return jsonify({
            "success": True,
            "message": f"SCL saved to file (TIA Portal not connected): {scl_path}",
            "block_name": block_name,
            "file_path": str(scl_path),
            "tia_imported": False,
        })


@app.route('/api/import-xml', methods=['POST'])
def import_xml():
    """Import a LAD/FBD block via SimaticML XML."""
    if not tia_handler:
        return jsonify({"success": False, "message": "TIA Openness not available"})

    data = request.json
    if not data or not data.get("xml_content"):
        return jsonify({"success": False, "message": "xml_content is required"})

    block_name = data.get("block_name", "imported_block")
    xml_content = data["xml_content"]

    log(f"Importing XML block: {block_name}")
    result = tia_handler.import_xml_block(xml_content, block_name)
    return jsonify(result)


@app.route('/api/export-block', methods=['POST'])
def export_block():
    """Export a block from TIA Portal as XML."""
    if not tia_handler:
        return jsonify({"success": False, "message": "TIA Openness not available"})

    data = request.json
    if not data or not data.get("block_name"):
        return jsonify({"success": False, "message": "block_name is required"})

    log(f"Exporting block: {data['block_name']}")
    result = tia_handler.export_block(data["block_name"])
    return jsonify(result)


@app.route('/api/list-blocks', methods=['GET'])
def list_blocks():
    """List all program blocks in the current project."""
    if not tia_handler:
        return jsonify({"success": False, "message": "TIA Openness not available", "blocks": []})

    result = tia_handler.list_blocks()
    return jsonify(result)


# ===========================================
# Compile & Download Endpoints
# ===========================================

@app.route('/api/compile', methods=['POST'])
def compile_project():
    """Compile the current TIA Portal project."""
    if not tia_handler:
        return jsonify({"success": False, "message": "TIA Openness not available"})

    log("Compiling project...")
    result = tia_handler.compile_project()
    log(f"Compile result: {result.get('message')}")
    return jsonify(result)


@app.route('/api/download', methods=['POST'])
def download_to_plc():
    """Download compiled project to PLC."""
    if not tia_handler:
        return jsonify({"success": False, "message": "TIA Openness not available"})

    data = request.json or {}
    plc_ip = data.get("plc_ip", "192.168.0.1")

    log(f"Downloading to PLC at {plc_ip}...")
    result = tia_handler.download_to_plc(plc_ip=plc_ip)
    log(f"Download result: {result.get('message')}")
    return jsonify(result)


@app.route('/api/go-online', methods=['POST'])
def go_online():
    """Establish online connection to PLC."""
    if not tia_handler:
        return jsonify({"success": False, "message": "TIA Openness not available"})

    data = request.json or {}
    plc_ip = data.get("plc_ip", "192.168.0.1")

    log(f"Going online with PLC at {plc_ip}...")
    result = tia_handler.go_online(plc_ip=plc_ip)
    return jsonify(result)


# ===========================================
# File-based Mode (always works, no TIA needed)
# ===========================================

@app.route('/api/save-file', methods=['POST'])
def save_file():
    """
    Save generated code to a file.
    Works without TIA Portal — always available.
    """
    data = request.json
    if not data:
        return jsonify({"success": False, "message": "No JSON data provided"})

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
        "path": str(filepath),
    })


# ===========================================
# Logs Endpoint
# ===========================================

@app.route('/api/logs', methods=['GET'])
def get_logs():
    """Get recent bridge log entries."""
    count = request.args.get("count", 50, type=int)

    if tia_handler:
        logs = tia_handler.get_logs(count)
    else:
        logs = []
        if LOG_FILE.exists():
            lines = LOG_FILE.read_text().strip().split("\n")
            logs = lines[-count:]

    return jsonify({"logs": logs, "count": len(logs)})


# ===========================================
# Run Server
# ===========================================

if __name__ == '__main__':
    print("=" * 60)
    print("  TIA Portal Bridge Server (Openness API)")
    print("  Run this on your WINDOWS PC with TIA Portal V19")
    print("=" * 60)
    print(f"  Temp directory: {TEMP_DIR}")
    print(f"  Log file:       {LOG_FILE}")
    print(f"  TIA Openness:   {'Available' if TIA_AVAILABLE else 'NOT available'}")
    if tia_handler:
        print(f"  DLL path:       {tia_handler.dll_path}")
        print(f"  DLL loaded:     {tia_handler._initialized}")
    print()
    print("  Your Mac can connect to this server at:")
    print("  http://<THIS_PC_IP>:5050")
    print()
    print("  Find your IP with: ipconfig")
    print("=" * 60)

    app.run(
        host='0.0.0.0',
        port=5050,
        debug=False,  # debug=False for production use with TIA Portal
    )
