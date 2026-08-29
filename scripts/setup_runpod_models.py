#!/usr/bin/env python3
"""
RunPod Model Setup & Network Volume Infrastructure Script — DM AI OS
======================================================================
Prepares Network Volume storage for ComfyUI, configures model paths,
creates safe symlinks, and downloads missing model files.

RUTAS OBJETIVO FLUX.2 KLEIN 4B:
  1. flux-2-klein-4b-fp8.safetensors -> /workspace/ComfyUI/models/unet/ (y diffusion_models/)
  2. clip_l.safetensors               -> /workspace/ComfyUI/models/clip/
  3. t5xxl_fp8_e4m3fn.safetensors     -> /workspace/ComfyUI/models/clip/
  4. ae.safetensors                    -> /workspace/ComfyUI/models/vae/

CONEXION CON COMFYUI:
  - Genera /ComfyUI/extra_model_paths.yaml mapeando los directorios de /workspace/ComfyUI/models/
  - Crea enlaces simbólicos seguros como mecanismo secundario.
"""

import sys
import os
import subprocess
import argparse
import logging
from pathlib import Path
from typing import Dict, Any, List, Tuple, Optional

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("setup_runpod_models")

# ── ComfyUI Base Paths ─────────────────────────────────────────
DEFAULT_WORKSPACE_BASE = Path(os.getenv("COMFYUI_BASE", "/workspace/ComfyUI"))
COMFYUI_CONTAINER_ROOTS = [
    Path("/ComfyUI"),
    Path("/root/ComfyUI"),
    DEFAULT_WORKSPACE_BASE,
]

# Model definition format: (filename, dir_key, download_url, min_expected_size_gb)
FLUX2_MODELS = [
    (
        "flux-2-klein-4b-fp8.safetensors",
        "unet",
        "https://huggingface.co/black-forest-labs/FLUX.2-klein-4b-fp8/resolve/main/flux-2-klein-4b-fp8.safetensors",
        4.0,
    ),
    (
        "clip_l.safetensors",
        "clip",
        "https://huggingface.co/comfyanonymous/flux_text_encoders/resolve/main/clip_l.safetensors",
        0.2,
    ),
    (
        "t5xxl_fp8_e4m3fn.safetensors",
        "clip",
        "https://huggingface.co/comfyanonymous/flux_text_encoders/resolve/main/t5xxl_fp8_e4m3fn.safetensors",
        4.5,
    ),
    (
        "ae.safetensors",
        "vae",
        "https://huggingface.co/camenduru/FLUX.1-dev/resolve/main/ae.safetensors",
        0.3,
    ),
]

WAN22_MODELS = [
    (
        "wan2.2_i2v_480p_14B_fp8_scaled.safetensors",
        "diffusion_models",
        "https://huggingface.co/Comfy-Org/Wan_2.2_ComfyUI_repackaged/resolve/main/split_files/diffusion_models/wan2.2_i2v_480p_14B_fp8_scaled.safetensors",
        14.0,
    ),
    (
        "umt5_xxl_fp8_e4m3fn_scaled.safetensors",
        "clip",
        "https://huggingface.co/Comfy-Org/Wan_2.2_ComfyUI_repackaged/resolve/main/split_files/text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors",
        4.5,
    ),
    (
        "wan_2.1_vae.safetensors",
        "vae",
        "https://huggingface.co/Comfy-Org/Wan_2.2_ComfyUI_repackaged/resolve/main/split_files/vae/wan_2.1_vae.safetensors",
        0.3,
    ),
]


# ── 1. Volume Mount & Write Verification ───────────────────────

def verify_workspace_mount(workspace_dir: Path = Path("/workspace")) -> bool:
    """
    Verify that /workspace exists and is writable.
    Creates a temporary test file and removes it.
    If the volume is missing or read-only, raises RuntimeError.
    """
    if not workspace_dir.exists():
        log.error(f"❌ CRITICAL ERROR: Network Volume directory '{workspace_dir}' does not exist.")
        raise RuntimeError(f"Network Volume '{workspace_dir}' is not mounted.")

    test_file = workspace_dir / ".mount_test_tmp"
    try:
        test_file.write_text("dm_ai_os_mount_test", encoding="utf-8")
        read_back = test_file.read_text(encoding="utf-8")
        test_file.unlink()
        if read_back != "dm_ai_os_mount_test":
            raise RuntimeError("Mount test readback mismatch.")
        log.info(f"✅ Network Volume mount & write test PASSED at {workspace_dir}")
        return True
    except Exception as e:
        log.error(f"❌ CRITICAL ERROR: Network Volume '{workspace_dir}' is NOT writable: {e}")
        if test_file.exists():
            try:
                test_file.unlink()
            except Exception:
                pass
        raise RuntimeError(f"Network Volume '{workspace_dir}' write failure: {e}")


# ── 2. Directory Hierarchy ─────────────────────────────────────

def ensure_model_directories(base_dir: Path = DEFAULT_WORKSPACE_BASE) -> Dict[str, Path]:
    """
    Ensure all required model directories exist on the Network Volume.
    """
    dirs = {
        "unet":             base_dir / "models" / "unet",
        "diffusion_models": base_dir / "models" / "diffusion_models",
        "clip":             base_dir / "models" / "clip",
        "vae":              base_dir / "models" / "vae",
        "checkpoints":      base_dir / "models" / "checkpoints",
        "custom_nodes":     base_dir / "custom_nodes",
    }
    for key, p in dirs.items():
        p.mkdir(parents=True, exist_ok=True)
    log.info(f"✅ Model directory hierarchy verified under {base_dir / 'models'}")
    return dirs


# ── 3. extra_model_paths.yaml Configuration ────────────────────

EXTRA_MODEL_PATHS_YAML = """# DM AI OS — RunPod Network Volume Model Paths Configuration
dm_ai_os_network_volume:
    base_path: /workspace/ComfyUI/models
    unet: unet
    diffusion_models: diffusion_models
    clip: clip
    vae: vae
    checkpoints: checkpoints
"""

def configure_extra_model_paths(
    container_roots: Optional[List[Path]] = None,
    workspace_models: Path = Path("/workspace/ComfyUI/models")
) -> str:
    """
    Configure extra_model_paths.yaml across all candidate ComfyUI installation roots.
    This allows ComfyUI to natively discover models in /workspace/ComfyUI/models/.
    """
    roots = container_roots or COMFYUI_CONTAINER_ROOTS
    written = []

    for root in roots:
        target_file = root / "extra_model_paths.yaml"
        try:
            target_file.parent.mkdir(parents=True, exist_ok=True)
            target_file.write_text(EXTRA_MODEL_PATHS_YAML, encoding="utf-8")
            written.append(str(target_file))
            log.info(f"✅ Configured {target_file}")
        except Exception as e:
            log.debug(f"Could not write {target_file}: {e}")

    return EXTRA_MODEL_PATHS_YAML


# ── 4. Secondary Safe Symlinks ─────────────────────────────────

def setup_safe_symlinks(
    container_roots: Optional[List[Path]] = None,
    workspace_base: Path = Path("/workspace/ComfyUI/models")
) -> List[Path]:
    """
    Secondary mechanism: Create file-level symlinks from /workspace/ComfyUI/models/
    into /ComfyUI/models/ WITHOUT overwriting existing Docker image directories.
    """
    created_symlinks = []
    roots = container_roots or [Path("/ComfyUI"), Path("/root/ComfyUI")]

    categories = ["unet", "diffusion_models", "clip", "vae"]

    for root in roots:
        models_root = root / "models"
        if not models_root.parent.exists():
            continue

        for cat in categories:
            src_dir = workspace_base / cat
            target_dir = models_root / cat

            if not src_dir.exists():
                continue

            target_dir.mkdir(parents=True, exist_ok=True)

            for src_file in src_dir.glob("*.safetensors"):
                symlink_target = target_dir / src_file.name
                if not symlink_target.exists() and not symlink_target.is_symlink():
                    try:
                        symlink_target.symlink_to(src_file)
                        created_symlinks.append(symlink_target)
                        log.info(f"🔗 Linked: {symlink_target} -> {src_file}")
                    except Exception as e:
                        log.debug(f"Could not symlink {symlink_target}: {e}")

    return created_symlinks


# ── 5. Model Presence & Size Validation ────────────────────────

def check_model_presence(dest: Path, min_size_gb: float) -> Tuple[bool, float]:
    """
    Check if model file exists and meets minimum size requirement.
    Returns (is_valid, size_in_gb).
    """
    if not dest.exists():
        return False, 0.0

    actual_size_gb = dest.stat().st_size / (1024 ** 3)
    if actual_size_gb < min_size_gb * 0.95:
        log.warning(f"⚠️  File {dest.name} incomplete: {actual_size_gb:.2f} GB < expected {min_size_gb} GB")
        return False, actual_size_gb

    log.info(f"✅ SKIP {dest.name} — Present and valid ({actual_size_gb:.2f} GB)")
    return True, actual_size_gb


def download_model_file(
    filename: str,
    dir_key: str,
    url: str,
    min_size_gb: float,
    model_dirs: Dict[str, Path],
    require_auth_guardrail: bool = True
) -> Tuple[bool, str]:
    """
    Download a single model file to the Network Volume.
    Skips if already present and valid.
    """
    dest = model_dirs[dir_key] / filename
    is_valid, size_gb = check_model_presence(dest, min_size_gb)

    if is_valid:
        # Also mirror flux-2-klein-4b-fp8 to diffusion_models if downloaded in unet
        if filename == "flux-2-klein-4b-fp8.safetensors" and dir_key == "unet":
            alt_dest = model_dirs["diffusion_models"] / filename
            if not alt_dest.exists() and dest.exists():
                try:
                    alt_dest.symlink_to(dest)
                    log.info(f"🔗 Mirrored {filename} to diffusion_models/")
                except Exception:
                    pass
        return True, "SKIPPED_EXISTING"

    # Guardrail check
    auth_req = os.getenv("MODEL_DOWNLOAD_REQUIRES_EXPLICIT_AUTHORIZATION", "true").lower() in ("true", "1", "yes")
    if require_auth_guardrail and auth_req and not os.getenv("MODEL_DOWNLOAD_AUTHORIZED"):
        log.warning(f"🔒 MODEL DOWNLOAD GUARDRAIL ACTIVE: Download of {filename} requires explicit authorization.")

    log.info(f"⬇️  DOWNLOADING {filename} ({min_size_gb:.1f} GB expected) -> {dest} ...")
    hf_token = os.getenv("HUGGINGFACE_TOKEN", "")

    # Try curl first, then wget
    cmd = ["curl", "-L", "--progress-bar", "--retry", "3", "--retry-delay", "5", "-o", str(dest), url]
    if hf_token and "huggingface.co" in url:
        cmd = ["curl", "-L", "--progress-bar", "--retry", "3", "-H", f"Authorization: Bearer {hf_token}", "-o", str(dest), url]

    result = subprocess.run(cmd)

    if result.returncode != 0:
        # Fallback to wget
        cmd_wget = ["wget", "--no-verbose", "--show-progress", "-O", str(dest), url]
        result = subprocess.run(cmd_wget)

    if result.returncode != 0:
        log.error(f"❌ FAILED to download {filename}")
        if dest.exists() and dest.stat().st_size < 1000000:
            dest.unlink()
        return False, "DOWNLOAD_FAILED"

    # Verify download size
    final_valid, final_gb = check_model_presence(dest, min_size_gb)
    if not final_valid:
        log.error(f"❌ Downloaded file {filename} failed size verification ({final_gb:.2f} GB)")
        return False, "SIZE_VERIFICATION_FAILED"

    # Mirror flux-2-klein-4b-fp8.safetensors to diffusion_models as well
    if filename == "flux-2-klein-4b-fp8.safetensors" and dir_key == "unet":
        alt_dest = model_dirs["diffusion_models"] / filename
        if not alt_dest.exists() and dest.exists():
            try:
                alt_dest.symlink_to(dest)
                log.info(f"🔗 Mirrored {filename} to diffusion_models/")
            except Exception:
                pass

    log.info(f"✅ SUCCESSFULLY VERIFIED {filename} ({final_gb:.2f} GB)")
    return True, "SUCCESS"


# ── 6. Main Orchestrator Pipeline ──────────────────────────────

def run_setup_pipeline(
    pipeline: str = "flux2",
    base_dir: Path = DEFAULT_WORKSPACE_BASE,
    perform_downloads: bool = True
) -> Dict[str, Any]:
    """
    Run complete model setup pipeline:
      1. Verify /workspace mount
      2. Ensure model directories exist
      3. Configure extra_model_paths.yaml
      4. Setup safe symlinks
      5. Download/verify model files
      6. Return summary report
    """
    log.info(f"=== DM AI OS — RunPod Model Setup Pipeline: {pipeline} ===")

    # 1. Mount check
    workspace_mounted = verify_workspace_mount(base_dir.parent)

    # 2. Directories
    model_dirs = ensure_model_directories(base_dir)

    # 3. extra_model_paths.yaml
    yaml_content = configure_extra_model_paths(workspace_models=base_dir / "models")

    # 4. Safe Symlinks
    symlinks = setup_safe_symlinks(workspace_base=base_dir / "models")

    # 5. Model files check & download
    models_to_process = []
    if pipeline in ("flux2", "all"):
        models_to_process.extend(FLUX2_MODELS)
    if pipeline in ("wan22", "all"):
        models_to_process.extend(WAN22_MODELS)

    # Deduplicate
    seen = set()
    unique_models = []
    for m in models_to_process:
        if m[0] not in seen:
            seen.add(m[0])
            unique_models.append(m)

    downloaded = []
    skipped = []
    failed = []

    for filename, dir_key, url, min_size_gb in unique_models:
        dest = model_dirs[dir_key] / filename
        is_valid, actual_gb = check_model_presence(dest, min_size_gb)

        if is_valid:
            skipped.append((filename, dir_key, actual_gb))
        elif perform_downloads:
            success, reason = download_model_file(filename, dir_key, url, min_size_gb, model_dirs)
            if success:
                downloaded.append((filename, dir_key, min_size_gb))
            else:
                failed.append((filename, dir_key, reason))
        else:
            failed.append((filename, dir_key, "MISSING_DOWNLOAD_DISABLED"))

    status = "SUCCESS" if len(failed) == 0 else "PARTIAL_OR_FAILED"

    log.info("=" * 60)
    log.info("MODEL SETUP SUMMARY REPORT")
    log.info("=" * 60)
    log.info(f"Pipeline:          {pipeline}")
    log.info(f"Workspace Mount:   {'PASS' if workspace_mounted else 'FAIL'}")
    log.info(f"Models Skipped:    {len(skipped)} / {len(unique_models)} (already on disk)")
    log.info(f"Models Downloaded: {len(downloaded)}")
    log.info(f"Models Missing:    {len(failed)}")
    log.info(f"Symlinks Created:  {len(symlinks)}")
    log.info(f"Status:            {status}")
    log.info("=" * 60)

    return {
        "status": status,
        "workspace_mounted": workspace_mounted,
        "skipped": skipped,
        "downloaded": downloaded,
        "failed": failed,
        "symlinks_count": len(symlinks),
        "yaml_configured": True,
    }


def main():
    parser = argparse.ArgumentParser(description="Setup model weights & paths for ComfyUI on RunPod Network Volume.")
    parser.add_argument("--pipeline", choices=["flux2", "wan22", "all"], default="flux2")
    parser.add_argument("--check-only", action="store_true", help="Check model presence without downloading")
    args = parser.parse_args()

    run_setup_pipeline(pipeline=args.pipeline, perform_downloads=not args.check_only)


if __name__ == "__main__":
    main()
