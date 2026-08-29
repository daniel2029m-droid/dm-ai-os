"""
DM AI OS — RunPod Multi-Datacenter GPU Query & Diagnostic
==========================================================
Queries ALL datacenters concurrently via RunPod GraphQL API.
Checks stock for all NVIDIA GPUs with >= 24GB VRAM.
NO PODS ARE CREATED. NO CREDIT IS SPENT.
"""

import sys
import os
import asyncio
import logging
from pathlib import Path

ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))

from src.adapters.runpod_adapter import runpod_adapter

logging.basicConfig(level=logging.WARNING)


async def check_dc(dc: dict, query_dc_gpus: str):
    dc_id = dc["id"]
    dc_name = dc.get("name", "")
    dc_loc = dc.get("location", "")
    try:
        res = await runpod_adapter._graphql_query(query_dc_gpus, {"dcId": dc_id})
        avail_gpus = []
        for g in res.get("gpuTypes", []):
            lp = g.get("lowestPrice") or {}
            min_bid = lp.get("minimumBidPrice")
            unint = lp.get("uninterruptablePrice")
            price = unint if unint is not None else min_bid
            vram = g.get("memoryInGb", 0)

            if price is not None and vram >= 24:
                avail_gpus.append({
                    "gpu": g.get("displayName", g.get("id")),
                    "id": g.get("id"),
                    "vram": vram,
                    "datacenter": dc_id,
                    "location": f"{dc_name} ({dc_loc})",
                    "community": g.get("communityPrice"),
                    "secure": g.get("securePrice"),
                    "lowest": price
                })
        return avail_gpus
    except Exception:
        return []


async def run_query():
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

    # Query all datacenters in parallel using asyncio.gather
    tasks = [check_dc(dc, query_dc_gpus) for dc in dcs]
    results = await asyncio.gather(*tasks)

    tx3_gpus = []
    global_gpus = []

    for r_list in results:
        for g in r_list:
            global_gpus.append(g)
            if g["datacenter"] == "US-TX-3":
                tx3_gpus.append(g)

    # Preferred ranking for selection
    priority_order = [
        "RTX 4090",
        "RTX 5090",
        "RTX 3090",
        "A40",
        "L40S",
        "A100",
        "RTX A6000",
        "RTX 6000",
        "L40",
        "RTX A5000",
        "RTX 5000"
    ]

    def gpu_rank(item):
        name = item["gpu"].upper()
        for idx, p in enumerate(priority_order):
            if p.upper() in name:
                return idx
        return 99

    tx3_gpus.sort(key=gpu_rank)
    global_gpus.sort(key=lambda x: (gpu_rank(x), x["lowest"]))

    print("\n" + "=" * 90)
    print("DM AI OS — RUNPOD GPU AVAILABILITY AUDIT")
    print("Current Network Volume: tbupq29n08 | Location: US-TX-3")
    print("=" * 90)

    print("\n### GPUs DISPONIBLES EN US-TX-3 (DATACENTER DEL VOLUME tbupq29n08)")
    print("-" * 90)
    if tx3_gpus:
        print(f"{'GPU':<25} | {'VRAM':<6} | {'DATACENTER':<10} | {'COMMUNITY':<10} | {'SECURE':<10} | {'COMPATIBLE VOLUME'}")
        print("-" * 90)
        for g in tx3_gpus:
            comm_str = f"${g['community']:.2f}/h" if g['community'] else "N/A"
            sec_str = f"${g['secure']:.2f}/h" if g['secure'] else "N/A"
            comp_str = "YES (tbupq29n08)" if g['datacenter'] == "US-TX-3" else "NO (Requires new volume)"
            print(f"{g['gpu']:<25} | {g['vram']:<4}GB | {g['datacenter']:<10} | {comm_str:<10} | {sec_str:<10} | {comp_str}")
    else:
        print("NO GPUS WITH >=24GB VRAM AVAILABLE IN US-TX-3 CURRENTLY.")

    print("\n### TOP GPUs DISPONIBLES EN OTROS DATACENTERS (GLOBAL >= 24GB VRAM)")
    print("-" * 90)
    print(f"{'GPU':<25} | {'VRAM':<6} | {'DATACENTER':<10} | {'COMMUNITY':<10} | {'SECURE':<10} | {'COMPATIBLE VOLUME'}")
    print("-" * 90)

    seen = set()
    count = 0
    for g in global_gpus:
        key = (g['gpu'], g['datacenter'])
        if key not in seen:
            seen.add(key)
            comm_str = f"${g['community']:.2f}/h" if g['community'] else "N/A"
            sec_str = f"${g['secure']:.2f}/h" if g['secure'] else "N/A"
            comp_str = "YES (tbupq29n08)" if g['datacenter'] == "US-TX-3" else "NO (Requires new volume)"
            print(f"{g['gpu']:<25} | {g['vram']:<4}GB | {g['datacenter']:<10} | {comm_str:<10} | {sec_str:<10} | {comp_str}")
            count += 1
            if count >= 20:
                break

    print("\n" + "=" * 90)
    print("RECOMENDACION FINAL:")
    print("=" * 90)
    if tx3_gpus:
        best = tx3_gpus[0]
        print(f"BEST GPU FOR CURRENT VOLUME: {best['gpu']} ({best['vram']}GB VRAM) in US-TX-3 at ${best['lowest']:.2f}/h")
    else:
        print("CURRENT VOLUME HAS NO AVAILABLE GPU IN US-TX-3.")
        best_alt = global_gpus[0] if global_gpus else None
        if best_alt:
            print(f"BEST ALTERNATIVE DATACENTER FOR NEW VOLUME: {best_alt['datacenter']} with {best_alt['gpu']} ({best_alt['vram']}GB) at ${best_alt['lowest']:.2f}/h")
    print("=" * 90 + "\n")

if __name__ == "__main__":
    asyncio.run(run_query())
