"""
DM AI OS — Remote Status Inspector (Python Core)
"""
import os
import sys
import json
import httpx
import asyncio
from datetime import datetime
from pathlib import Path

ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))

async def main():
    print("==========================================================")
    print("                DM AI OS — REMOTE STATUS                  ")
    print("==========================================================")
    print("")

    # 1. PC ONLINE
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[1/9] PC ONLINE:         ONLINE ({now})")

    # 2. DM AI OS Status
    url_file = ROOT_DIR / "tunnel_url.txt"
    tunnel_url = url_file.read_text().strip() if url_file.exists() else "http://127.0.0.1:8000"
    print(f"[2/9] DM AI OS TUNNEL:   {tunnel_url}")

    # 3. API GATEWAY
    gw_status = "OFFLINE"
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            r = await client.get("http://127.0.0.1:8000/health")
            if r.status_code == 200 and r.json().get("status") == "ONLINE":
                gw_status = "ONLINE (HTTP 200)"
    except Exception:
        pass
    print(f"[3/9] API GATEWAY:       {gw_status}")

    # 4. MCP SERVER
    mcp_status = "OFFLINE"
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            r = await client.get("http://127.0.0.1:8001/health")
            if r.status_code == 200 and r.json().get("status") == "ONLINE":
                mcp_status = "ONLINE (HTTP 200)"
            elif r.status_code == 200:
                mcp_status = f"ONLINE (HTTP {r.status_code})"
    except Exception:
        pass
    print(f"[4/9] MCP SERVER:        {mcp_status}")

    # 5. OLLAMA
    ollama_status = "OFFLINE"
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            r = await client.get("http://127.0.0.1:11434/api/tags")
            if r.status_code == 200:
                ollama_status = "ONLINE (Port 11434)"
    except Exception:
        pass
    print(f"[5/9] OLLAMA:            {ollama_status}")

    # RunPod Checks
    try:
        from src.adapters.runpod_adapter import runpod_adapter
        acc = await runpod_adapter.get_account_status()
        pods = await runpod_adapter.list_pods()
        active = [p for p in pods if p.get("desiredStatus") not in ("TERMINATED",)]
        vols = await runpod_adapter.list_network_volumes()
        vol = next((v for v in vols if v.get("id") == "tbupq29n08"), None)
        
        print(f"[6/9] RUNPOD API:        OK")
        print(f"[7/9] RUNPOD BALANCE:    ${acc.get('balance', 0.0):.2f} USD")
        print(f"[8/9] ACTIVE PODS:       {len(active)} (0 GPU COST)")
        vol_str = f"{vol.get('name')} ({vol.get('id')} / {vol.get('dataCenterId')})" if vol else "NOT FOUND"
        print(f"[9/9] NETWORK VOLUME:    {vol_str}")
    except Exception as e:
        print(f"[6/9] RUNPOD API:        ERROR ({e})")
        print(f"[7/9] RUNPOD BALANCE:    N/A")
        print(f"[8/9] ACTIVE PODS:       N/A")
        print(f"[9/9] NETWORK VOLUME:    N/A")

    print("")
    print("==========================================================")

if __name__ == "__main__":
    asyncio.run(main())
