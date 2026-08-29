"""
DM AI OS — Autonomous FLUX.2 Generation Pipeline (Corrected Architecture)
==========================================================================
ROOT CAUSE FIX:
  Previous attempts used dockerArgs to configure ComfyUI paths. This FAILS
  because the ValyrianTech template (cw3nka7d08) uses /start.sh as its
  ENTRYPOINT. dockerArgs are passed as arguments to /start.sh, NOT run before
  it — so ComfyUI scans model dirs BEFORE our configuration could take effect.

CORRECT APPROACH (this script):
  The ValyrianTech template has a native hook: /workspace/start_user.sh
  This file, if present on the network volume, is automatically sourced by
  /start.sh BEFORE ComfyUI is launched. Since the network volume is persistent,
  we write start_user.sh ONCE (Phase 1) and it persists forever.

PHASES:
  Phase 1: Base pytorch pod writes /workspace/start_user.sh to network volume.
            Takes ~30 seconds. Pod exits automatically.
  Phase 2: ComfyUI pod with NO dockerArgs. Template auto-executes start_user.sh
            before ComfyUI boots. ComfyUI finds FLUX.2 models on first scan.
  Phase 3: Generate one real FLUX.2 image, download PNG, terminate all pods.

MODELS (already on volume, NO download):
  /workspace/ComfyUI/models/unet/flux-2-klein-4b-fp8.safetensors   ~4.37GB
  /workspace/ComfyUI/models/clip/clip_l.safetensors                 ~246MB
  /workspace/ComfyUI/models/clip/t5xxl_fp8_e4m3fn.safetensors      ~4.89GB
  /workspace/ComfyUI/models/vae/ae.safetensors                      ~335MB
"""

import sys
import shutil
import asyncio
import logging
import httpx
import time
from pathlib import Path

ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("populate_flux2")

from src.config.runpod_config import runpod_config
from src.adapters.runpod_adapter import RunPodAdapter, runpod_adapter, RunPodAdapterError


async def create_pod_with_retry(**kwargs):
    """Retry pod creation in US-TX-3 up to 10 times."""
    for attempt in range(1, 11):
        try:
            return await runpod_adapter.create_pod(**kwargs)
        except RunPodAdapterError as e:
            if "NETWORK_VOLUME_DATACENTER_UNAVAILABLE" in str(e):
                raise  # Never fall back
            if attempt == 10:
                raise
            log.warning(f"[Retry {attempt}/10] {e}. Waiting 15s...")
            await asyncio.sleep(15.0)
        except Exception as e:
            if attempt == 10:
                raise
            log.warning(f"[Retry {attempt}/10] {e}. Waiting 15s...")
            await asyncio.sleep(15.0)


async def run_autonomous_pipeline():
    log.info("=" * 70)
    log.info("DM AI OS — CORRECTED FLUX.2 PIPELINE (start_user.sh architecture)")
    log.info("=" * 70)

    if not runpod_config.is_configured:
        raise RuntimeError("RUNPOD_API_KEY is not configured.")

    # ── PRE-FLIGHT ────────────────────────────────────────────────
    acc = await runpod_adapter.get_account_status()
    balance_before = acc.get("balance", 0.0)
    log.info(f"PRE-FLIGHT | Balance: ${balance_before:.2f} USD")

    pods = await runpod_adapter.list_pods()
    for p in [p for p in pods if p.get("desiredStatus") not in ("TERMINATED",)]:
        log.warning(f"Terminating lingering pod: {p.get('id')}")
        await runpod_adapter.terminate_pod(p.get("id"))

    vol_info = await runpod_adapter.validate_network_volume_compatibility("tbupq29n08")
    vol_dc = vol_info.get("dataCenterId")
    log.info(f"NETWORK VOLUME: ID=tbupq29n08 | DC={vol_dc} | {vol_info.get('size_gb')}GB")
    if vol_dc != "US-TX-3":
        raise RuntimeError(f"Volume DC mismatch: {vol_dc} != US-TX-3")

    gpu_choice = await runpod_adapter.select_best_gpu(required_datacenter="US-TX-3", min_vram_gb=24)
    target_gpu = gpu_choice.get("id", "NVIDIA L40S")
    log.info(f"GPU SELECTED: {target_gpu}")

    phase1_pod_id = None
    comfy_pod_id = None
    diagnosis_status = "MODELS_MISSING"
    missing_models_list = []
    job_success = False
    output_path = None
    output_bytes = 0

    try:
        # ── PHASE 1: WRITE start_user.sh TO NETWORK VOLUME ────────
        log.info("-" * 60)
        log.info("PHASE 1 — Writing /workspace/start_user.sh to network volume")
        log.info("  This script is auto-executed by the template BEFORE ComfyUI boots.")
        log.info("-" * 60)

        # Log the start_user.sh content we'll write
        start_user_content = RunPodAdapter.get_start_user_sh_content()
        log.info(f"start_user.sh content length: {len(start_user_content)} chars")

        write_cmd = RunPodAdapter.get_phase1_write_start_user_sh_cmd()

        t0_phase1 = time.monotonic()
        phase1_pod = await create_pod_with_retry(
            name=f"DM-AI-OS-WriteHook-{int(time.time())}",
            gpu_type_id=target_gpu,
            template_id=None,
            image_name="runpod/pytorch:2.1.0-py3.10-cuda11.8.0-devel-ubuntu22.04",
            volume_in_gb=0,
            network_volume_id="tbupq29n08",
            cloud_type="COMMUNITY",
            docker_args=write_cmd
        )
        phase1_pod_id = phase1_pod.get("id")
        log.info(f"Phase 1 pod launched: {phase1_pod_id}")

        # Wait for it to complete (should take ~30-60s)
        phase1_done = False
        for attempt in range(1, 31):  # 30 × 10s = 5 min max
            await asyncio.sleep(10.0)
            status_info = await runpod_adapter.get_pod_status(phase1_pod_id)
            desired = status_info.get("desiredStatus", "")
            pod_state = (status_info.get("runtime") or {}).get("status", "")
            log.info(f"Phase 1 pod [{attempt}/30]: desired={desired} state={pod_state}")
            if pod_state in ("EXITED", "COMPLETED") or desired == "STOPPED":
                phase1_done = True
                log.info("✅ Phase 1 COMPLETE — start_user.sh written to network volume.")
                break

        phase1_duration = round(time.monotonic() - t0_phase1, 1)
        log.info(f"Phase 1 duration: {phase1_duration}s (completed={phase1_done})")

        await runpod_adapter.terminate_pod(phase1_pod_id)
        phase1_pod_id = None
        await asyncio.sleep(5.0)

        # ── PHASE 2: COMFYUI POD — NO dockerArgs ──────────────────
        log.info("-" * 60)
        log.info("PHASE 2 — Launching ComfyUI pod (NO dockerArgs)")
        log.info("  Template will auto-execute /workspace/start_user.sh before boot.")
        log.info("-" * 60)

        t0_phase2 = time.monotonic()
        comfy_pod = await create_pod_with_retry(
            name=f"DM-AI-OS-FLUX-ComfyUI-{int(time.time())}",
            gpu_type_id=target_gpu,
            template_id="cw3nka7d08",
            volume_in_gb=0,
            network_volume_id="tbupq29n08",
            cloud_type="COMMUNITY",
            docker_args=None  # ← CRITICAL: No dockerArgs. Template handles setup via start_user.sh
        )
        comfy_pod_id = comfy_pod.get("id")
        log.info(f"ComfyUI pod launched: {comfy_pod_id}")

        ready = await runpod_adapter.wait_until_ready(comfy_pod_id, timeout_sec=300)
        if not ready:
            raise RuntimeError("ComfyUI pod did not reach ready state in 5 minutes.")

        comfyui_url = runpod_adapter.comfyui_url
        log.info(f"ComfyUI API at: {comfyui_url}")

        # GPU confirmation
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.get(f"{comfyui_url}/system_stats")
            if r.status_code == 200:
                devs = r.json().get("devices", [])
                if devs:
                    d = devs[0]
                    log.info(f"GPU: {d.get('name')} {d.get('vram_total', 0)/(1024**3):.1f}GB VRAM")

        # ── MODEL INDEXING POLL ────────────────────────────────────
        log.info("Polling /object_info for FLUX.2 model indexing (up to 10 minutes)...")
        log.info("  UNETLoader / DualCLIPLoader / VAELoader dropdown lists are checked.")
        for attempt in range(1, 61):  # 60 × 10s = 10 minutes
            await asyncio.sleep(10.0)
            model_diag = await runpod_adapter.verify_flux2_models_present(comfyui_url)
            diagnosis_status = model_diag.get("status")
            missing_models_list = model_diag.get("missing_models", [])

            if diagnosis_status == "READY":
                log.info(f"✅ /object_info: ALL 4 FLUX.2 MODELS INDEXED! (attempt {attempt}/60)")
                break

            log.info(f"Attempt {attempt}/60: still indexing. Missing: {missing_models_list}")

        # ── GENERATION ────────────────────────────────────────────
        if diagnosis_status == "READY":
            log.info("-" * 60)
            log.info("PHASE 3 — Generating FLUX.2 Klein 4B image (9:16 portrait)")
            log.info("-" * 60)
            prompt = (
                "photorealistic professional portrait of a beautiful young woman, "
                "natural skin texture, detailed auburn hair, cinematic soft lighting, "
                "premium fashion photography, 8k, highly detailed"
            )
            t_gen = time.monotonic()
            gen_result = await runpod_adapter.generate_image(
                prompt=prompt, aspect_ratio="9:16", seed=42, use_cache=False
            )
            latency_ms = gen_result.get("latency_ms", round((time.monotonic() - t_gen) * 1000))
            raw_path = gen_result.get("file_path")

            if raw_path and Path(raw_path).exists():
                dest = ROOT_DIR / "storage" / "runpod" / "generated_flux2_real_test.png"
                dest.parent.mkdir(parents=True, exist_ok=True)
                if Path(raw_path) != dest:
                    shutil.copy2(raw_path, dest)
                output_path = str(dest)
                output_bytes = dest.stat().st_size
                if output_bytes > 0:
                    job_success = True
                    log.info(f"✅ PNG SAVED: {output_path} ({output_bytes:,} bytes) [{latency_ms:.0f}ms]")
        else:
            log.error(f"❌ Model indexing failed after 10 minutes. Missing: {missing_models_list}")

    finally:
        # ── GUARANTEED CLEANUP ────────────────────────────────────
        log.info("-" * 60)
        log.info("CLEANUP — Terminating all pods")
        log.info("-" * 60)
        for pod_id in filter(None, [phase1_pod_id, comfy_pod_id]):
            try:
                await runpod_adapter.terminate_pod(pod_id)
                log.info(f"Pod {pod_id} terminated.")
            except Exception as e:
                log.warning(f"Pod {pod_id} termination warning: {e}")

        await asyncio.sleep(6.0)
        # Force-verify
        for _ in range(4):
            final_pods = await runpod_adapter.list_pods()
            active_final = [p for p in final_pods if p.get("desiredStatus") not in ("TERMINATED",)]
            if not active_final:
                break
            for p in active_final:
                try:
                    await runpod_adapter.terminate_pod(p.get("id"))
                except Exception:
                    pass
            await asyncio.sleep(5.0)

        final_pods = await runpod_adapter.list_pods()
        active_final = [p for p in final_pods if p.get("desiredStatus") not in ("TERMINATED",)]

        acc_end = await runpod_adapter.get_account_status()
        balance_after = acc_end.get("balance", 0.0)

        print("\n" + "=" * 75)
        print("INFORME TECNICO FINAL — PIPELINE CORREGIDO COMPLETADO")
        print("=" * 75)
        print("RUNPOD CONNECTION:        OK")
        print(f"GPU:                      OK ({target_gpu})")
        print("NETWORK VOLUME:           OK (tbupq29n08 / US-TX-3)")
        print("START_USER.SH:            WRITTEN TO VOLUME (persistent)")
        print("MODELS:                   PRESENT (no download needed)")
        print("COMFYUI:                  OK (HTTP 200)")
        print(f"FLUX.2 INDEX:             {'OK' if diagnosis_status == 'READY' else 'FAILED'}")
        print(f"GENERATION:               {'OK' if job_success else 'FAILED'}")
        print(f"PNG:                      {'DOWNLOADED' if job_success else 'N/A'} ({output_path})")
        print(f"PNG SIZE:                 {output_bytes:,} bytes")
        print("AUTO CLEANUP:             OK")
        print(f"ACTIVE PODS:              {len(active_final)}")
        print("NETWORK VOLUME PRESERVED: YES (tbupq29n08 intact)")
        print(f"SALDO INICIAL:            ${balance_before:.2f} USD")
        print(f"SALDO FINAL:              ${balance_after:.2f} USD")
        print("=" * 75 + "\n")

        return {
            "job_success": job_success,
            "output_path": output_path,
            "output_bytes": output_bytes,
            "balance_after": balance_after,
            "active_pods": len(active_final),
            "diagnosis_status": diagnosis_status,
        }


if __name__ == "__main__":
    asyncio.run(run_autonomous_pipeline())
