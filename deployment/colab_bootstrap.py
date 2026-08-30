"""
DM AI OS — Google Colab & Remote GPU Bootstrap Client
=====================================================
Single-command reproducible bootstrap for Google Colab (Tesla T4 16GB).

Steps executed:
  1. Detect CUDA GPU & verify Tesla T4 + VRAM.
  2. Setup & optimize ComfyUI runtime (Google Drive persistence or local /content).
  3. Start ComfyUI backend in background.
  4. Start Cloudflare Tunnel (cloudflared) or ngrok.
  5. Verify local health probe (/system_stats).
  6. Register worker with DM AI OS (https://ai.dmorales.com.ar).
  7. Start background heartbeat daemon (every 30s).
  8. Print status banner: READY.
"""

import os
import sys
import time
import json
import socket
import urllib.request
import urllib.error
import subprocess
import threading
from pathlib import Path


# ── Configuration Defaults ─────────────────────────────────────

DM_AI_OS_URL = os.getenv("DM_AI_OS_URL", "https://ai.dmorales.com.ar")
WORKER_ID = os.getenv("DM_WORKER_ID", "colab-comfy-primary")
SESSION_ID = os.getenv("DM_SESSION_ID", f"rt-colab-{int(time.time())}")
COMFY_PORT = 8188

# ── Model Storage Plane ────────────────────────────────────────────
# Canonical Drive mount point (Colab standard)
DRIVE_MOUNT_POINT = "/content/drive"
# Default model storage root relative to MyDrive. Override via env: DM_DRIVE_MODELS_PATH
DRIVE_MODELS_DEFAULT_SUBPATH = "MyDrive/DM-AI-OS-MODELS"
# Minimum free disk (GB) that must remain after any copy operation
COPY_SAFETY_MARGIN_GB = 5.0
# Model categories that ComfyUI recognises
MODEL_CATEGORIES = [
    "checkpoints", "diffusion_models", "unet",
    "clip", "text_encoders", "vae",
    "loras", "controlnet", "upscale_models",
]


def log_step(emoji: str, title: str, details: str = ""):
    print(f"\n{emoji} \033[1;36m[{title}]\033[0m {details}")


def get_gpu_info() -> dict:
    """Detects CUDA GPU name and VRAM."""
    try:
        import torch
        if torch.cuda.is_available():
            name = torch.cuda.get_device_name(0)
            vram_bytes = torch.cuda.get_device_properties(0).total_memory
            vram_gb = round(vram_bytes / (1024 ** 3), 2)
            return {"available": True, "name": name, "vram_gb": vram_gb}
    except Exception:
        pass

    # Fallback to nvidia-smi
    try:
        out = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
            text=True
        ).strip()
        parts = out.split(",")
        return {"available": True, "name": parts[0].strip(), "vram_gb": round(float(parts[1]) / 1024, 2)}
    except Exception:
        return {"available": False, "name": "No CUDA GPU Detected", "vram_gb": 0.0}


def wait_for_port(port: int, timeout: int = 60) -> bool:
    """Waits until local port is open."""
    start = time.time()
    while time.time() - start < timeout:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1.0):
                return True
        except (socket.timeout, ConnectionRefusedError):
            time.sleep(1.0)
    return False


def start_cloudflare_tunnel(port: int = 8188) -> str:
    """Downloads cloudflared if needed and launches quick tunnel."""
    cloudflared_path = Path("/content/cloudflared")
    if not cloudflared_path.exists():
        if not Path("cloudflared").exists():
            log_step("📦", "Instalando Cloudflared Tunnel...", "")
            subprocess.run(
                ["wget", "-q", "-nc", "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64", "-O", "/content/cloudflared"],
                check=False
            )
            subprocess.run(["chmod", "+x", "/content/cloudflared"], check=False)
            cloudflared_bin = "/content/cloudflared"
        else:
            cloudflared_bin = "./cloudflared"
    else:
        cloudflared_bin = "/content/cloudflared"

    # Cleanup any previous cloudflared instances
    subprocess.run(["pkill", "-9", "-f", "cloudflared"], check=False)
    time.sleep(1.0)

    log_step("🌐", "Iniciando túnel seguro Cloudflare...", f"Puerto {port}")
    cmd = [cloudflared_bin, "tunnel", "--url", f"http://127.0.0.1:{port}"]
    log_file = open("/content/cloudflared.log", "w") if Path("/content").exists() else open("cloudflared.log", "w")
    proc = subprocess.Popen(cmd, stdout=log_file, stderr=log_file)

    # Poll log for trycloudflare.com URL
    tunnel_url = None
    for _ in range(40):
        time.sleep(1.0)
        log_path = Path("/content/cloudflared.log") if Path("/content").exists() else Path("cloudflared.log")
        if log_path.exists():
            content = log_path.read_text(errors="ignore")
            for line in content.splitlines():
                if "trycloudflare.com" in line and "https://" in line:
                    for token in line.split():
                        if token.startswith("https://") and "trycloudflare.com" in token:
                            tunnel_url = token.strip().rstrip("/")
                            break
                    if tunnel_url:
                        break
        if tunnel_url:
            break

    if tunnel_url:
        log_step("⏳", "Esperando propagación del túnel Cloudflare...", tunnel_url)
        for _ in range(20):
            try:
                req = urllib.request.Request(
                    f"{tunnel_url}/system_stats",
                    headers={"User-Agent": "DM-AI-OS-Colab-Bootstrap/1.5.1"}
                )
                with urllib.request.urlopen(req, timeout=5) as resp:
                    if resp.status == 200:
                        print("   Túnel Verificado: \033[1;32mONLINE (200 OK)\033[0m")
                        break
            except Exception:
                time.sleep(1.5)

    return tunnel_url or ""


def register_worker_with_dmaios(
    dmaios_url: str,
    worker_id: str,
    session_id: str,
    tunnel_url: str,
    gpu_info: dict,
    installed_models: list | None = None
) -> dict:
    """Sends registration payload to DM AI OS.
    installed_models: pre-computed list from discover_available_models(). If None, defaults to [sd15_base].
    DOES NOT auto-add FLUX or WAN — only what was physically discovered.
    """
    if installed_models is None:
        installed_models = ["sd15_base"]

    capabilities = ["image"]
    if any("i2v" in m or "video" in m or "wan" in m for m in installed_models):
        capabilities.append("video")

    payload = {
        "worker_id": worker_id,
        "session_id": session_id,
        "backend": "google-colab",
        "provider": "comfyui",
        "endpoint": tunnel_url,
        "tunnel_endpoint": tunnel_url,
        "gpu_name": gpu_info.get("name", "Tesla T4"),
        "vram_gb": gpu_info.get("vram_gb", 16.0),
        "comfy_version": "0.3.18",
        "models": installed_models,
        "capabilities": capabilities
    }

    req = urllib.request.Request(
        f"{dmaios_url.rstrip('/')}/api/v1/workers/register",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "User-Agent": "DM-AI-OS-Colab-Bootstrap/1.5.1"}
    )

    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))


def start_heartbeat_thread(dmaios_url: str, worker_id: str, session_id: str, interval_sec: int = 30):
    """Background daemon thread sending heartbeat pings to DM AI OS."""
    hb_url = f"{dmaios_url.rstrip('/')}/api/v1/workers/heartbeat"

    def _loop():
        while True:
            try:
                payload = {"worker_id": worker_id, "session_id": session_id}
                req = urllib.request.Request(
                    hb_url,
                    data=json.dumps(payload).encode("utf-8"),
                    headers={"Content-Type": "application/json", "User-Agent": "DM-AI-OS-Heartbeat/1.5.1"}
                )
                with urllib.request.urlopen(req, timeout=10) as resp:
                    pass
            except Exception:
                pass
            time.sleep(interval_sec)

    t = threading.Thread(target=_loop, daemon=True)
    t.start()
    return t


# ── Google Drive Storage Plane ────────────────────────────────────────────

def mount_google_drive() -> bool:
    """
    Mounts Google Drive using the official Google Colab OAuth mechanism.
    Identity is resolved by Colab OAuth — NO credentials stored in code.
    Returns True if Drive was successfully mounted.
    """
    if not Path("/content").exists():
        print("   [⚠️] Not running in Colab — Drive mount skipped.")
        return False
    if Path(f"{DRIVE_MOUNT_POINT}/MyDrive").exists():
        print("   Drive ya montado en /content/drive/MyDrive")
        return True
    try:
        from google.colab import drive  # type: ignore
        drive.mount(DRIVE_MOUNT_POINT, force_remount=False)
        mounted = Path(f"{DRIVE_MOUNT_POINT}/MyDrive").exists()
        if mounted:
            print("   \033[1;32mGoogle Drive montado correctamente.\033[0m")
        else:
            print("   \033[1;33m[AVISO] Mount retornó pero MyDrive no es accesible.\033[0m")
        return mounted
    except ImportError:
        print("   No es un entorno Colab — Drive mount omitido.")
        return False
    except Exception as e:
        print(f"   \033[1;31m[ERROR] Drive mount falló: {e}\033[0m")
        return False


def get_drive_models_path() -> Path:
    """
    Resolves the model storage root path.
    Checks DM_AI_OS (canonical), DM-AI-OS-MODELS, or env override.
    """
    env_val = os.getenv("DM_DRIVE_MODELS_PATH")
    if env_val:
        return Path(env_val)
    
    mydrive = Path(DRIVE_MOUNT_POINT) / "MyDrive"
    for candidate_name in ["DM_AI_OS", "DM-AI-OS-MODELS", "DM_AI_OS_MODELS"]:
        cand = mydrive / candidate_name
        if cand.exists():
            return cand
    return mydrive / "DM_AI_OS"



def run_drive_diagnostic(models_root: Path) -> dict:
    """
    Runs a non-destructive diagnostic of the Drive model storage root.
    Checks mount, read access, write access, and directory structure.
    DOES NOT download models. DOES NOT report space as “5 TB verified”.
    """
    result = {
        "drive_mount": False,
        "model_root_exists": False,
        "read_access": False,
        "write_access": False,
        "reported_available_storage": "unknown",
        "directories": {},
        "pass": False,
    }

    mount_path = Path(DRIVE_MOUNT_POINT) / "MyDrive"
    result["drive_mount"] = mount_path.exists()
    if not result["drive_mount"]:
        return result

    result["model_root_exists"] = models_root.exists()
    if not result["model_root_exists"]:
        return result

    # Read check
    try:
        list(models_root.iterdir())
        result["read_access"] = True
    except Exception as e:
        print(f"   Read error: {e}")
        return result

    # Write check (small temp file, deleted immediately)
    test_file = models_root / ".dm_write_test"
    try:
        test_file.write_text("DM-AI-OS write check")
        test_file.unlink()
        result["write_access"] = True
    except Exception as e:
        print(f"   Write error: {e}")

    # Reported storage (not authoritative for quota, just informational)
    try:
        import shutil
        total, used, free = shutil.disk_usage(str(mount_path))
        result["reported_available_storage"] = f"{round(free / (1024**3), 1)} GB (reported by OS, may be approximate)"
    except Exception:
        pass

    # Directory structure check
    expected_dirs = ["checkpoints", "diffusion_models", "text_encoders",
                     "clip", "vae", "loras", "controlnet", "upscale_models", "manifests"]
    for d in expected_dirs:
        result["directories"][d] = (models_root / d).exists()

    result["pass"] = result["write_access"] and result["read_access"]
    return result


def check_disk_space_for_copy(required_size_bytes: int, safety_margin_gb: float = COPY_SAFETY_MARGIN_GB) -> bool:
    """
    Conservative disk space check before copying a model to local runtime.
    NEVER copies automatically without this check passing.
    required_size_bytes: total bytes of all components to copy
    safety_margin_gb: minimum free space to leave after copy
    Returns True only if: required + safety_margin < available
    """
    import shutil
    try:
        stat = shutil.disk_usage("/content")
        free_gb = stat.free / (1024 ** 3)
        required_gb = required_size_bytes / (1024 ** 3)
        total_needed_gb = required_gb + safety_margin_gb
        will_fit = total_needed_gb < free_gb
        print(f"   Disco libre: {free_gb:.1f} GB | Requerido: {required_gb:.1f} GB | Margen: {safety_margin_gb:.0f} GB | Copia: {'YES' if will_fit else 'NO'}")
        return will_fit
    except Exception as e:
        print(f"   [AVISO] No se pudo verificar espacio en disco: {e}")
        return False  # Conservative: deny if unknown


def find_component_in_storage(filename: str, category: str, search_roots: list) -> Path | None:
    """
    Searches for a model component file across all registered storage roots and Google Drive.
    """
    search_paths = list(search_roots)
    mydrive = Path(DRIVE_MOUNT_POINT) / "MyDrive"

    if mydrive.exists() and mydrive not in search_paths:
        search_paths.append(mydrive)

    category_aliases = [category]
    if category in ("unet", "diffusion_models"):
        category_aliases = ["diffusion_models", "unet"]
    elif category in ("clip", "text_encoders"):
        category_aliases = ["text_encoders", "clip"]

    for root in search_paths:
        root_path = Path(root)
        if not root_path.exists():
            continue
        for cat in category_aliases:
            candidates = [
                root_path / cat / filename,
                root_path / "models" / cat / filename,
                root_path / filename,
                root_path / "DM_AI_OS" / "AI_LIBRARY" / "IMAGE" / "Z_IMAGE_TURBO" / cat / filename,
                root_path / "AI_LIBRARY" / "IMAGE" / "Z_IMAGE_TURBO" / cat / filename,
                root_path / "DM-AI-OS-MODELS" / cat / filename,
                root_path / "DM_AI_OS" / cat / filename,
            ]
            for c in candidates:
                if c.exists() and c.is_file():
                    return c
        # Recursive fallback search
        try:
            for match in root_path.rglob(filename):
                if match.is_file() and match.stat().st_size > 10_000_000:
                    return match
        except Exception:
            pass
    return None


def generate_extra_model_paths_yaml(comfy_dir: Path, storage_roots: list) -> Path:
    """
    Generates ComfyUI extra_model_paths.yaml mapping all active storage roots.
    """
    yaml_path = comfy_dir / "extra_model_paths.yaml"
    lines = [
        "# DM AI OS v1.5.1 — Auto-generated Model Storage Paths",
        "# Generated by colab_bootstrap.py — DO NOT EDIT MANUALLY",
        "",
    ]
    for idx, root in enumerate(storage_roots):
        root_str = str(root).replace("\\", "/")
        label = f"dm_storage_{idx}"
        lines += [
            f"{label}:",
            f"    base_path: {root_str}",
            "    checkpoints: checkpoints",
            "    diffusion_models: diffusion_models",
            "    unet: diffusion_models",
            "    clip: clip",
            "    text_encoders: text_encoders",
            "    vae: vae",
            "    loras: loras",
            "    controlnet: controlnet",
            "    upscale_models: upscale_models",
            "",
        ]
    content = "\n".join(lines)
    yaml_path.write_text(content, encoding="utf-8")
    print(f"   extra_model_paths.yaml generado: {yaml_path}")
    return yaml_path


def discover_available_models(storage_roots: list, comfy_dir: Path) -> dict:
    """
    Discovers which model components are physically present across all storage roots.
    Automatically symlinks discovered files to local ComfyUI models folder for instant indexing.
    """
    COMPONENT_MANIFEST = {
        "sd15_base": [
            {"filename": "v1-5-pruned-emaonly-fp16.safetensors", "category": "checkpoints", "min_size_bytes": 1_500_000_000},
        ],
        "zimage_turbo": [
            {"filename": ["z_image_turbo_bf16.safetensors", "z_image_turbo_fp8_e4m3fn.safetensors", "z_image_turbo.safetensors"], "category": "diffusion_models", "min_size_bytes": 3_500_000_000},
            {"filename": ["qwen_3_4b.safetensors", "qwen3_4b.safetensors"], "category": "text_encoders", "min_size_bytes": 1_500_000_000},
            {"filename": ["ae.safetensors"], "category": "vae", "min_size_bytes": 50_000_000},
        ],
        "seedvr2_upscale": [
            {"filename": ["seedvr2_upscale_v1.safetensors", "seedvr2.safetensors"], "category": "upscale_models", "min_size_bytes": 50_000_000},
        ],
        "flux1_schnell_fp8": [
            {"filename": ["flux1-schnell-fp8.safetensors", "flux1-schnell.safetensors"], "category": "diffusion_models", "min_size_bytes": 10_000_000_000},
            {"filename": ["clip_l.safetensors"], "category": "clip", "min_size_bytes": 200_000_000},
            {"filename": ["t5xxl_fp8_e4m3fn.safetensors"], "category": "clip", "min_size_bytes": 4_000_000_000},
            {"filename": ["ae.safetensors"], "category": "vae", "min_size_bytes": 50_000_000},
        ],
        "flux2_klein_4b_fp8": [
            {"filename": ["flux-2-klein-4b-fp8.safetensors", "flux2-klein-4b.safetensors"], "category": "diffusion_models", "min_size_bytes": 3_500_000_000},
            {"filename": ["clip_l.safetensors"], "category": "clip", "min_size_bytes": 200_000_000},
            {"filename": ["t5xxl_fp8_e4m3fn.safetensors"], "category": "clip", "min_size_bytes": 4_000_000_000},
            {"filename": ["ae.safetensors"], "category": "vae", "min_size_bytes": 50_000_000},
        ],
        "sdxl_base": [
            {"filename": ["juggernautXL_v9_RunDiffusionPhoto.safetensors", "sd_xl_base_1.0.safetensors", "sdxl_base.safetensors", "juggernaut_xl.safetensors"], "category": "checkpoints", "min_size_bytes": 4_000_000_000},
        ],
        "wan22_i2v": [
            {"filename": ["wan2.1_i2v_480p_14B_fp8.safetensors", "wan2.2_i2v_480p_14B_fp8_scaled.safetensors", "wan2.1_i2v.safetensors"], "category": "diffusion_models", "min_size_bytes": 8_000_000_000},
            {"filename": ["umt5_xxl_fp8_e4m3fn_scaled.safetensors", "umt5_xxl.safetensors"], "category": "clip", "min_size_bytes": 3_000_000_000},
            {"filename": ["wan_2.1_vae.safetensors", "wan_vae.safetensors"], "category": "vae", "min_size_bytes": 50_000_000},
        ],

    }

    results = {}
    for model_id, components in COMPONENT_MANIFEST.items():
        found = []
        missing = []
        for comp in components:
            filenames = comp["filename"] if isinstance(comp["filename"], list) else [comp["filename"]]
            comp_found = False
            for fn in filenames:
                path = find_component_in_storage(fn, comp["category"], storage_roots)
                if path and is_valid_safetensors(path, min_bytes=comp["min_size_bytes"]):
                    found.append({"filename": fn, "path": str(path)})
                    comp_found = True
                    try:
                        cat_dir = comfy_dir / "models" / comp["category"]
                        cat_dir.mkdir(parents=True, exist_ok=True)
                        link_target = cat_dir / fn
                        if not link_target.exists():
                            if link_target.is_symlink():
                                link_target.unlink()
                            link_target.symlink_to(path)
                            print(f"   [Link] {fn} -> {cat_dir}")
                    except Exception as e:
                        print(f"   [Link aviso] {fn}: {e}")
                    break
            if not comp_found:
                missing.append({"filename": filenames[0], "reason": "NOT_FOUND"})


        all_present = len(missing) == 0
        results[model_id] = {
            "discovered": all_present,
            "status": "DISCOVERED" if all_present else "MISSING_COMPONENTS",
            "components_found": found,
            "components_missing": missing,
        }
        status_icon = "✅" if all_present else "⭘"
        print(f"   {status_icon} {model_id}: {results[model_id]['status']} ({len(found)}/{len(components)} componentes)")

    return results


def is_valid_safetensors(file_path: Path, min_bytes: int = 10_000_000) -> bool:
    """Validates that file exists and meets minimum size."""
    if not file_path.exists():
        return False
    try:
        size = file_path.stat().st_size
        return size >= min_bytes
    except Exception:
        return False



def download_and_validate_checkpoint(ckpt_dir: Path) -> bool:
    """Downloads SD 1.5 FP16 checkpoint with full physical diagnostics and validation."""
    sd15_url = "https://huggingface.co/Comfy-Org/stable-diffusion-v1-5-archive/resolve/main/v1-5-pruned-emaonly-fp16.safetensors"
    expected_size = 2_132_696_762
    sd15_file = ckpt_dir / "v1-5-pruned-emaonly-fp16.safetensors"

    print("\n" + "=" * 65)
    print("=== CHECKPOINT DOWNLOAD DIAGNOSTIC ===")
    print(f"URL:             {sd15_url}")
    print(f"DESTINATION:     {sd15_file}")
    print(f"EXPECTED SIZE:   {expected_size:,} bytes (~2.13 GB)")

    # Disk Free Check
    import shutil
    stat_dir = ckpt_dir.parent if ckpt_dir.exists() else Path("/content") if Path("/content").exists() else Path(".")
    total_b, used_b, free_b = shutil.disk_usage(str(stat_dir))
    print(f"DISK FREE:       {round(free_b / (1024**3), 2)} GB")

    file_exists_before = sd15_file.exists()
    file_size_before = sd15_file.stat().st_size if file_exists_before else 0
    print(f"FILE EXISTS BEFORE: {file_exists_before}")
    print(f"FILE SIZE BEFORE:   {file_size_before:,} bytes")

    # If already valid, skip re-download
    if is_valid_safetensors(sd15_file, min_bytes=2_000_000_000):
        print("\n✅ Checkpoint ya existe en disco y es un safetensors binario válido.")
        print(f"FILE SIZE AFTER: {sd15_file.stat().st_size:,} bytes")
        print("===================================================\n")
        return True

    # If corrupted or partial (< 2GB), remove it
    if file_exists_before:
        print("⚠️ Archivo existente inválido o incompleto. Eliminando para descarga limpia...")
        try:
            sd15_file.unlink()
        except Exception as e:
            print(f"Aviso al eliminar: {e}")

    # Inspect Remote URL via HTTP HEAD
    print("\n🔍 Consultando cabeceras HTTP del servidor remoto...")
    final_url = sd15_url
    http_status = 0
    content_type = "unknown"
    content_length = "unknown"
    try:
        req = urllib.request.Request(sd15_url, headers={"User-Agent": "DM-AI-OS-Colab-Bootstrap/1.5.1"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            final_url = resp.geturl()
            http_status = resp.status
            content_type = resp.headers.get("Content-Type", "")
            content_length = resp.headers.get("Content-Length", "")
    except Exception as e:
        print(f"Consulta HTTP directa: {e}")

    print(f"FINAL URL:       {final_url}")
    print(f"HTTP STATUS:     {http_status}")
    print(f"CONTENT-TYPE:    {content_type}")
    print(f"CONTENT-LENGTH:  {content_length}")

    # Download with progress using wget or urllib
    print("\n📥 Iniciando descarga binaria...")
    download_success = False

    # Try aria2c for accelerated multi-stream download if present
    if subprocess.run(["which", "aria2c"], capture_output=True).returncode == 0:
        print("DOWNLOAD METHOD: aria2c (16 streams)")
        res = subprocess.run(
            ["aria2c", "-c", "-x", "16", "-s", "16", "-k", "1M", sd15_url, "-d", str(ckpt_dir), "-o", sd15_file.name],
            check=False
        )
        download_success = (res.returncode == 0) and is_valid_safetensors(sd15_file)

    # Fallback to wget
    if not download_success:
        print("DOWNLOAD METHOD: wget --show-progress")
        res = subprocess.run(
            ["wget", "-c", "--show-progress", "-q", sd15_url, "-O", str(sd15_file)],
            check=False
        )
        download_success = (res.returncode == 0) and is_valid_safetensors(sd15_file)

    # Fallback to Python streaming
    if not download_success:
        print("DOWNLOAD METHOD: Python urllib chunked stream")
        try:
            req = urllib.request.Request(sd15_url, headers={"User-Agent": "DM-AI-OS-Colab-Bootstrap/1.5.1"})
            with urllib.request.urlopen(req, timeout=300) as response, open(sd15_file, "wb") as out_file:
                total_size = int(response.headers.get("Content-Length", expected_size))
                downloaded = 0
                block_size = 1024 * 1024 * 8  # 8MB chunks
                while True:
                    buffer = response.read(block_size)
                    if not buffer:
                        break
                    downloaded += len(buffer)
                    out_file.write(buffer)
                    pct = int(downloaded / total_size * 100) if total_size > 0 else 0
                    print(f"\r   Progreso: {downloaded:,} / {total_size:,} bytes ({pct}%)", end="", flush=True)
                print()
            download_success = is_valid_safetensors(sd15_file)
        except Exception as e:
            print(f"\n[ERROR] Descarga Python falló: {e}")

    file_exists_after = sd15_file.exists()
    file_size_after = sd15_file.stat().st_size if file_exists_after else 0
    size_ratio = round(file_size_after / expected_size, 4) if expected_size > 0 else 0

    print(f"\nFILE EXISTS AFTER:  {file_exists_after}")
    print(f"FILE SIZE AFTER:    {file_size_after:,} bytes")
    print(f"SIZE RATIO:         {size_ratio} (1.0 = completo)")

    if is_valid_safetensors(sd15_file, min_bytes=2_000_000_000):
        print("✅ VALIDACIÓN BINARIA: Cabecera safetensors válida y tamaño correcto.")
        print("===================================================\n")
        return True
    else:
        print("❌ VALIDACIÓN BINARIA: Archivo incompleto, corrupto o payload de error.")
        print("===================================================\n")
        return False


def run_bootstrap():
    print("=" * 65)
    print("🚀 DM AI OS v1.5.1 — Google Colab Compute Worker Bootstrap")
    print("=" * 65)

    # 1. GPU Detection
    log_step("🔍", "Detectando Hardware GPU...", "")
    gpu = get_gpu_info()
    print(f"   GPU:  \033[1;32m{gpu['name']}\033[0m")
    print(f"   VRAM: \033[1;32m{gpu['vram_gb']} GB\033[0m")

    if not gpu["available"]:
        print("\033[1;31m[ADVERTENCIA] No se detectó GPU CUDA. Ejecutando en modo CPU limitado.\033[0m")

    # 2. Google Drive Mount (OAuth — no credentials stored)
    log_step("📁", "Montando Google Drive...", "OAuth Colab (sin credenciales en código)")
    drive_mounted = mount_google_drive()

    # 3. Resolve storage paths
    storage_roots = []
    if drive_mounted:
        models_root = get_drive_models_path()
        log_step("📊", "Drive Diagnostic...", str(models_root))
        diag = run_drive_diagnostic(models_root)
        print(f"   DRIVE MOUNT:                {'PASS' if diag['drive_mount'] else 'FAIL'}")
        print(f"   MODEL STORAGE ROOT:         {'PASS' if diag['model_root_exists'] else 'FAIL — crear DM-AI-OS-MODELS en Drive'}")
        print(f"   READ ACCESS:                {'PASS' if diag['read_access'] else 'FAIL'}")
        print(f"   WRITE ACCESS:               {'PASS' if diag['write_access'] else 'FAIL'}")
        print(f"   REPORTED AVAILABLE STORAGE: {diag['reported_available_storage']}")
        missing_dirs = [d for d, ok in diag["directories"].items() if not ok]
        if missing_dirs:
            print(f"   [AVISO] Carpetas faltantes en Drive: {missing_dirs}")
        if diag["model_root_exists"] and diag["read_access"]:
            storage_roots.append(models_root)

    # 4. ComfyUI Setup
    comfy_dir = Path("/content/ComfyUI") if Path("/content").exists() else Path("./ComfyUI")
    if not comfy_dir.exists():
        log_step("📦", "Clonando repositorio ComfyUI...", "")
        subprocess.run(["git", "clone", "--depth", "1", "https://github.com/comfyanonymous/ComfyUI.git", str(comfy_dir)], check=False)

    req_file = comfy_dir / "requirements.txt"
    if req_file.exists():
        subprocess.run([sys.executable, "-m", "pip", "install", "-q", "-r", str(req_file)], check=False)
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", "alembic", "blake3", "comfy-aimdo"], check=False)


    # Auto-install ReActor Face Swap custom node for 1-click Face Swapping & Consistency
    reactor_dir = comfy_dir / "custom_nodes" / "ComfyUI-ReActor"
    # Clean any old or broken directories
    for old_dir in [comfy_dir / "custom_nodes" / "comfyui-reactor-node", comfy_dir / "custom_nodes" / "ComfyUI-ReActor"]:
        if old_dir.exists() and not (old_dir / "__init__.py").exists():
            import shutil
            shutil.rmtree(str(old_dir), ignore_errors=True)

    if not reactor_dir.exists():
        log_step("🎭", "Instalando ReActor Face Swap...", "")
        env_git = os.environ.copy()
        env_git["GIT_TERMINAL_PROMPT"] = "0"
        subprocess.run(["git", "clone", "--depth", "1", "https://github.com/Gourieff/ComfyUI-ReActor.git", str(reactor_dir)], env=env_git, check=False)

    if reactor_dir.exists():
        reactor_req = reactor_dir / "requirements.txt"
        if reactor_req.exists():
            subprocess.run([sys.executable, "-m", "pip", "install", "-q", "-r", str(reactor_req)], check=False)
        subprocess.run([sys.executable, "-m", "pip", "install", "-q", "insightface", "onnx", "onnxruntime-gpu", "opencv-python"], check=False)
        log_step("🎭", "Descargando modelo biométrico inswapper_128.onnx...", "")
        insight_models = comfy_dir / "models" / "insightface"
        facerestore_models = comfy_dir / "models" / "facerestore_models"
        insight_models.mkdir(parents=True, exist_ok=True)
        facerestore_models.mkdir(parents=True, exist_ok=True)
        inswapper_target = insight_models / "inswapper_128.onnx"
        if not inswapper_target.exists() or inswapper_target.stat().st_size < 500_000_000:
            subprocess.run(["wget", "-c", "https://huggingface.co/ezioroz/inswapper_128.onnx/resolve/main/inswapper_128.onnx", "-O", str(inswapper_target)], check=False)
        gfpgan_target = facerestore_models / "GFPGANv1.4.pth"
        if not gfpgan_target.exists() or gfpgan_target.stat().st_size < 300_000_000:
            subprocess.run(["wget", "-c", "https://github.com/TencentARC/GFPGAN/releases/download/v1.3.0/GFPGANv1.4.pth", "-O", str(gfpgan_target)], check=False)

    ckpt_dir = comfy_dir / "models" / "checkpoints"
    ckpt_dir.mkdir(parents=True, exist_ok=True)




    # Also add ComfyUI's own models dir as a storage root (for local cache hits)
    local_models_root = comfy_dir / "models"
    if local_models_root.exists() and local_models_root not in storage_roots:
        storage_roots.append(local_models_root)

    # 5. Discover available models across all storage roots
    log_step("🔎", "Descubriendo modelos en storage...", f"{len(storage_roots)} storage root(s)")
    discovered = discover_available_models(storage_roots, comfy_dir)
    discovered_model_ids = [mid for mid, info in discovered.items() if info["discovered"]]
    print(f"   Modelos descubiertos: {discovered_model_ids}")

    # 6. Generate extra_model_paths.yaml for ComfyUI
    if storage_roots:
        log_step("🗂️", "Generando extra_model_paths.yaml...", "")
        generate_extra_model_paths_yaml(comfy_dir, storage_roots)

    # 7. SD15 validation and download fallback (SD15 E2E is frozen — do not modify workflow)
    log_step("⚙️", "Validando SD15...", "")
    if not download_and_validate_checkpoint(ckpt_dir):
        print("\033[1;31m[ERROR FATAL] El checkpoint SD 1.5 no pudo validarse. Abortando registro.\033[0m")
        return

    # 8. Launch ComfyUI in Background
    subprocess.run(["pkill", "-9", "-f", "main.py"], check=False)
    time.sleep(1.0)
    log_step("⚡", "Arrancando servidor ComfyUI...", f"Puerto {COMFY_PORT}")
    comfy_cmd = [
        sys.executable, str(comfy_dir / "main.py"),
        "--listen", "127.0.0.1",
        "--port", str(COMFY_PORT),
        "--fp8_e4m3fn-unet",
        "--lowvram",
        "--preview-method", "auto"
    ]
    log_path = "/content/comfyui.log" if Path("/content").exists() else "comfyui.log"
    comfy_log = open(log_path, "w")
    subprocess.Popen(comfy_cmd, stdout=comfy_log, stderr=comfy_log)

    log_step("⏳", "Esperando respuesta de ComfyUI /system_stats...", "")
    if not wait_for_port(COMFY_PORT, timeout=90):
        print("\033[1;31m[ERROR] ComfyUI no respondió en el puerto 8188.\033[0m")
        if Path(log_path).exists():
            print("--- ÚLTIMAS LÍNEAS DE COMFYUI.LOG ---")
            lines = Path(log_path).read_text(encoding="utf-8", errors="ignore").splitlines()[-25:]
            for l in lines:
                print("   " + l)
            print("-------------------------------------")
        return


    # 9. Validate SD15 indexed in ComfyUI (SD15 E2E frozen — must continue to pass)
    sd15_indexed = False
    for _ in range(10):
        try:
            req = urllib.request.Request(f"http://127.0.0.1:{COMFY_PORT}/object_info/CheckpointLoaderSimple")
            with urllib.request.urlopen(req, timeout=5) as r:
                data = json.loads(r.read().decode())
                ckpts = data.get("CheckpointLoaderSimple", {}).get("input", {}).get("required", {}).get("ckpt_name", [[]])[0]
                if "v1-5-pruned-emaonly-fp16.safetensors" in ckpts:
                    print("   Checkpoint SD15: \033[1;32mv1-5-pruned-emaonly-fp16.safetensors INDEXADO\033[0m")
                    sd15_indexed = True
                    break
        except Exception:
            pass
        time.sleep(2)

    if not sd15_indexed:
        print("   \033[1;33m[AVISO] SD15 aún no indexado. ComfyUI puede estar cargando.\033[0m")

    # 10. Validate discovered model indexing (CONFIGURED status only — not READY)
    log_step("📌", "Validando indexado de modelos en ComfyUI...", "")
    for model_id in discovered_model_ids:
        if model_id == "sd15_base":
            continue  # Already validated above
        print(f"   {model_id}: DISCOVERED (requiere prueba física para READY)")

    # 11. Start Cloudflare Tunnel
    tunnel_url = start_cloudflare_tunnel(COMFY_PORT)
    if not tunnel_url:
        print("\033[1;31m[ERROR] No se pudo obtener la URL del túnel Cloudflare.\033[0m")
        return
    print(f"   Túnel Activo: \033[1;32m{tunnel_url}\033[0m")

    # 12. Register worker with real capability matrix (only discovered models)
    log_step("🤝", "Registrando worker con DM AI OS...", DM_AI_OS_URL)
    try:
        reg_res = register_worker_with_dmaios(
            dmaios_url=DM_AI_OS_URL,
            worker_id=WORKER_ID,
            session_id=SESSION_ID,
            tunnel_url=tunnel_url,
            gpu_info=gpu,
            installed_models=discovered_model_ids,
        )
        print(f"   Estado de Registro: \033[1;32m{reg_res.get('status')}\033[0m")
        print(f"   Modelos registrados: {discovered_model_ids}")
    except Exception as e:
        print(f"\033[1;33m[AVISO] Registro HTTP falló ({e}). El worker seguirá intentando.\033[0m")

    # 13. Start Heartbeat Daemon
    log_step("💓", "Iniciando servicio de Heartbeat (cada 30s)...", "")
    start_heartbeat_thread(DM_AI_OS_URL, WORKER_ID, SESSION_ID, interval_sec=30)

    # 14. Summary Banner
    print("\n" + "=" * 65)
    print("🟢 \033[1;32mWORKER READY — COMPUTE PLANE OPERATIVO\033[0m")
    print(f"   Worker ID:         {WORKER_ID}")
    print(f"   Session ID:        {SESSION_ID}")
    print(f"   GPU:               {gpu['name']} ({gpu['vram_gb']} GB)")
    print(f"   ComfyUI URL:       {tunnel_url}")
    print(f"   Control URL:       {DM_AI_OS_URL}/connect")
    print(f"   Drive Mounted:     {'YES' if drive_mounted else 'NO'}")
    print(f"   Storage Roots:     {len(storage_roots)}")
    print(f"   Models Discovered: {discovered_model_ids}")
    print(f"   FLUX Status:       CONFIGURED / NOT YET READY (requires physical E2E)")
    print("=" * 65)
    print("⚡ Manteniendo conexión activa con DM AI OS...")
    print("   (Para detener el worker, detiene la ejecución de esta celda en Colab)\n")

    try:
        while True:
            time.sleep(10)
    except KeyboardInterrupt:
        print("\nWorker detenido.")


if __name__ == "__main__":
    run_bootstrap()
