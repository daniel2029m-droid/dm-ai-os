Set WshShell = CreateObject("WScript.Shell")
WshShell.CurrentDirectory = "C:\Users\moral\.gemini\antigravity-ide\scratch"

WshShell.Run "cmd /c C:\Users\moral\.gemini\antigravity-ide\scratch\.venv\Scripts\python.exe -m uvicorn src.api.server:app --host 0.0.0.0 --port 8000 > C:\Users\moral\.gemini\antigravity-ide\scratch\deployment\api_out.log 2>&1", 0, False
WshShell.Run "cmd /c C:\Users\moral\.gemini\antigravity-ide\scratch\.venv\Scripts\python.exe -m uvicorn src.mcp.mcp_server:mcp_app --host 0.0.0.0 --port 8001 > C:\Users\moral\.gemini\antigravity-ide\scratch\deployment\mcp_out.log 2>&1", 0, False
WshShell.Run "cmd /c powershell -NoProfile -ExecutionPolicy Bypass -File C:\Users\moral\.gemini\antigravity-ide\scratch\scripts\start_tunnel.ps1 > C:\Users\moral\.gemini\antigravity-ide\scratch\deployment\tunnel_out.log 2>&1", 0, False
