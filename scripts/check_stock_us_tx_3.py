"""
Check Available GPUs in Datacenter US-TX-3 — DM AI OS
=====================================================
Queries RunPod GraphQL API for available GPU stock in US-TX-3.
"""

import sys
import asyncio
import logging
from pathlib import Path

ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("check_stock_dc")

from src.adapters.runpod_adapter import runpod_adapter

async def check_dc_stock():
    query = """
    query {
        gpuTypes {
            id
            displayName
            memoryInGb
            communityPrice
            securePrice
        }
    }
    """
    data = await runpod_adapter._graphql_query(query)
    gpus = data.get("gpuTypes", [])
    
    mutation = """
    mutation PodFindAndDeployOnDemand($input: PodFindAndDeployOnDemandInput!) {
        podFindAndDeployOnDemand(input: $input) {
            id
            desiredStatus
        }
    }
    """

    log.info(f"Checking stock across {len(gpus)} GPU types in datacenter US-TX-3...")
    available = []
    
    # Priority order for FLUX.2 (needs >= 16GB VRAM)
    high_priority = [g for g in gpus if g.get("memoryInGb", 0) >= 16]
    high_priority.sort(key=lambda g: g.get("communityPrice") or 99.0)

    for g in high_priority[:10]:
        gpu_name = g.get("id")
        displayName = g.get("displayName")
        mem = g.get("memoryInGb")
        price = g.get("communityPrice") or g.get("securePrice")
        
        for cloud in ["COMMUNITY", "SECURE"]:
            inp = {
                "name": "DM-AI-OS-StockTest",
                "gpuTypeId": gpu_name,
                "gpuCount": 1,
                "templateId": "cw3nka7d08",
                "cloudType": cloud,
                "dataCenterId": "US-TX-3",
                "volumeInGb": 0,
                "containerDiskInGb": 20,
                "networkVolumeId": "tbupq29n08"
            }
            try:
                res = await runpod_adapter._graphql_query(mutation, {"input": inp})
                pod = res.get("podFindAndDeployOnDemand", {})
                pod_id = pod.get("id")
                if pod_id:
                    log.info(f"🎉 AVAILABLE IN US-TX-3! GPU: '{displayName}' ({gpu_name}) | Cloud: {cloud} | VRAM: {mem}GB | Price: ${price}/h | Pod ID: {pod_id}")
                    await runpod_adapter.terminate_pod(pod_id)
                    available.append({"id": gpu_name, "name": displayName, "cloud": cloud, "mem": mem, "price": price})
                    return
            except Exception as e:
                pass

    if not available:
        log.warning("No GPU with >=16GB VRAM currently in stock in US-TX-3 attached to Network Volume tbupq29n08.")

if __name__ == "__main__":
    asyncio.run(check_dc_stock())
