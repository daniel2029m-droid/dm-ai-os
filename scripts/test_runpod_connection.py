"""
Real Authentication & Connection Test for RunPod — DM AI OS
============================================================
Performs a REAL authentication check against RunPod GraphQL API.
- NO pods created
- NO GPUs started
- NO endpoints deployed
- NO budget consumed
- NO secrets exposed in output
"""

import sys
import os
import asyncio
import logging
from pathlib import Path

# Ensure root scratch directory is in python path
ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))

# Setup logging without showing sensitive headers
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("test_runpod_connection")

from src.config.runpod_config import runpod_config
from src.adapters.runpod_adapter import runpod_adapter, RunPodAdapterError


async def test_real_connection():
    log.info("RUNPOD CONNECTION TEST")
    log.info("------------------------------------------------------------")

    # 1. Check API Key configuration
    api_key = runpod_config.api_key
    if not api_key:
        log.error("API KEY: NOT CONFIGURED")
        return {
            "api_key_configured": False,
            "auth": False,
            "account_access": False,
            "pods_found": 0,
            "endpoints_found": 0
        }

    log.info("API KEY: CONFIGURED")

    # 2. Perform Real GraphQL Query against RunPod API
    query = """
    query {
        myself {
            id
            email
            clientBalance
            pods {
                id
                name
                desiredStatus
            }
            endpoints {
                id
                name
            }
        }
    }
    """

    auth_success = False
    account_success = False
    pods_count = 0
    endpoints_count = 0

    try:
        data = await runpod_adapter._graphql_query(query)
        myself = data.get("myself", {})
        if myself and "id" in myself:
            auth_success = True
            account_success = True
            pods = myself.get("pods") or []
            endpoints = myself.get("endpoints") or []
            pods_count = len(pods)
            endpoints_count = len(endpoints)
            log.info("AUTHENTICATION: SUCCESS")
            log.info("ACCOUNT ACCESS: SUCCESS")
            log.info(f"PODS: {pods_count} found")
            log.info(f"ENDPOINTS: {endpoints_count} found")
        else:
            auth_success = True
            log.info("AUTHENTICATION: SUCCESS")
            log.info("ACCOUNT ACCESS: FAILED")
    except RunPodAdapterError as e:
        log.error(f"AUTHENTICATION / ACCESS FAILED: {e}")
        # Try fallback simple query if endpoints schema field differed
        fallback_query = """
        query {
            myself {
                id
                email
                clientBalance
                pods {
                    id
                    name
                }
            }
        }
        """
        try:
            data = await runpod_adapter._graphql_query(fallback_query)
            myself = data.get("myself", {})
            if myself and "id" in myself:
                auth_success = True
                account_success = True
                pods = myself.get("pods") or []
                pods_count = len(pods)
                endpoints_count = 0
                log.info("AUTHENTICATION: SUCCESS (Fallback query)")
                log.info("ACCOUNT ACCESS: SUCCESS")
                log.info(f"PODS: {pods_count} found")
                log.info(f"ENDPOINTS: {endpoints_count} found")
        except Exception as err:
            log.error(f"Fallback connection query failed: {err}")

    log.info("------------------------------------------------------------")
    return {
        "api_key_configured": bool(api_key),
        "auth": auth_success,
        "account_access": account_success,
        "pods_found": pods_count,
        "endpoints_found": endpoints_count
    }


if __name__ == "__main__":
    res = asyncio.run(test_real_connection())
    if not res["auth"]:
        sys.exit(1)
