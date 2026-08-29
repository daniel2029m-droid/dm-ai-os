"""
Test Candidate Network Volume Mutations — DM AI OS
===================================================
Tests candidate GraphQL mutation signatures for network volume creation.
Consumes $0.00 credits on syntax validation checks.
"""

import sys
import asyncio
import logging
from pathlib import Path

ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("test_volume_mutations")

from src.adapters.runpod_adapter import runpod_adapter

async def test_mutations():
    candidates = [
        # Candidate 1: CreateNetworkVolumeInput
        (
            """
            mutation CreateNetworkVolume($input: CreateNetworkVolumeInput!) {
                createNetworkVolume(input: $input) {
                    id
                    name
                    size
                }
            }
            """,
            {"input": {"name": "DM-AI-OS-Models", "size": 40, "dataCenterId": "US-TX-3"}}
        ),
        # Candidate 2: Direct arguments
        (
            """
            mutation {
                createNetworkVolume(name: "DM-AI-OS-Models", size: 40, dataCenterId: "US-TX-3") {
                    id
                    name
                    size
                }
            }
            """,
            None
        ),
        # Candidate 3: generateNetworkVolume
        (
            """
            mutation GenerateNetworkVolume($input: GenerateNetworkVolumeInput!) {
                generateNetworkVolume(input: $input) {
                    id
                    name
                    size
                }
            }
            """,
            {"input": {"name": "DM-AI-OS-Models", "size": 40, "dataCenterId": "US-TX-3"}}
        ),
        # Candidate 4: saveNetworkVolume with SaveNetworkVolumeInput -> was invalid, try NetworkVolumeInput
        (
            """
            mutation SaveNetworkVolume($input: NetworkVolumeInput!) {
                saveNetworkVolume(input: $input) {
                    id
                    name
                    size
                }
            }
            """,
            {"input": {"name": "DM-AI-OS-Models", "size": 40, "dataCenterId": "US-TX-3"}}
        ),
    ]

    for idx, (mut, payload) in enumerate(candidates, 1):
        log.info(f"Testing Candidate {idx}...")
        try:
            res = await runpod_adapter._graphql_query(mut, payload)
            log.info(f"🎉 SUCCESS Candidate {idx}: {res}")
            break
        except Exception as e:
            log.warning(f"Candidate {idx} result: {e}")

if __name__ == "__main__":
    asyncio.run(test_mutations())
