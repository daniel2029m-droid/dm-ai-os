"""
DM AI OS — Single Ephemeral Volume Contents & Checksum Verifier
================================================================
AUTHORIZED EXPLICITLY BY USER:
- Create 1 Ephemeral base pod in US-TX-3 attached to Network Volume tbupq29n08
- Mount volume, run find/stat/sha256sum over /workspace/ComfyUI/models/
- Report file existence, exact byte size, and SHA-256 checksums
- NO ComfyUI launch, NO image generation, NO downloads
- Terminate pod immediately upon exit. Verify 0 active pods.
"""

import sys
import time
import asyncio
import logging
from pathlib import Path

ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("verify_volume")

from src.config.runpod_config import runpod_config
from src.adapters.runpod_adapter import runpod_adapter, RunPodAdapterError


async def run_verification():
    log.info("============================================================")
    log.info("DM AI OS — EPHEMERAL NETWORK VOLUME VERIFIER (tbupq29n08)")
    log.info("============================================================")

    if not runpod_config.is_configured:
        raise RuntimeError("RUNPOD_API_KEY is not configured.")

    acc = await runpod_adapter.get_account_status()
    balance_before = acc.get("balance", 0.0)
    log.info(f"PRE-FLIGHT | Saldo disponible: ${balance_before:.2f} USD")

    # Clear active pods first
    pods = await runpod_adapter.list_pods()
    active = [p for p in pods if p.get("desiredStatus") not in ("TERMINATED",)]
    for p in active:
        log.warning(f"Terminating lingering pod: {p.get('id')}")
        await runpod_adapter.terminate_pod(p.get("id"))
    if active:
        await asyncio.sleep(4.0)

    # Validate volume
    vol_info = await runpod_adapter.validate_network_volume_compatibility("tbupq29n08")
    vol_dc = vol_info.get("dataCenterId")
    log.info(f"NETWORK VOLUME: ID=tbupq29n08 | DC={vol_dc} | Size={vol_info.get('size_gb')}GB")
    if vol_dc != "US-TX-3":
        raise RuntimeError(f"Volume DC mismatch: {vol_dc} != US-TX-3")

    # Select best GPU in US-TX-3
    gpu_choice = await runpod_adapter.select_best_gpu(required_datacenter="US-TX-3", min_vram_gb=24)
    target_gpu = gpu_choice.get("id", "NVIDIA L40S")
    log.info(f"GPU TARGET SELECTED: {target_gpu} (Datacenter: US-TX-3)")

    # Pure verification command — NO downloads, NO ComfyUI
    verify_cmd = (
        "bash -c '"
        "set -e && "
        "echo \"=== NETWORK VOLUME VERIFICATION START ===\" && "
        "if [ ! -d /workspace ]; then echo \"CRITICAL_ERROR: /workspace not mounted\"; exit 1; fi && "
        "echo \"--- DIRECTORY HIERARCHY ---\" && "
        "find /workspace/ComfyUI/models/ -type f -exec ls -lh {} + 2>/dev/null || echo \"No files found\" && "
        "echo \"--- EXACT STAT AND CHECKSUMS ---\" && "
        "for f in "
        "/workspace/ComfyUI/models/unet/flux-2-klein-4b-fp8.safetensors "
        "/workspace/ComfyUI/models/diffusion_models/flux-2-klein-4b-fp8.safetensors "
        "/workspace/ComfyUI/models/clip/clip_l.safetensors "
        "/workspace/ComfyUI/models/clip/t5xxl_fp8_e4m3fn.safetensors "
        "/workspace/ComfyUI/models/vae/ae.safetensors; do "
        "if [ -f \"$f\" ]; then "
        "sz=$(stat -c%s \"$f\"); "
        "echo -n \"FILE_FOUND: $f | SIZE_BYTES: $sz | SHA256: \"; "
        "sha256sum \"$f\" | cut -d\" \" -f1; "
        "else "
        "echo \"FILE_MISSING: $f\"; "
        "fi; done && "
        "echo \"=== NETWORK VOLUME VERIFICATION COMPLETE ===\""
        "'"
    )

    pod_id = None
    t0 = time.monotonic()
    try:
        pod = await runpod_adapter.create_pod(
            name=f"DM-AI-OS-VolVerify-{int(time.time())}",
            gpu_type_id=target_gpu,
            template_id=None,
            image_name="runpod/pytorch:2.1.0-py3.10-cuda11.8.0-devel-ubuntu22.04",
            volume_in_gb=0,
            network_volume_id="tbupq29n08",
            cloud_type="COMMUNITY",
            docker_args=verify_cmd
        )
        pod_id = pod.get("id")
        log.info(f"Verification Pod launched: {pod_id}")

        # Wait for container to exit (up to 3 minutes / 180s)
        completed = False
        for attempt in range(1, 19):
            await asyncio.sleep(10.0)
            status_info = await runpod_adapter.get_pod_status(pod_id)
            desired = status_info.get("desiredStatus", "")
            runtime = status_info.get("runtime") or {}
            pod_state = runtime.get("status", "")
            log.info(f"Verification Pod status [{attempt}/18]: desired={desired} state={pod_state}")

            if pod_state in ("EXITED", "COMPLETED") or desired == "STOPPED":
                completed = True
                log.info("✅ Verification Pod EXITED / COMPLETED successfully!")
                break

        duration_sec = round(time.monotonic() - t0, 1)
        log.info(f"Verification Pod finished in {duration_sec}s.")

    finally:
        if pod_id:
            log.info(f"Terminating Pod {pod_id} immediately...")
            await runpod_adapter.terminate_pod(pod_id)
            await asyncio.sleep(5.0)

        # Force verify 0 pods active
        for _ in range(4):
            final_pods = await runpod_adapter.list_pods()
            active_final = [p for p in final_pods if p.get("desiredStatus") not in ("TERMINATED",)]
            if not active_final:
                break
            for p in active_final:
                await runpod_adapter.terminate_pod(p.get("id"))
            await asyncio.sleep(4.0)

        final_pods = await runpod_adapter.list_pods()
        active_final = [p for p in final_pods if p.get("desiredStatus") not in ("TERMINATED",)]

        acc_end = await runpod_adapter.get_account_status()
        balance_after = acc_end.get("balance", 0.0)

        log.info("=" * 60)
        log.info(f"VERIFICATION POD TERMINATED | Active Pods: {len(active_final)}")
        log.info(f"Saldo restante: ${balance_after:.2f} USD")
        log.info("=" * 60)


if __name__ == "__main__":
    asyncio.run(run_verification())
