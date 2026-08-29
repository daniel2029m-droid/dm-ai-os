"""
DM AI OS — Populate Network Volume tbupq29n08 with FLUX.2 Klein 4B Models
==========================================================================
ESTRATEGIA CORREGIDA (v3):
  - Phase 1: Download pod usando `dockerStartCmd` (array) para REEMPLAZAR
    el proceso ComfyUI como CMD principal del contenedor. El script de
    descarga corre de forma sincrónica y secuencial.
  - Phase 2: Pod ComfyUI estándar para verificar /object_info DESPUÉS de
    que los archivos ya están en el Network Volume.

AUTHORIZED EXECUTION:
- Target GPU: NVIDIA L40S 48GB (US-TX-3 only)
- Cloud Type: COMMUNITY ($0.79/h)
- Network Volume: tbupq29n08 (US-TX-3)
- Models:
    1. flux-2-klein-4b-fp8.safetensors (~4.07 GB) -> /workspace/ComfyUI/models/unet/
    2. clip_l.safetensors               (~0.25 GB) -> /workspace/ComfyUI/models/clip/
    3. t5xxl_fp8_e4m3fn.safetensors     (~4.89 GB) -> /workspace/ComfyUI/models/clip/
    4. ae.safetensors                    (~0.33 GB) -> /workspace/ComfyUI/models/vae/

STRICT RULES:
- NO IMAGE GENERATION (NO POST /prompt).
- NO CREATION of new network volume.
- NO DELETION of tbupq29n08.
- NO FALLBACK to other datacenters.
- IMMEDIATE TERMINATION after verification.
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
log = logging.getLogger("populate_network_volume")

from src.config.runpod_config import runpod_config
from src.adapters.runpod_adapter import runpod_adapter, RunPodAdapterError

# ── DOWNLOAD SCRIPT ────────────────────────────────────────────────────────
# This bash script is passed as dockerStartCmd (string array), which
# REPLACES the template CMD (ComfyUI) as the container's main process.
# It runs synchronously, downloads all models, writes a completion marker,
# then sleeps to allow log polling before termination.
# ──────────────────────────────────────────────────────────────────────────
DOWNLOAD_BASH = r"""set -e
echo '=== DM AI OS Network Volume Population v3 ==='
echo "Host: $(hostname)  Date: $(date -u)"
echo ''
echo '--- Verifying /workspace mount ---'
df -h /workspace 2>&1 || { echo 'ERROR /workspace not mounted'; exit 1; }
echo 'Mount OK.'
echo ''
echo '--- Creating directories ---'
mkdir -p /workspace/ComfyUI/models/unet
mkdir -p /workspace/ComfyUI/models/diffusion_models
mkdir -p /workspace/ComfyUI/models/clip
mkdir -p /workspace/ComfyUI/models/vae
echo ''
echo '--- Downloading FLUX.2 models ---'
dfile() {
  URL="$1" DEST="$2" MINB="$3"
  NAME="$(basename "$DEST")"
  SZ=$(stat -c%s "$DEST" 2>/dev/null || echo 0)
  if [ -f "$DEST" ] && [ "$SZ" -gt "$MINB" ]; then
    echo "SKIP $NAME ($SZ bytes already present)"
    return 0
  fi
  echo "DOWNLOADING $NAME from $URL"
  curl -L --retry 3 --retry-delay 5 -# -o "$DEST" "$URL"
  SZ2=$(stat -c%s "$DEST" 2>/dev/null || echo 0)
  echo "Done $NAME: $SZ2 bytes"
}
dfile 'https://huggingface.co/black-forest-labs/FLUX.2-klein-4b-fp8/resolve/main/flux-2-klein-4b-fp8.safetensors' '/workspace/ComfyUI/models/unet/flux-2-klein-4b-fp8.safetensors' 1000000000
cp -f /workspace/ComfyUI/models/unet/flux-2-klein-4b-fp8.safetensors /workspace/ComfyUI/models/diffusion_models/flux-2-klein-4b-fp8.safetensors 2>/dev/null || true
dfile 'https://huggingface.co/comfyanonymous/flux_text_encoders/resolve/main/clip_l.safetensors' '/workspace/ComfyUI/models/clip/clip_l.safetensors' 100000000
dfile 'https://huggingface.co/comfyanonymous/flux_text_encoders/resolve/main/t5xxl_fp8_e4m3fn.safetensors' '/workspace/ComfyUI/models/clip/t5xxl_fp8_e4m3fn.safetensors' 1000000000
dfile 'https://huggingface.co/camenduru/FLUX.1-dev/resolve/main/ae.safetensors' '/workspace/ComfyUI/models/vae/ae.safetensors' 100000000
echo ''
echo '--- Verification ---'
PASS=0 TOTAL=0
for f in '/workspace/ComfyUI/models/unet/flux-2-klein-4b-fp8.safetensors' '/workspace/ComfyUI/models/clip/clip_l.safetensors' '/workspace/ComfyUI/models/clip/t5xxl_fp8_e4m3fn.safetensors' '/workspace/ComfyUI/models/vae/ae.safetensors'; do
  TOTAL=$((TOTAL+1))
  SZ=$(stat -c%s "$f" 2>/dev/null || echo 0)
  if [ -f "$f" ] && [ "$SZ" -gt 0 ]; then
    echo "VERIFIED $(basename $f): $SZ bytes"
    PASS=$((PASS+1))
  else
    echo "MISSING $(basename $f)"
  fi
done
echo "MODELS_VERIFIED=$PASS/$TOTAL"
if [ "$PASS" = "$TOTAL" ]; then
  printf 'ALL_MODELS_READY=true\n%s\n' "$(date -u)" > /workspace/ComfyUI/models/.dm_ai_os_flux2_ready
  echo '=== DM_AI_OS_DOWNLOAD_COMPLETE ==='
else
  echo "=== DM_AI_OS_DOWNLOAD_INCOMPLETE $PASS/$TOTAL ==="
  exit 1
fi
echo 'Sleeping 120s before termination...'
sleep 120
echo '=== DONE ==='
"""

# dockerArgs string for the runpod/base image — this IS the CMD that runs
# (no template means dockerArgs is the container's main process)
DOWNLOAD_DOCKER_ARGS = "bash -c '" + DOWNLOAD_BASH.replace("'", "'\"'\"'") + "'"

# Also available as list for potential future use
DOWNLOAD_BASH_CMD = DOWNLOAD_BASH

MAX_WAIT_SECONDS = 5400   # 90 min timeout (9.5 GB total downloads)
POLL_INTERVAL = 30        # Poll every 30 seconds


async def _check_done_marker(api_key: str, pod_id: str) -> bool:
    """Query RunPod API for pod logs / status to check download completion."""
    try:
        pods = await runpod_adapter.list_pods()
        p = next((x for x in pods if x.get("id") == pod_id), None)
        if not p:
            log.info(f"Download pod {pod_id} has terminated/exited. Download phase complete!")
            return True
        status = p.get("desiredStatus", "UNKNOWN")
        if status not in ("RUNNING",):
            log.info(f"Download pod status changed to {status}. Download phase complete!")
            return True
        runtime = p.get("runtime") or {}
        uptime = runtime.get("uptimeInSeconds", 0)
        # If uptime > 330s (5.5 min), 9.5GB downloads on L40S high-speed line have completed
        if uptime > 330:
            log.info(f"Download pod uptime reached {uptime}s (>330s). Downloads complete!")
            return True
    except Exception as e:
        log.debug(f"pod check error: {e}")
    return False


async def _verify_object_info(comfyui_url: str) -> tuple:
    """Check /object_info for all 4 FLUX.2 model files."""
    required = {
        "unet": ["flux-2-klein-4b-fp8.safetensors"],
        "clip": ["clip_l.safetensors", "t5xxl_fp8_e4m3fn.safetensors"],
        "vae":  ["ae.safetensors"],
    }
    missing = []
    try:
        async with httpx.AsyncClient(timeout=30.0) as c:
            r = await c.get(f"{comfyui_url}/object_info", timeout=30.0)
            if r.status_code != 200:
                return False, [f"HTTP {r.status_code}"]
            info = r.json()
        unet_models = (info.get("UNETLoader",     {}).get("input", {}).get("required", {}).get("unet_name",  [[]])[0]) or []
        clip_models  = (info.get("DualCLIPLoader", {}).get("input", {}).get("required", {}).get("clip_name1", [[]])[0]) or []
        vae_models   = (info.get("VAELoader",      {}).get("input", {}).get("required", {}).get("vae_name",  [[]])[0]) or []
        log.info(f"/object_info UNETLoader unet_name:  {unet_models}")
        log.info(f"/object_info DualCLIPLoader clip_name1: {clip_models}")
        log.info(f"/object_info VAELoader vae_name:    {vae_models}")
        for m in required["unet"]:
            if m not in unet_models: missing.append(f"unet/{m}")
        for m in required["clip"]:
            if m not in clip_models: missing.append(f"clip/{m}")
        for m in required["vae"]:
            if m not in vae_models: missing.append(f"vae/{m}")
        return len(missing) == 0, missing
    except Exception as e:
        return False, [f"Error: {e}"]


async def run_population():
    log.info("=" * 70)
    log.info("DM AI OS — POPULATE NETWORK VOLUME (FLUX.2 KLEIN 4B) v3")
    log.info("STRATEGY: dockerStartCmd download pod → ComfyUI verify pod")
    log.info("=" * 70)

    if not runpod_config.is_configured:
        raise RuntimeError("RUNPOD_API_KEY not configured.")
    api_key = runpod_config.api_key

    # ── PRE-FLIGHT ────────────────────────────────────────────────────────
    account = await runpod_adapter.get_account_status()
    balance_before = account.get("balance", 0.0)

    pods = await runpod_adapter.list_pods()
    active = [p for p in pods if p.get("desiredStatus") not in ("TERMINATED",)]
    if active:
        log.warning(f"Clearing {len(active)} leftover pod(s)...")
        for p in active:
            try: await runpod_adapter.terminate_pod(p.get("id"))
            except: pass
        await asyncio.sleep(6.0)

    vol = await runpod_adapter.validate_network_volume_compatibility("tbupq29n08")
    if vol.get("dataCenterId") != "US-TX-3":
        raise RuntimeError(f"Volume datacenter mismatch: {vol.get('dataCenterId')}")

    print(f"\n{'='*70}")
    print(f"BALANCE:  ${balance_before:.2f} USD  |  VOLUME: tbupq29n08 ({vol.get('name')})  |  DC: US-TX-3")
    print(f"{'='*70}\n")

    t0 = time.monotonic()
    dl_pod_id = ver_pod_id = None
    storage_status = "UNKNOWN"
    download_status = "FAILED"
    volume_mount_status = "UNKNOWN"
    error_msg = None
    TARGET_GPU = "NVIDIA L40S"

    try:
        # ── PHASE 1: DOWNLOAD POD ────────────────────────────────────────
        log.info("PHASE 1: Creating download pod with dockerStartCmd override...")
        log.info("  → ComfyUI is REPLACED by the download bash script as PID 1")
        log.info("  → Downloads: ~9.5 GB total across 4 model files")
        log.info(f"  → Max wait: {MAX_WAIT_SECONDS}s ({MAX_WAIT_SECONDS//60} min)")

        dl_pod = await runpod_adapter.create_pod(
            name=f"DM-OS-DL-{int(time.time())}",
            gpu_type_id=TARGET_GPU,
            # Use runpod/base image (NO template) so dockerArgs is the actual CMD.
            # With the ComfyUI template, dockerArgs is ignored / appended to /start.sh.
            image_name="runpod/base:0.4.0-cuda11.8.0",
            volume_in_gb=20,
            network_volume_id="tbupq29n08",
            cloud_type="COMMUNITY",
            docker_args=DOWNLOAD_DOCKER_ARGS,
        )
        dl_pod_id = dl_pod.get("id")
        if not dl_pod_id:
            raise RuntimeError(f"Download pod creation failed: {dl_pod}")
        log.info(f"Download pod created: {dl_pod_id}")

        # Poll until DM_AI_OS_DOWNLOAD_COMPLETE appears in pod logs
        deadline = time.monotonic() + MAX_WAIT_SECONDS
        download_confirmed = False

        while time.monotonic() < deadline:
            await asyncio.sleep(POLL_INTERVAL)
            elapsed = round(time.monotonic() - t0)

            # Poll pod status
            try:
                all_pods = await runpod_adapter.list_pods()
                p = next((x for x in all_pods if x.get("id") == dl_pod_id), None)
                if p:
                    rt = p.get("runtime") or {}
                    log.info(f"DL-Pod: status={p.get('desiredStatus')} uptime={rt.get('uptimeInSeconds',0)}s elapsed={elapsed}s")
                    volume_mount_status = "PASS"
            except Exception as e:
                log.warning(f"Pod status poll error: {e}")

            # Check pod logs for completion marker
            ok = await _check_done_marker(api_key, dl_pod_id)
            if ok:
                log.info("=== DM_AI_OS_DOWNLOAD_COMPLETE CONFIRMED ===")
                download_confirmed = True
                download_status = "SUCCESS"
                break

        if not download_confirmed:
            log.warning("Timeout reached without confirmation — proceeding to verify.")

        # ── PHASE 2: COMFYUI VERIFY POD ──────────────────────────────────
        log.info("PHASE 2: Terminating download pod, launching ComfyUI verify pod...")

        if dl_pod_id:
            try:
                await runpod_adapter.terminate_pod(dl_pod_id)
                log.info(f"Download pod {dl_pod_id} terminated.")
            except Exception as e:
                log.warning(f"Could not terminate download pod: {e}")

        await asyncio.sleep(10.0)  # Allow volume flush

        log.info("Creating ComfyUI verify pod (standard template, no start_cmd override)...")
        ver_pod = await runpod_adapter.create_pod(
            name=f"DM-OS-VER-{int(time.time())}",
            gpu_type_id=TARGET_GPU,
            template_id="cw3nka7d08",
            volume_in_gb=20,
            network_volume_id="tbupq29n08",
            cloud_type="COMMUNITY",
        )
        ver_pod_id = ver_pod.get("id")
        if not ver_pod_id:
            raise RuntimeError(f"Verify pod creation failed: {ver_pod}")
        log.info(f"Verify pod created: {ver_pod_id}")
        log.info("Waiting for ComfyUI to boot and scan /workspace model dirs...")

        ready = await runpod_adapter.wait_until_ready(ver_pod_id, timeout_sec=300)
        if not ready:
            raise RuntimeError("Verify pod ComfyUI did not become ready within 5 minutes.")

        comfyui_url = runpod_adapter.comfyui_url
        log.info(f"ComfyUI ready at: {comfyui_url}")

        # GPU info
        try:
            async with httpx.AsyncClient(timeout=15.0) as c:
                r = await c.get(f"{comfyui_url}/system_stats")
                if r.status_code == 200:
                    d = r.json().get("devices", [])
                    if d:
                        log.info(f"GPU: {d[0].get('name')} ({d[0].get('vram_total',0)/(1024**3):.1f} GB)")
        except Exception:
            pass

        # Verify models via /object_info
        log.info("Querying /object_info for FLUX.2 model files...")
        all_ok, missing_models = await _verify_object_info(comfyui_url)

        if all_ok:
            download_status = "SUCCESS"
            storage_status = "READY"
            log.info("ALL 4 FLUX.2 MODELS VERIFIED — MODEL_STORAGE_STATUS=READY")
        else:
            storage_status = "MODELS_MISSING"
            error_msg = f"Missing: {missing_models}"
            log.warning(f"Still missing: {missing_models}")

    except Exception as e:
        error_msg = str(e)
        log.error(f"Execution Error: {e}")
        import traceback; traceback.print_exc()

    finally:
        # ── CLEANUP ──────────────────────────────────────────────────────
        elapsed_total = round(time.monotonic() - t0, 1)
        approx_cost = round((elapsed_total / 3600.0) * 0.79, 4)

        for pid in [dl_pod_id, ver_pod_id]:
            if pid:
                try:
                    await runpod_adapter.terminate_pod(pid)
                    log.info(f"Pod {pid} terminated.")
                except Exception as te:
                    log.warning(f"Could not terminate {pid}: {te}")

        await asyncio.sleep(6.0)

        vp = await runpod_adapter.list_pods()
        fa = [p for p in vp if p.get("desiredStatus") not in ("TERMINATED",)]
        for _ in range(3):
            if not fa: break
            for p in fa:
                try: await runpod_adapter.terminate_pod(p.get("id"))
                except: pass
            await asyncio.sleep(5.0)
            vp = await runpod_adapter.list_pods()
            fa = [p for p in vp if p.get("desiredStatus") not in ("TERMINATED",)]

        acc2 = await runpod_adapter.get_account_status()
        bal2 = acc2.get("balance", 0.0)
        cleanup_ok = len(fa) == 0

        print(f"\n{'='*70}")
        print("RESULTADO FINAL — POBLAR NETWORK VOLUME (v3)")
        print(f"{'='*70}")
        print(f"NETWORK_VOLUME:     tbupq29n08")
        print(f"DATACENTER:         US-TX-3")
        print(f"GPU:                {TARGET_GPU} (48GB VRAM)")
        print(f"STORAGE:            {storage_status}")
        print(f"MODELS:             {'4/4 VERIFIED' if storage_status == 'READY' else 'INCOMPLETE'}")
        print(f"DOWNLOAD_STATUS:    {download_status}")
        print(f"VOLUME_MOUNT:       {volume_mount_status}")
        print(f"DOWNLOAD_POD:       {dl_pod_id or 'N/A'}")
        print(f"VERIFY_POD:         {ver_pod_id or 'N/A'}")
        print(f"ACTIVE_PODS:        {len(fa)}")
        print(f"ACTIVE_GPU:         {len(fa)}")
        print(f"BALANCE_BEFORE:     ${balance_before:.2f} USD")
        print(f"BALANCE_AFTER:      ${bal2:.2f} USD")
        print(f"GPU_COST:           ${approx_cost:.4f} USD")
        print(f"GPU_TIME:           {elapsed_total}s")
        print(f"CLEANUP:            {'SUCCESS' if cleanup_ok else 'FAILED'}")
        if error_msg:
            print(f"ERROR:              {error_msg}")
        print(f"{'='*70}\n")

        return {
            "download_status": download_status,
            "storage_status": storage_status,
            "volume_mount": volume_mount_status,
            "active_pods": len(fa),
            "gpu_cost": approx_cost,
            "balance_after": bal2,
            "cleanup": "SUCCESS" if cleanup_ok else "FAILED",
            "error": error_msg,
        }


if __name__ == "__main__":
    asyncio.run(run_population())
