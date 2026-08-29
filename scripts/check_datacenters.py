import asyncio
import json
import logging
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))

from src.adapters.runpod_adapter import runpod_adapter

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

async def check_all_datacenters():
    query_dcs = """
    query {
        dataCenters {
            id
            name
            location
        }
    }
    """
    res_dcs = await runpod_adapter._graphql_query(query_dcs)
    dcs = res_dcs.get("dataCenters", [])
    print(f"Total Datacenters on RunPod: {len(dcs)}")

    query_dc_gpus = """
    query GetGpusByDC($dcId: String!) {
        gpuTypes {
            id
            displayName
            memoryInGb
            communityPrice
            securePrice
            lowestPrice(input: {gpuCount: 1, dataCenterId: $dcId}) {
                minimumBidPrice
                uninterruptablePrice
            }
        }
    }
    """

    print("=" * 90)
    print("DATACENTERS WITH AVAILABLE >= 24GB GPUs")
    print("=" * 90)

    tx3_gpus = []

    for dc in dcs:
        dc_id = dc["id"]
        try:
            res = await runpod_adapter._graphql_query(query_dc_gpus, {"dcId": dc_id})
            avail = []
            for g in res.get("gpuTypes", []):
                lp = g.get("lowestPrice") or {}
                unint_price = lp.get("uninterruptablePrice")
                min_bid = lp.get("minimumBidPrice")
                price = unint_price if unint_price is not None else min_bid
                if price is not None and g.get("memoryInGb", 0) >= 24:
                    avail.append(f"{g['displayName']} ({g['memoryInGb']}GB @ ${price:.2f}/h)")
                    if dc_id == "US-TX-3":
                        tx3_gpus.append({
                            "gpu": g["displayName"],
                            "id": g["id"],
                            "vram": g["memoryInGb"],
                            "community": g.get("communityPrice"),
                            "secure": g.get("securePrice"),
                            "lowest": price
                        })
            if avail:
                print(f"[{dc_id:8s}] {dc.get('name', ''):20s} ({dc.get('location', ''):20s}): {', '.join(avail)}")
        except Exception as e:
            pass

    print("\n" + "=" * 90)
    print("SUMMARY FOR CURRENT VOLUME DATACENTER (US-TX-3):")
    print("=" * 90)
    if tx3_gpus:
        for g in tx3_gpus:
            print(f"  - {g['gpu']} ({g['id']}) | VRAM: {g['vram']}GB | Comm: ${g['community']}/h | Sec: ${g['secure']}/h | Lowest: ${g['lowest']}/h")
    else:
        print("  NO GPU AVAILABLE currently in US-TX-3")

if __name__ == "__main__":
    asyncio.run(check_all_datacenters())
