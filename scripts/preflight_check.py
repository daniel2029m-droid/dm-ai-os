"""
Pre-flight Status Check for RunPod Controlled Real Test
======================================================
Queries RunPod GraphQL API for:
1. Authentication status & client balance
2. Active pods count
3. Network volumes list
Consumes $0.00 credits. NO pods created.
"""

import sys
import os
import asyncio
import logging
from pathlib import Path

ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("preflight_check")

from src.adapters.runpod_adapter import runpod_adapter

async def preflight():
    log.info("=== RUNPOD PRE-FLIGHT CHECK ===")
    
    # 1. Account Status
    account = await runpod_adapter.get_account_status()
    log.info(f"Account Email: {account.get('email')}")
    log.info(f"Client Balance: ${account.get('balance', 0.0):.2f} USD")
    
    # 2. Active Pods
    pods = await runpod_adapter.list_pods()
    active_pods = [p for p in pods if p.get("desiredStatus") != "TERMINATED"]
    log.info(f"Total Pods: {len(pods)} | Active Pods: {len(active_pods)}")
    for p in active_pods:
        log.info(f"  -> Active Pod: ID={p.get('id')} Name={p.get('name')} Status={p.get('desiredStatus')} Cost=${p.get('costPerHr')}/h")
        
    # 3. Network Volumes
    net_vols = await runpod_adapter.list_network_volumes()
    log.info(f"Network Volumes Found: {len(net_vols)}")
    for nv in net_vols:
        log.info(f"  -> Volume: ID={nv.get('id')} Name={nv.get('name')} Size={nv.get('size')}GB Datacenter={nv.get('dataCenterId')}")
        
    log.info("===============================")
    return {
        "balance": account.get("balance", 0.0),
        "active_pods_count": len(active_pods),
        "network_volumes": net_vols
    }

if __name__ == "__main__":
    asyncio.run(preflight())
