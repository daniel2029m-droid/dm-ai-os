"""
DM AI OS — Headless Breakaway Daemon Launcher
Launches API Gateway, MCP Server, and Cloudflare Tunnel as persistent Windows background processes.
"""
import os
import sys
import time
import socket
import subprocess
from pathlib import Path

ROOT_DIR = Path(__file__).parent.parent
VENV_PYTHON = ROOT_DIR / ".venv" / "Scripts" / "python.exe"

def is_port_listening(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(1.0)
        return s.connect_ex(('127.0.0.1', port)) == 0

def launch_service(cmd_list, log_name):
    log_path = ROOT_DIR / "deployment" / log_name
    f = open(log_path, "a", encoding="utf-8")
    flags = 0x01000000 | 0x00000008 | 0x00000200
    try:
        p = subprocess.Popen(cmd_list, cwd=str(ROOT_DIR), stdout=f, stderr=f, creationflags=flags)
        return p
    except Exception:
        flags = 0x00000008 | 0x00000200
        p = subprocess.Popen(cmd_list, cwd=str(ROOT_DIR), stdout=f, stderr=f, creationflags=flags)
        return p

def main():
    py = str(VENV_PYTHON) if VENV_PYTHON.exists() else sys.executable
    
    if not is_port_listening(8000):
        print("[API Gateway] Starting on port 8000...")
        launch_service([py, "-m", "uvicorn", "src.api.server:app", "--host", "0.0.0.0", "--port", "8000", "--log-level", "info"], "api_gateway.log")
    else:
        print("[API Gateway] Already running on port 8000.")

    if not is_port_listening(8001):
        print("[MCP Server] Starting on port 8001...")
        launch_service([py, "-m", "uvicorn", "src.mcp.mcp_server:mcp_app", "--host", "0.0.0.0", "--port", "8001", "--log-level", "info"], "mcp_server.log")
    else:
        print("[MCP Server] Already running on port 8001.")

    cf_procs = subprocess.run(["tasklist", "/FI", "IMAGENAME eq cloudflared.exe"], capture_output=True, text=True)
    if "cloudflared.exe" not in cf_procs.stdout:
        print("[Tunnel] Starting Cloudflare Quick Tunnel...")
        ps_script = str(ROOT_DIR / "scripts" / "start_tunnel.ps1")
        launch_service(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", ps_script], "tunnel.log")
    else:
        print("[Tunnel] cloudflared process already active.")

if __name__ == "__main__":
    main()
