"""
Single Real Execution Test for NVIDIA NIM — FLUX.2 Klein 4B
============================================================
IMPORTANT: Makes ONLY ONE real request to NVIDIA NIM.
Do NOT run multiple times to preserve quota.
"""

import sys
import os
import asyncio
import logging
from pathlib import Path

# Ensure root scratch directory is in python path
ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
log = logging.getLogger("single_real_test")

from src.adapters.nvidia_adapter import nvidia_adapter, NVIDIAAdapterError
from src.providers.provider_history import provider_history


async def run_single_real_call():
    log.info("Starting SINGLE real NVIDIA NIM API call for FLUX.2 Klein 4B...")
    
    # Prompt for real test call
    prompt = "A high resolution photorealistic portrait of an elegant woman on a terrace in Buenos Aires at golden hour."
    aspect_ratio = "1:1"

    base_url = "https://ai.api.nvidia.com/v1/genai/black-forest-labs/flux.2-klein-4b"
    nvidia_adapter._override_base_url = base_url

    try:
        result = await nvidia_adapter.generate_image(
            prompt=prompt,
            aspect_ratio=aspect_ratio,
            use_cache=False  # Bypass cache for live validation
        )
    except NVIDIAAdapterError as e:
        log.error(f"Endpoint {base_url} returned error: {e}")
        return False, str(e)


    log.info("============================================================")
    log.info("REAL NVIDIA NIM CALL RESULTS:")
    log.info(f"Status: {result.get('status')}")
    log.info(f"Provider: {result.get('provider')}")
    log.info(f"Model: {result.get('model')}")
    log.info(f"Image Saved At: {result.get('file_path')}")
    log.info(f"Image URL: {result.get('image_url')}")
    log.info(f"Latency: {result.get('latency_ms')} ms")
    log.info(f"HTTP Status: {result.get('http_status')}")
    log.info("============================================================")

    # Output details to json file for record
    out_log = ROOT_DIR / "logs" / "single_nvidia_real_test_result.json"
    out_log.parent.mkdir(parents=True, exist_ok=True)
    import json
    out_log.write_text(json.dumps(result, indent=2), encoding="utf-8")
    
    return True, result


if __name__ == "__main__":
    success, res = asyncio.run(run_single_real_call())
    if not success:
        sys.exit(1)
