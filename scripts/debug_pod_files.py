import asyncio
import json
import logging
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))

from src.adapters.runpod_adapter import runpod_adapter

async def debug_pod():
    query = """
    query Pod($podId: String!) {
        pod(input: {podId: $podId}) {
            id
            desiredStatus
            runtime {
                ports {
                    ip
                    isIpPublic
                    privatePort
                    publicPort
                    type
                }
            }
        }
    }
    """
    res = await runpod_adapter._graphql_query(query, {"podId": "c92pio2y6606bm"})
    print(json.dumps(res, indent=2))

if __name__ == "__main__":
    asyncio.run(debug_pod())
