"""
RunPod Resource Discovery Script — DM AI OS
===========================================
Queries RunPod GraphQL API for real available GPU types, templates, prices, and VRAM specifications.
Consumes $0.00 credits (Metadata API query only).
"""

import sys
import os
import json
import asyncio
import logging
from pathlib import Path

ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("discover_runpod_resources")

from src.config.runpod_config import runpod_config
from src.adapters.runpod_adapter import runpod_adapter


async def discover():
    log.info("Starting RunPod Real Resource Discovery via GraphQL API...")

    if not runpod_config.is_configured:
        log.error("RUNPOD_API_KEY is missing from environment.")
        return

    # Query 1: GPU Types & Real Prices
    query_gpus = """
    query {
        gpuTypes {
            id
            displayName
            memoryInGb
            securePrice
            communityPrice
            secureSpotPrice
            communitySpotPrice
        }
    }
    """

    # Query 2: Pod Templates
    query_templates = """
    query {
        myself {
            id
            email
            clientBalance
            podTemplates {
                id
                name
                imageName
                containerDiskInGb
                volumeInGb
            }
        }
    }
    """

    results = {}

    try:
        gpu_data = await runpod_adapter._graphql_query(query_gpus)
        results["gpu_types"] = gpu_data.get("gpuTypes", [])
        log.info(f"Retrieved {len(results['gpu_types'])} GPU types from RunPod.")
    except Exception as e:
        log.error(f"Failed to query gpuTypes: {e}")
        results["gpu_types"] = []

    try:
        user_data = await runpod_adapter._graphql_query(query_templates)
        myself = user_data.get("myself", {})
        results["myself"] = myself
        log.info(f"User Balance: ${myself.get('clientBalance', 0.0):.2f}")
        log.info(f"User Templates: {len(myself.get('podTemplates', []))} found.")
    except Exception as e:
        log.error(f"Failed to query myself/podTemplates: {e}")

    # Save discovery output to JSON file for reference
    out_file = ROOT_DIR / "logs" / "runpod_discovery_results.json"
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(json.dumps(results, indent=2), encoding="utf-8")
    log.info(f"Discovery details written to {out_file}")

    return results


if __name__ == "__main__":
    asyncio.run(discover())
