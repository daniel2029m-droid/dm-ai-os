import sys
import asyncio
from pathlib import Path
ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))
from src.adapters.runpod_adapter import runpod_adapter

async def check_vols():
    vols = await runpod_adapter.list_network_volumes()
    print("Network Volumes on account:")
    for v in vols:
        print(f"ID: {v.get('id')} | Name: {v.get('name')} | Size: {v.get('size')} GB")

if __name__ == "__main__":
    asyncio.run(check_vols())
