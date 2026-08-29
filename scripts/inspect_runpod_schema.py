"""
RunPod GraphQL Schema Introspection Script — DM AI OS
=====================================================
Queries RunPod GraphQL API schema to find all valid Network Volume / Storage mutations.
Consumes $0.00 credits.
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
log = logging.getLogger("inspect_runpod_schema")

from src.adapters.runpod_adapter import runpod_adapter

async def inspect_schema():
    log.info("Inspecting RunPod GraphQL Schema for volume/storage mutations...")

    query = """
    query {
        __schema {
            mutationType {
                fields {
                    name
                    description
                    args {
                        name
                        type {
                            name
                            kind
                            ofType {
                                name
                                kind
                            }
                        }
                    }
                }
            }
        }
    }
    """

    try:
        data = await runpod_adapter._graphql_query(query)
        fields = data.get("__schema", {}).get("mutationType", {}).get("fields", [])
        
        vol_mutations = [f for f in fields if any(k in f["name"].lower() for k in ["volume", "storage", "network"])]
        log.info(f"Found {len(vol_mutations)} volume-related mutations in RunPod GraphQL API:")
        for m in vol_mutations:
            args_str = ", ".join([f"{a['name']}: {a['type'].get('name') or a['type'].get('ofType',{}).get('name')}" for a in m.get("args", [])])
            log.info(f"  Mutation: {m['name']}({args_str})")

        # Also inspect NetworkVolume type if present
        query_types = """
        query {
            __schema {
                types {
                    name
                    kind
                    fields {
                        name
                        type {
                            name
                        }
                    }
                }
            }
        }
        """
        types_data = await runpod_adapter._graphql_query(query_types)
        types_list = types_data.get("__schema", {}).get("types", [])
        vol_types = [t for t in types_list if any(k in t["name"].lower() for k in ["volume", "storage", "network"])]
        log.info(f"Found {len(vol_types)} volume-related types in Schema:")
        for t in vol_types[:15]:
            log.info(f"  Type: {t['name']} ({t['kind']})")

    except Exception as e:
        log.error(f"Schema introspection failed: {e}")

if __name__ == "__main__":
    asyncio.run(inspect_schema())
