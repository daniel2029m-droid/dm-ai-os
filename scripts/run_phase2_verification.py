"""
DM AI OS — Standalone Phase 2 ComfyUI Model Verification
=========================================================
1. Terminates any active download pod.
2. Spawns a fresh ComfyUI pod (cw3nka7d08) in US-TX-3 with Network Volume tbupq29n08.
3. Queries /object_info endpoint to verify detection of all 4 FLUX.2 model files.
4. Immediately terminates the verification pod and confirms 0 active pods.
"""

import sys
import time
import asyncio
import logging
import httpx
from pathlib import Path

ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("phase2_verify")

from src.config.runpod_config import runpod_config
from src.adapters.runpod_adapter import runpod_adapter


async def main():
    log.info("============================================================")
    log.info("DM AI OS — PHASE 2 MODEL VERIFICATION (COMFYUI /object_info)")
    log.info("============================================================")

    # 1. Terminate download pod if active
    pods = await runpod_adapter.list_pods()
    active = [p for p in pods if p.get("desiredStatus") not in ("TERMINATED",)]
    if active:
        for p in active:
            log.info(f"Terminating prior active pod {p.get('id')}...")
            try:
                await runpod_adapter.terminate_pod(p.get("id"))
            except Exception as te:
                log.warning(f"Error terminating pod: {te}")
        await asyncio.sleep(6.0)

    # 2. Spin up ComfyUI verification pod
    log.info("Creating ComfyUI verify pod in US-TX-3 with Network Volume tbupq29n08...")
    vpod = await runpod_adapter.create_pod(
        name=f"DM-OS-VERIFY-{int(time.time())}",
        gpu_type_id="NVIDIA L40S",
        template_id="cw3nka7d08",
        volume_in_gb=20,
        network_volume_id="tbupq29n08",
        cloud_type="COMMUNITY",
    )
    vpid = vpod.get("id")
    if not vpid:
        raise RuntimeError("Failed to create verification pod.")
    log.info(f"Verify pod created successfully: {vpid}")

    # 3. Wait until ready
    ready = await runpod_adapter.wait_until_ready(vpid, timeout_sec=300)
    if not ready:
        await runpod_adapter.terminate_pod(vpid)
        raise RuntimeError("Verify pod failed to boot ComfyUI within timeout.")

    comfyui_url = runpod_adapter.comfyui_url
    log.info(f"ComfyUI HTTP API is READY at {comfyui_url}")

    # Check GPU info via system_stats
    try:
        async with httpx.AsyncClient(timeout=15.0) as c:
            r = await c.get(f"{comfyui_url}/system_stats")
            if r.status_code == 200:
                devices = r.json().get("devices", [])
                if devices:
                    gpu_name = devices[0].get("name", "Unknown")
                    vram = devices[0].get("vram_total", 0) / (1024**3)
                    log.info(f"GPU Confirmed: {gpu_name} ({vram:.1f} GB VRAM)")
    except Exception as e:
        log.warning(f"System stats query warning: {e}")

    # 4. Verify /object_info
    log.info("Checking /object_info for FLUX.2 model loaders...")
    async with httpx.AsyncClient(timeout=30.0) as c:
        r = await c.get(f"{comfyui_url}/object_info")
        info = r.json()

    unet_models = (info.get("UNETLoader", {}).get("input", {}).get("required", {}).get("unet_name", [[]])[0]) or []
    clip_models = (info.get("DualCLIPLoader", {}).get("input", {}).get("required", {}).get("clip_name1", [[]])[0]) or []
    vae_models = (info.get("VAELoader", {}).get("input", {}).get("required", {}).get("vae_name", [[]])[0]) or []

    log.info(f"UNETLoader models:   {unet_models}")
    log.info(f"DualCLIPLoader clip1: {clip_models}")
    log.info(f"VAELoader models:    {vae_models}")

    missing = []
    if "flux-2-klein-4b-fp8.safetensors" not in unet_models:
        missing.append("flux-2-klein-4b-fp8.safetensors")
    if "clip_l.safetensors" not in clip_models:
        missing.append("clip_l.safetensors")
    if "t5xxl_fp8_e4m3fn.safetensors" not in clip_models:
        missing.append("t5xxl_fp8_e4m3fn.safetensors")
    if "ae.safetensors" not in vae_models:
        missing.append("ae.safetensors")

    # 5. Clean up pod immediately
    log.info(f"Terminating verify pod {vpid} immediately...")
    try:
        await runpod_adapter.terminate_pod(vpid)
    except Exception as te:
        log.warning(f"Error terminating verify pod: {te}")
    await asyncio.sleep(6.0)

    # 6. Verify 0 active pods
    v_pods = await runpod_adapter.list_pods()
    final_active = [p for p in v_pods if p.get("desiredStatus") not in ("TERMINATED",)]

    acc = await runpod_adapter.get_account_status()

    unet_status = "DETECTADO" if "flux-2-klein-4b-fp8.safetensors" not in missing else "FALTA"
    clip_l_status = "DETECTADO" if "clip_l.safetensors" not in missing else "FALTA"
    t5xxl_status = "DETECTADO" if "t5xxl_fp8_e4m3fn.safetensors" not in missing else "FALTA"
    vae_status = "DETECTADO" if "ae.safetensors" not in missing else "FALTA"
    all_ready = len(missing) == 0

    print("\n" + "=" * 70)
    print("RESULTADO DE VERIFICACION EN FASE 2 (COMFYUI /object_info)")
    print("=" * 70)
    print(f"NETWORK VOLUME:  tbupq29n08 (US-TX-3)")
    print(f"UNET MODEL:      {unet_status}")
    print(f"CLIP_L MODEL:    {clip_l_status}")
    print(f"T5XXL MODEL:     {t5xxl_status}")
    print(f"VAE MODEL:       {vae_status}")
    print(f"STORAGE STATUS:  {'ALL_MODELS_READY' if all_ready else 'MISSING_MODELS'}")
    print(f"ACTIVE PODS:     {len(final_active)}")
    print(f"BALANCE:         ${acc.get('balance', 0.0):.2f} USD")
    if missing:
        print(f"MISSING LIST:    {missing}")
    print("=" * 70 + "\n")

    return {
        "status": "ALL_MODELS_READY" if all_ready else "MISSING_MODELS",
        "missing": missing,
        "active_pods": len(final_active),
    }


if __name__ == "__main__":
    asyncio.run(main())
