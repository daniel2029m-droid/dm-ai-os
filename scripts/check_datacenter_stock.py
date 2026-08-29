"""
Check GPU Stock across Datacenters — DM AI OS
==============================================
Finds datacenters with available RTX 4090 / RTX 3090 stock.
"""

import sys
import asyncio
import logging
from pathlib import Path

ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("check_dc_stock")

from src.adapters.runpod_adapter import runpod_adapter

async def find_stock():
    mutation = """
    mutation PodFindAndDeployOnDemand($input: PodFindAndDeployOnDemandInput!) {
        podFindAndDeployOnDemand(input: $input) {
            id
            desiredStatus
            machine {
                podHostId
                gpuDisplayName
            }
        }
    }
    """
    
    gpus_to_test = ["NVIDIA GeForce RTX 4090", "NVIDIA GeForce RTX 3090", "NVIDIA L40S"]
    cloud_types = ["COMMUNITY", "SECURE"]
    
    log.info("Testing global GPU stock without datacenter restriction...")
    for gpu in gpus_to_test:
        for cloud in cloud_types:
            inp = {
                "name": "DM-AI-OS-StockCheck",
                "gpuTypeId": gpu,
                "gpuCount": 1,
                "templateId": "cw3nka7d08",
                "cloudType": cloud,
                "volumeInGb": 20,
                "containerDiskInGb": 20
            }
            try:
                res = await runpod_adapter._graphql_query(mutation, {"input": inp})
                pod = res.get("podFindAndDeployOnDemand", {})
                pod_id = pod.get("id")
                if pod_id:
                    log.info(f"🎉 GLOBAL STOCK FOUND! GPU: {gpu} ({cloud}) | Pod ID: {pod_id}")
                    # Terminate pod immediately
                    await runpod_adapter.terminate_pod(pod_id)
                    return
            except Exception as e:
                log.info(f"Global stock check for {gpu} ({cloud}): {e}")

if __name__ == "__main__":
    asyncio.run(find_stock())
