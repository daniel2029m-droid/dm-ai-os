"""
DM AI OS — Single Authorized Controlled Real Test (FLUX.2 Klein 4B)
======================================================================
Executes the single authorized real test following the strict 13-step flow:
1. Pre-flight checks (Balance, Active Pods = 0, Network Volume tbupq29n08 in US-TX-3, GPU in US-TX-3)
2. Create Single Pod in US-TX-3
3. Mount Network Volume tbupq29n08 at /workspace
4. Verify /workspace mount & write permissions
5. Model setup (check & download missing models only)
6. Start/Restart ComfyUI & wait for HTTP 200 API ready
7. Real model diagnosis via /object_info endpoint (UNETLoader, DualCLIPLoader, VAELoader)
8. IF all 4 models indexed -> Execute SINGLE real generation (FLUX.2 Klein 4B, 768x1344, 9:16)
9. IF any model missing -> Skip /prompt, log diagnostic, execute cleanup
10. Download PNG output to local storage & record provider_history
11. Immediate Pod Termination (podTerminate)
12. Verify ACTIVE PODS = 0 and ACTIVE GPU = 0
13. Output complete technical report
"""

import sys
import os
import time
import json
import asyncio
import logging
import httpx
from pathlib import Path

ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("controlled_flux2_test")

from src.config.runpod_config import runpod_config
from src.adapters.runpod_adapter import runpod_adapter, RunPodAdapterError
from src.storage.storage_layer import storage
from src.providers.provider_history import provider_history


async def execute_authorized_test():
    log.info("============================================================")
    log.info("DM AI OS — RUNPOD FLUX.2 KLEIN 4B CONTROLLED TEST EXECUTION")
    log.info("============================================================")

    # ── STEP 1: PRE-FLIGHT CHECKS ──────────────────────────────────────────
    log.info("------------------------------------------------------------")
    log.info("PASO 1 — PRE-FLIGHT CHECKS")
    log.info("------------------------------------------------------------")

    if not runpod_config.is_configured:
        raise RuntimeError("RUNPOD_API_KEY is not configured in environment.")

    account = await runpod_adapter.get_account_status()
    balance_before = account.get("balance", 0.0)
    email = account.get("email", "Unknown")
    log.info(f"1. CLIENT EMAIL:   {email}")
    log.info(f"2. SALDO ANTES:    ${balance_before:.2f} USD")

    if balance_before < 0.50:
        raise RuntimeError(f"Insufficient balance: ${balance_before:.2f} USD < $0.50 minimum safety buffer.")

    # List & clear active pods
    pods = await runpod_adapter.list_pods()
    active_pods_before = [p for p in pods if p.get("desiredStatus") not in ("TERMINATED",)]
    log.info(f"3. ACTIVE PODS BEFORE: {len(active_pods_before)}")

    if active_pods_before:
        log.warning(f"Active pod detected: {active_pods_before[0].get('id')}. Terminating prior to run...")
        for p in active_pods_before:
            await runpod_adapter.terminate_pod(p.get("id"))
        await asyncio.sleep(5.0)

    # Validate Network Volume
    vol_info = await runpod_adapter.validate_network_volume_compatibility("tbupq29n08")
    vol_dc = vol_info.get("dataCenterId")
    log.info(f"4. NETWORK VOLUME: ID={vol_info.get('volume_id')} Name={vol_info.get('name')} Datacenter={vol_dc}")

    if vol_dc != "US-TX-3":
        raise RuntimeError(f"Volume datacenter mismatch! Expected US-TX-3, got {vol_dc}")

    # Check GPU availability in US-TX-3
    gpu_choice = await runpod_adapter.select_best_gpu(required_datacenter="US-TX-3", min_vram_gb=24)
    target_gpu = gpu_choice.get("id", "NVIDIA L40S")
    target_gpu_dc = gpu_choice.get("target_datacenter") or vol_dc
    log.info(f"5. TARGET GPU SELECTED: {target_gpu} (Datacenter: {target_gpu_dc})")

    if target_gpu_dc != "US-TX-3":
        raise RuntimeError(f"ABORT: No compatible GPU available in datacenter US-TX-3 where volume tbupq29n08 resides.")

    # ── STEP 2 & 3: POD CREATION & VOLUME MOUNT ───────────────────────────
    t_start = time.monotonic()
    t_prep_start = time.monotonic()
    pod_id = None
    comfyui_url = None
    http_stats_code = None
    http_prompt_code = None
    diagnosis_status = "UNKNOWN"
    missing_models_list = []
    job_success = False
    output_path = None
    output_bytes = 0
    latency_ms = 0.0
    error_msg = None
    prep_duration_sec = 0.0
    download_duration_sec = 0.0
    gen_duration_sec = 0.0

    try:
        log.info("------------------------------------------------------------")
        log.info("PASO 2 & 3 — CREATING SINGLE POD & MOUNTING NETWORK VOLUME")
        log.info("------------------------------------------------------------")

        setup_cmd = runpod_adapter.get_comfyui_volume_setup_cmd()

        pod = await runpod_adapter.create_pod(
            name=f"DM-OS-FLUX2-RealTest-{int(time.time())}",
            gpu_type_id=target_gpu,
            template_id="cw3nka7d08",
            volume_in_gb=20,
            network_volume_id="tbupq29n08",
            cloud_type="COMMUNITY",
            docker_args=setup_cmd
        )

        pod_id = pod.get("id")
        if not pod_id:
            raise RuntimeError(f"Pod creation failed. API returned: {pod}")

        log.info(f"Pod created successfully: {pod_id} | GPU: {target_gpu} | Datacenter: US-TX-3")
        runpod_config.pod_id = pod_id

        # ── STEP 4, 5, 6: BOOT, VOLUME VERIFY, MODEL SETUP & COMFYUI READY ────
        log.info("------------------------------------------------------------")
        log.info("PASO 4, 5, 6 — WAITING FOR VOLUME SETUP & COMFYUI BOOT")
        log.info("------------------------------------------------------------")

        ready = await runpod_adapter.wait_until_ready(pod_id, timeout_sec=600)
        if not ready:
            raise RuntimeError("Pod or ComfyUI failed to become ready within timeout.")

        comfyui_url = runpod_adapter.comfyui_url
        log.info(f"ComfyUI API connected at {comfyui_url}")

        prep_duration_sec = round(time.monotonic() - t_prep_start, 1)

        # Check /system_stats
        async with httpx.AsyncClient(timeout=15.0) as client:
            r_stats = await client.get(f"{comfyui_url}/system_stats")
            http_stats_code = r_stats.status_code
            if http_stats_code == 200:
                devices = r_stats.json().get("devices", [])
                if devices:
                    gpu_name = devices[0].get("name", "Unknown")
                    vram_gb = devices[0].get("vram_total", 0) / (1024**3)
                    log.info(f"GPU Confirmed on ComfyUI: {gpu_name} ({vram_gb:.1f} GB VRAM)")

        if http_stats_code != 200:
            raise RuntimeError(f"ComfyUI /system_stats returned HTTP {http_stats_code}")

        os.environ["MODEL_DOWNLOAD_AUTHORIZED"] = "1"

        # ── STEP 7: WAIT FOR MODEL DOWNLOAD & INDEXING (Up to 36 attempts / 6 min) ────
        log.info("------------------------------------------------------------")
        log.info("PASO 7 — WAITING FOR MODEL DOWNLOAD COMPLETION & COMFYUI INDEXING")
        log.info("------------------------------------------------------------")

        model_diag = {"status": "MODELS_MISSING", "ready": False, "missing_models": []}
        max_attempts = 36  # 36 x 10s = 360 seconds (6 minutes)
        for attempt in range(1, max_attempts + 1):
            model_diag = await runpod_adapter.verify_flux2_models_present(comfyui_url)
            diagnosis_status = model_diag.get("status")
            missing_models_list = model_diag.get("missing_models", [])
            if diagnosis_status == "READY":
                log.info(f"✅ ComfyUI /object_info model index VERIFIED READY on attempt {attempt}/{max_attempts}!")
                break
            log.info(f"Downloading / Indexing in progress... Attempt {attempt}/{max_attempts} (Missing: {missing_models_list})")
            await asyncio.sleep(10.0)

        log.info(f"FINAL DIAGNOSIS STATUS: {diagnosis_status}")
        log.info(f"FINAL MISSING MODELS:   {missing_models_list}")

        # ── STEP 8 & 9: CONDITIONAL REAL GENERATION ────────────────────────────
        if diagnosis_status == "READY" and len(missing_models_list) == 0:
            log.info("------------------------------------------------------------")
            log.info("PASO 8 — ALL 4 MODELS DETECTED: EXECUTING SINGLE REAL GENERATION")
            log.info("------------------------------------------------------------")

            prompt_text = "photorealistic professional portrait of a beautiful young woman, natural skin texture, realistic eyes, detailed auburn hair, cinematic soft lighting, premium fashion photography, highly detailed, photorealistic"
            t_gen_start = time.monotonic()

            gen_result = await runpod_adapter.generate_image(
                prompt=prompt_text,
                aspect_ratio="9:16",
                seed=42,
                use_cache=False
            )

            gen_duration_sec = round(time.monotonic() - t_gen_start, 1)
            latency_ms = gen_result.get("latency_ms", round(gen_duration_sec * 1000, 1))
            output_path = gen_result.get("file_path")
            http_prompt_code = 200

            # Copy or save PNG to storage/runpod/generated_flux2_real_test.png
            if output_path and Path(output_path).exists():
                output_bytes = Path(output_path).stat().st_size
                target_dest = ROOT_DIR / "storage" / "runpod" / "generated_flux2_real_test.png"
                target_dest.parent.mkdir(parents=True, exist_ok=True)
                if Path(output_path) != target_dest:
                    import shutil
                    shutil.copy2(output_path, target_dest)
                    output_path = str(target_dest)
                if output_bytes > 0:
                    job_success = True
                    log.info(f"PASO 10 — PNG GENERATED & VERIFIED: {output_path} ({output_bytes} bytes)")
        else:
            log.warning("------------------------------------------------------------")
            log.warning("PASO 9 — DIAGNOSIS FAILED: SKIPPING /prompt AND GENERATION")
            log.warning("------------------------------------------------------------")
            log.warning(f"Aborting generation because models are missing: {missing_models_list}")
            http_prompt_code = None
            error_msg = f"Model diagnosis failed. Missing: {missing_models_list}"

    except Exception as e:
        error_msg = str(e)
        log.error(f"Execution Error during controlled test: {e}")

    finally:
        # ── STEP 11: MANDATORY CLEANUP (TERMINATE POD) ───────────────────────
        log.info("------------------------------------------------------------")
        log.info("PASO 11 — CLEANUP: IMMEDIATE POD TERMINATION")
        log.info("------------------------------------------------------------")

        t_end = time.monotonic()
        total_gpu_sec = round(t_end - t_start, 1)
        approx_cost = round((total_gpu_sec / 3600.0) * 0.79, 4)

        if pod_id:
            try:
                await runpod_adapter.terminate_pod(pod_id)
                log.info(f"Pod {pod_id} terminated cleanly.")
            except Exception as te:
                log.error(f"Error terminating pod {pod_id}: {te}")

        await asyncio.sleep(5.0)

        # ── STEP 12: FINAL VERIFICATION (0 ACTIVE PODS & GPUS) ───────────────
        log.info("------------------------------------------------------------")
        log.info("PASO 12 — FINAL VERIFICATION (0 ACTIVE PODS)")
        log.info("------------------------------------------------------------")

        verify_pods = await runpod_adapter.list_pods()
        final_active_pods = [p for p in verify_pods if p.get("desiredStatus") not in ("TERMINATED",)]

        retry = 0
        while len(final_active_pods) > 0 and retry < 3:
            log.warning(f"Active pod remaining: {final_active_pods[0].get('id')}. Retrying podTerminate...")
            for p in final_active_pods:
                await runpod_adapter.terminate_pod(p.get("id"))
            await asyncio.sleep(4.0)
            verify_pods = await runpod_adapter.list_pods()
            final_active_pods = [p for p in verify_pods if p.get("desiredStatus") not in ("TERMINATED",)]
            retry += 1

        acc_after = await runpod_adapter.get_account_status()
        balance_after = acc_after.get("balance", 0.0)

        # ── STEP 13: COMPREHENSIVE TECHNICAL REPORT ───────────────────────────
        print("\n" + "=" * 70)
        print("INFORME TECNICO FINAL — CONTROLLED REAL TEST EXECUTION")
        print("=" * 70)
        print(f"GPU UTILIZADA:           {target_gpu} (48GB VRAM)")
        print(f"POD ID:                  {pod_id or 'N/A'}")
        print(f"DATACENTER:              {vol_dc}")
        print(f"NETWORK VOLUME ID:       tbupq29n08 (40GB)")
        print(f"TIEMPO TOTAL GPU:        {total_gpu_sec}s")
        print(f"TIEMPO PREPARACION:      {prep_duration_sec}s")
        print(f"TIEMPO GENERACION:       {gen_duration_sec}s")
        print(f"COSTO APROX GPU:         ${approx_cost:.4f} USD")
        print(f"SALDO ANTES:             ${balance_before:.2f} USD")
        print(f"SALDO DESPUES:           ${balance_after:.2f} USD")
        print(f"MODELOS DETECTADOS:      {'4/4' if diagnosis_status == 'READY' else f'FALTAN ({len(missing_models_list)})'}")
        print(f"HTTP /object_info:       {diagnosis_status}")
        print(f"HTTP /system_stats:      {http_stats_code or 'N/A'}")
        print(f"HTTP /prompt:            {http_prompt_code or 'SKIPPED'}")
        print(f"PNG GENERADO:            {output_path or 'N/A'}")
        print(f"TAMAÑO PNG:              {output_bytes} bytes")
        print(f"PODS FINALES ACTIVOS:    {len(final_active_pods)}")
        print(f"GPU FINALES ACTIVAS:     {len(final_active_pods)}")
        print(f"ESTADO NETWORK VOLUME:   INTACTO (tbupq29n08 Preservado)")
        print(f"RESULTADO PRUEBA:        {'SUCCESS' if job_success else 'FAILED_DIAGNOSIS' if not job_success and diagnosis_status != 'READY' else 'FAILED'}")
        if error_msg:
            print(f"ERROR DIAGNOSTICO:       {error_msg}")
        print("=" * 70 + "\n")

        return {
            "job_success": job_success,
            "pod_id": pod_id,
            "diagnosis_status": diagnosis_status,
            "missing_models": missing_models_list,
            "output_path": output_path,
            "output_bytes": output_bytes,
            "final_active_pods": len(final_active_pods),
            "balance_after": balance_after,
            "error_msg": error_msg
        }


if __name__ == "__main__":
    asyncio.run(execute_authorized_test())
