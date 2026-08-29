"""
DM AI OS — Resilient Background Services Launcher
Starts API Gateway (8000) and MCP Server (8001) as persistent background processes.
"""
import sys
import time
import socket
import subprocess
from pathlib import Path

ROOT_DIR = Path(__file__).parent.parent
VENV_PYTHON = ROOT_DIR / ".venv" / "Scripts" / "python.exe"
PYTHON_CMD = str(VENV_PYTHON) if VENV_PYTHON.exists() else sys.executable

def is_port_listening(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(1.0)
        return s.connect_ex(('127.0.0.1', port)) == 0

def launch_api():
    if is_port_listening(8000):
        print("[API Gateway] Already running on port 8000.")
        return
    print("[API Gateway] Starting on port 8000...")
    log_err = open(ROOT_DIR / "deployment" / "api_gw_err.log", "a", encoding="utf-8")
    log_out = open(ROOT_DIR / "deployment" / "api_gw_out.log", "a", encoding="utf-8")
    
    # DETACHED_PROCESS = 0x00000008, CREATE_NEW_PROCESS_GROUP = 0x00000200
    flags = 0x00000008 | 0x00000200
    p = subprocess.Popen(
        [PYTHON_CMD, "-m", "uvicorn", "src.api.server:app", "--host", "0.0.0.0", "--port", "8000", "--log-level", "info"],
        cwd=str(ROOT_DIR),
        stdout=log_out,
        stderr=log_err,
        creationflags=flags,
        close_fds=True
    )
    # Prevent garbage collection of file descriptors
    globals()["_api_proc"] = p
    globals()["_api_out"] = log_out
    globals()["_api_err"] = log_err

def launch_mcp():
    if is_port_listening(8001):
        print("[MCP Server] Already running on port 8001.")
        return
    print("[MCP Server] Starting on port 8001...")
    log_err = open(ROOT_DIR / "deployment" / "mcp_err.log", "a", encoding="utf-8")
    log_out = open(ROOT_DIR / "deployment" / "mcp_out.log", "a", encoding="utf-8")
    
    flags = 0x00000008 | 0x00000200
    p = subprocess.Popen(
        [PYTHON_CMD, "-m", "uvicorn", "src.mcp.mcp_server:mcp_app", "--host", "0.0.0.0", "--port", "8001", "--log-level", "info"],
        cwd=str(ROOT_DIR),
        stdout=log_out,
        stderr=log_err,
        creationflags=flags,
        close_fds=True
    )
    globals()["_mcp_proc"] = p
    globals()["_mcp_out"] = log_out
    globals()["_mcp_err"] = log_err

def launch_tunnel():
    cf_procs = subprocess.run(["tasklist", "/FI", "IMAGENAME eq cloudflared.exe"], capture_output=True, text=True)
    if "cloudflared.exe" in cf_procs.stdout:
        print("[Tunnel] cloudflared already running.")
        return
    print("[Tunnel] Starting Cloudflare Quick Tunnel...")
    ps_cmd = [
        "powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
        "-File", str(ROOT_DIR / "scripts" / "start_tunnel.ps1")
    ]
    flags = 0x00000008 | 0x00000200
    p = subprocess.Popen(ps_cmd, cwd=str(ROOT_DIR), creationflags=flags)
    globals()["_tunnel_proc"] = p

if __name__ == "__main__":
    launch_api()
    launch_mcp()
    launch_tunnel()
    
    # Poll for up to 10 seconds to verify ports
    for i in range(10):
        time.sleep(1)
        api_ok = is_port_listening(8000)
        mcp_ok = is_port_listening(8001)
        if api_ok and mcp_ok:
            print(f"[SUCCESS] All background services active after {i+1}s.")
            break
    print("API Gateway (8000):", "ONLINE" if is_port_listening(8000) else "OFFLINE")
    print("MCP Server (8001): ", "ONLINE" if is_port_listening(8001) else "OFFLINE")
