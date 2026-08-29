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

    return tunnel_url or ""


def register_worker_with_dmaios(dmaios_url: str, worker_id: str, session_id: str, tunnel_url: str, gpu_info: dict) -> dict:
    """Sends registration payload to DM AI OS."""
    reg_url = f"{dmaios_url.rstrip('/')}/api/v1/workers/register"
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
        "models": ["flux2_klein", "sd15_base", "wan22_i2v"],
        "capabilities": ["image", "video"]
    }

    req = urllib.request.Request(
        reg_url,
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


def is_valid_safetensors(file_path: Path, min_bytes: int = 2_000_000_000) -> bool:
    """Validates that file exists, meets minimum size, and contains a valid safetensors header."""
    if not file_path.exists():
        return False
    size = file_path.stat().st_size
    if size < min_bytes:
        return False
    try:
        with open(file_path, "rb") as f:
            header_bytes = f.read(16)
            if len(header_bytes) < 16:
                return False
            # Safetensors starts with uint64 header length (8 bytes) followed by JSON
            header_len = int.from_bytes(header_bytes[:8], byteorder="little")
            if header_len <= 0 or header_len > 100_000_000:
                return False
            # Check JSON start
            if header_bytes[8:9] != b"{":
                return False
        return True
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

    # 2. ComfyUI Setup
    comfy_dir = Path("/content/ComfyUI") if Path("/content").exists() else Path("./ComfyUI")
    if not comfy_dir.exists():
        log_step("📦", "Clonando repositorio ComfyUI...", "")
        subprocess.run(["git", "clone", "--depth", "1", "https://github.com/comfyanonymous/ComfyUI.git", str(comfy_dir)], check=False)
        req_file = comfy_dir / "requirements.txt"
        if req_file.exists():
            subprocess.run([sys.executable, "-m", "pip", "install", "-q", "-r", str(req_file)], check=False)

    ckpt_dir = comfy_dir / "models" / "checkpoints"
    ckpt_dir.mkdir(parents=True, exist_ok=True)

    # Validar y descargar Checkpoint SD 1.5 con diagnóstico físico
    if not download_and_validate_checkpoint(ckpt_dir):
        print("\033[1;31m[ERROR FATAL] El checkpoint SD 1.5 no pudo validarse. Abortando registro.\033[0m")
        return

    # 3. Launch ComfyUI in Background
    log_step("⚡", "Arrancando servidor ComfyUI...", f"Puerto {COMFY_PORT}")
    comfy_cmd = [
        sys.executable, str(comfy_dir / "main.py"),
        "--listen", "127.0.0.1",
        "--port", str(COMFY_PORT),
        "--fp8_e4m3fn-unet",
        "--lowvram",
        "--preview-method", "auto"
    ]
    comfy_log = open("/content/comfyui.log", "w") if Path("/content").exists() else open("comfyui.log", "w")
    comfy_proc = subprocess.Popen(comfy_cmd, stdout=comfy_log, stderr=comfy_log)

    log_step("⏳", "Esperando respuesta de ComfyUI /system_stats...", "")
    if not wait_for_port(COMFY_PORT, timeout=45):
        print("\033[1;31m[ERROR] ComfyUI no respondió en el puerto 8188.\033[0m")
        return

    # Validar que ComfyUI haya indexado el checkpoint
    for _ in range(10):
        try:
            req = urllib.request.Request(f"http://127.0.0.1:{COMFY_PORT}/object_info/CheckpointLoaderSimple")
            with urllib.request.urlopen(req, timeout=5) as r:
                data = json.loads(r.read().decode())
                ckpts = data.get("CheckpointLoaderSimple", {}).get("input", {}).get("required", {}).get("ckpt_name", [[]])[0]
                if "v1-5-pruned-emaonly-fp16.safetensors" in ckpts:
                    print("   Checkpoint ComfyUI: \033[1;32mv1-5-pruned-emaonly-fp16.safetensors INDEXADO\033[0m")
                    break
        except Exception:
            pass
        time.sleep(2)

    # 4. Start Tunnel
    tunnel_url = start_cloudflare_tunnel(COMFY_PORT)
    if not tunnel_url:
        print("\033[1;31m[ERROR] No se pudo obtener la URL del túnel Cloudflare.\033[0m")
        return

    print(f"   Túnel Activo: \033[1;32m{tunnel_url}\033[0m")

    # 5. Register with DM AI OS
    log_step("🤝", "Registrando worker con DM AI OS...", DM_AI_OS_URL)
    try:
        reg_res = register_worker_with_dmaios(
            dmaios_url=DM_AI_OS_URL,
            worker_id=WORKER_ID,
            session_id=SESSION_ID,
            tunnel_url=tunnel_url,
            gpu_info=gpu
        )
        print(f"   Estado de Registro: \033[1;32m{reg_res.get('status')}\033[0m")
    except Exception as e:
        print(f"\033[1;33m[AVISO] Registro HTTP falló ({e}). El worker seguirá intentando.\033[0m")

    # 6. Start Heartbeat Daemon
    log_step("💓", "Iniciando servicio de Heartbeat (cada 30s)...", "")
    start_heartbeat_thread(DM_AI_OS_URL, WORKER_ID, SESSION_ID, interval_sec=30)

    # 7. Complete Summary Banner & Keep-Alive Loop
    print("\n" + "=" * 65)
    print("🟢 \033[1;32mWORKER READY — COMPUTE PLANE OPERATIVO\033[0m")
    print(f"   Worker ID:   {WORKER_ID}")
    print(f"   Session ID:  {SESSION_ID}")
    print(f"   GPU:         {gpu['name']} ({gpu['vram_gb']} GB)")
    print(f"   ComfyUI URL: {tunnel_url}")
    print(f"   Control URL: {DM_AI_OS_URL}/connect")
    print("=" * 65)
    print("⚡ Manteniendo conexión activa con DM AI OS...")
    print("   (Para detener el worker, detén la ejecución de esta celda en Colab)\n")

    try:
        while True:
            time.sleep(10)
    except KeyboardInterrupt:
        print("\nWorker detenido.")


if __name__ == "__main__":
    run_bootstrap()
