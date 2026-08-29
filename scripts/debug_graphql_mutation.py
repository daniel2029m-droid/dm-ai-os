"""
Debug RunPod GraphQL Mutations — DM AI OS
=========================================
Tests minimal podFindAndDeploy inputs to find exact valid GraphQL parameters.
"""

import sys
import asyncio
import logging
from pathlib import Path

ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("debug_graphql")

from src.adapters.runpod_adapter import runpod_adapter

async def debug_mutations():
    log.info("Testing podFindAndDeploy input parameters...")

    gpu_candidates = [
        ("NVIDIA GeForce RTX 4090", "COMMUNITY"),
        ("NVIDIA GeForce RTX 4090", "SECURE"),
        ("NVIDIA RTX A4000", "COMMUNITY"),
        ("NVIDIA RTX A4000", "SECURE"),
        ("NVIDIA GeForce RTX 3090", "COMMUNITY"),
        ("NVIDIA GeForce RTX 3090", "SECURE"),
        ("NVIDIA L4", "COMMUNITY"),
        ("NVIDIA L4", "SECURE"),
    ]

    mutation = """
    mutation PodFindAndDeployOnDemand($input: PodFindAndDeployOnDemandInput!) {
        podFindAndDeployOnDemand(input: $input) {
            id
            imageName
            desiredStatus
        }
    }
    """

    for gpu, cloud in gpu_candidates:
        log.info(f"Testing podFindAndDeployOnDemand for {gpu} ({cloud}) with templateId 'cw3nka7d08'...")
        inp = {
            "name": "DM-AI-OS-StockTest",
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
                log.info(f"🎉 SUCCESS! Stock available for {gpu} ({cloud}) | Pod ID: {pod_id}")
                log.info(f"Terminating test pod {pod_id} immediately...")
                await runpod_adapter.terminate_pod(pod_id)
                break
        except Exception as e:
            log.warning(f"No stock for {gpu} ({cloud}): {e}")

        log.info(f"Testing podFindAndDeployOnDemand for {gpu} ({cloud}) with imageName 'runpod/comfyui:cuda12.8'...")
        inp_img = {
            "name": "DM-AI-OS-StockTest",
            "gpuTypeId": gpu,
            "imageName": "runpod/comfyui:cuda12.8",
            "cloudType": cloud,
            "volumeInGb": 20,
            "containerDiskInGb": 20
        }
        try:
            res = await runpod_adapter._graphql_query(mutation, {"input": inp_img})
            pod = res.get("podFindAndDeployOnDemand", {})
            pod_id = pod.get("id")
            if pod_id:
                log.info(f"🎉 SUCCESS! Stock available for {gpu} ({cloud}) with imageName | Pod ID: {pod_id}")
                log.info(f"Terminating test pod {pod_id} immediately...")
                await runpod_adapter.terminate_pod(pod_id)
                break
        except Exception as e:
            log.warning(f"No stock for {gpu} ({cloud}) with imageName: {e}")




if __name__ == "__main__":
    asyncio.run(debug_mutations())
