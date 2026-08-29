"""
RunPod GPU Diagnostic Script — DM AI OS
=======================================
Queries RunPod GraphQL API for:
1. Available GPUs in datacenter US-TX-3 (Network Volume tbupq29n08 location).
2. Available GPUs globally (VRAM >= 24GB).

NO PODS ARE CREATED. NO CREDIT IS SPENT.
"""

import sys
import os
import json
import asyncio
import logging
from pathlib import Path

ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))

from src.adapters.runpod_adapter import runpod_adapter

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("diagnose_gpus")


async def diagnose():
    # Query all GPU types
    query_all = """
    query {
        gpuTypes {
            id
            displayName
            memoryInGb
            securePrice
            communityPrice
            secureSpotPrice
            lowestPrice(input: {gpuCount: 1}) {
                minimumBidPrice
                uninterruptablePrice
            }
        }
    }
    """

    # Query with dataCenterId filter if supported
    query_dc = """
    query GetGpusByDC($dcId: String!) {
        gpuTypes {
            id
            displayName
            memoryInGb
            securePrice
            communityPrice
            lowestPrice(input: {gpuCount: 1, dataCenterId: $dcId}) {
                minimumBidPrice
                uninterruptablePrice
            }
        }
    }
    """

    res_all = await runpod_adapter._graphql_query(query_all)
    all_gpus = res_all.get("gpuTypes", [])

    # Filter >= 24GB
    gpus_24gb = [g for g in all_gpus if g.get("memoryInGb", 0) >= 24]

    # Query US-TX-3 specifically
    tx3_gpus = []
    try:
        res_tx3 = await runpod_adapter._graphql_query(query_dc, {"dcId": "US-TX-3"})
        for g in res_tx3.get("gpuTypes", []):
            lp = g.get("lowestPrice")
            if lp and (lp.get("minimumBidPrice") is not None or lp.get("uninterruptablePrice") is not None):
                tx3_gpus.append({
                    "id": g.get("id"),
                    "displayName": g.get("displayName"),
                    "memoryInGb": g.get("memoryInGb"),
                    "communityPrice": g.get("communityPrice"),
                    "securePrice": g.get("securePrice"),
                    "lowestPrice": lp
                })
    except Exception as e:
        log.warning(f"DC specific query note: {e}")

    print("=" * 80)
    print("RUNPOD GPU DIAGNOSTIC REPORT")
    print("=" * 80)
    print(f"DATACENTER US-TX-3 AVAILABLE GPUs ({len(tx3_gpus)} found):")
    print("-" * 80)
    for g in tx3_gpus:
        print(f"  - {g['displayName']} ({g['id']}) | VRAM: {g['memoryInGb']}GB | Community: ${g['communityPrice']}/h | Secure: ${g['securePrice']}/h | Lowest: {g['lowestPrice']}")

    print("\n" + "=" * 80)
    print(f"GLOBAL GPUs (>= 24GB VRAM) ({len(gpus_24gb)} types available on RunPod):")
    print("-" * 80)
    for g in sorted(gpus_24gb, key=lambda x: x.get("memoryInGb", 0)):
        lp = g.get("lowestPrice", {})
        avail = "AVAILABLE" if (lp and (lp.get("uninterruptablePrice") is not None or lp.get("minimumBidPrice") is not None)) else "OUT OF STOCK"
        print(f"  [{avail:12s}] {g['displayName']:30s} ({g['id']:35s}) | {g['memoryInGb']:3d}GB | Comm: ${g.get('communityPrice', 0):.2f}/h | Sec: ${g.get('securePrice', 0):.2f}/h")

if __name__ == "__main__":
    asyncio.run(diagnose())
