"""
DM AI OS — Hardware Detector & Local Model Manager
===================================================
Auto-detects: CPU, RAM, GPU, VRAM, disk space.
Detects local AI runtimes: Ollama, Whisper, XTTS, Piper.
Recommends best model for the user's hardware.
"""

import os
import json
import logging
import platform
import subprocess
from typing import Any, Dict, List, Optional

log = logging.getLogger("hardware_detector")

# Model VRAM requirements in GB (approximate)
MODEL_VRAM_REQUIREMENTS = {
    "qwen2.5:0.5b":  0.5,
    "qwen2.5:1.5b":  1.5,
    "qwen2.5:7b":    5.0,
    "qwen2.5:14b":   10.0,
    "llama3.2:1b":   1.5,
    "llama3.2:3b":   3.0,
    "llama3.1:8b":   6.0,
    "deepseek-r1:7b": 5.0,
    "deepseek-r1:14b": 10.0,
    "mistral:7b":    5.0,
    "gemma2:2b":     2.0,
    "phi3:mini":     2.5,
}


def _run_cmd(args: List[str], timeout: int = 5) -> str:
    """Run subprocess, return stdout string or empty."""
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
        return result.stdout.strip()
    except Exception:
        return ""


def get_cpu_info() -> Dict[str, Any]:
    info = {
        "name": platform.processor() or "Unknown CPU",
        "cores_physical": None,
        "cores_logical": None,
    }
    try:
        import psutil
        info["cores_physical"] = psutil.cpu_count(logical=False)
        info["cores_logical"] = psutil.cpu_count(logical=True)
        info["freq_mhz"] = round(psutil.cpu_freq().current, 1) if psutil.cpu_freq() else None
    except ImportError:
        pass
    return info


def get_ram_info() -> Dict[str, Any]:
    try:
        import psutil
        mem = psutil.virtual_memory()
        return {
            "total_gb": round(mem.total / (1024**3), 1),
            "available_gb": round(mem.available / (1024**3), 1),
            "used_percent": mem.percent,
        }
    except ImportError:
        return {"total_gb": None, "available_gb": None, "used_percent": None}


def get_gpu_info() -> List[Dict[str, Any]]:
    gpus = []

    # Try nvidia-smi first
    nvidia_out = _run_cmd(["nvidia-smi", "--query-gpu=name,memory.total,memory.free,memory.used", "--format=csv,noheader,nounits"])
    if nvidia_out:
        for line in nvidia_out.splitlines():
            parts = [p.strip() for p in line.split(",")]
            if len(parts) >= 4:
                try:
                    gpus.append({
                        "name": parts[0],
                        "vram_total_mb": int(parts[1]),
                        "vram_free_mb": int(parts[2]),
                        "vram_used_mb": int(parts[3]),
                        "type": "nvidia",
                    })
                except ValueError:
                    pass
        return gpus

    # Try PyTorch
    try:
        import torch
        if torch.cuda.is_available():
            for i in range(torch.cuda.device_count()):
                props = torch.cuda.get_device_properties(i)
                total = props.total_memory
                free = torch.cuda.mem_get_info(i)[0]
                gpus.append({
                    "name": props.name,
                    "vram_total_mb": total // (1024**2),
                    "vram_free_mb": free // (1024**2),
                    "vram_used_mb": (total - free) // (1024**2),
                    "type": "cuda",
                })
    except ImportError:
        pass

    return gpus


def get_disk_info() -> Dict[str, Any]:
    try:
        import psutil
        disk = psutil.disk_usage(os.path.expanduser("~"))
        return {
            "total_gb": round(disk.total / (1024**3), 1),
            "free_gb": round(disk.free / (1024**3), 1),
            "used_percent": round(disk.percent, 1),
        }
    except ImportError:
        return {"total_gb": None, "free_gb": None, "used_percent": None}


def detect_local_runtimes() -> List[Dict[str, Any]]:
    """Detect installed local AI runtimes."""
    runtimes = []

    # Ollama
    ollama_version = _run_cmd(["ollama", "--version"])
    if not ollama_version:
        # Try common install paths
        for path in [r"C:\Users\%USERNAME%\AppData\Local\Programs\Ollama\ollama.exe", "/usr/local/bin/ollama"]:
            ollama_version = _run_cmd([os.path.expandvars(path), "--version"])
            if ollama_version:
                break
    runtimes.append({
        "name": "Ollama",
        "id": "ollama",
        "available": bool(ollama_version),
        "version": ollama_version or None,
        "url": "http://localhost:11434",
    })

    # Whisper (OpenAI)
    whisper_version = _run_cmd(["whisper", "--help"])
    runtimes.append({
        "name": "Whisper (Speech-to-Text)",
        "id": "whisper",
        "available": bool(whisper_version),
        "version": None,
    })

    # XTTS
    try:
        import TTS  # noqa
        runtimes.append({"name": "XTTS (TTS)", "id": "xtts", "available": True, "version": None})
    except ImportError:
        runtimes.append({"name": "XTTS (TTS)", "id": "xtts", "available": False, "version": None})

    # Piper
    piper_version = _run_cmd(["piper", "--version"])
    runtimes.append({
        "name": "Piper TTS",
        "id": "piper",
        "available": bool(piper_version),
        "version": piper_version or None,
    })

    return runtimes


def get_ollama_models() -> List[Dict[str, Any]]:
    """List models currently pulled in Ollama, with memory estimates."""
    import httpx
    try:
        import httpx as _httpx
        r = _httpx.get("http://localhost:11434/api/tags", timeout=5)
        if r.status_code == 200:
            models = r.json().get("models", [])
            result = []
            for m in models:
                name = m.get("name", "")
                size_bytes = m.get("size", 0)
                result.append({
                    "name": name,
                    "size_gb": round(size_bytes / (1024**3), 2) if size_bytes else None,
                    "modified": m.get("modified_at"),
                })
            return result
    except Exception:
        pass
    return []


def recommend_models(vram_free_gb: Optional[float], ram_gb: Optional[float]) -> List[str]:
    """Recommend models that fit in available VRAM/RAM."""
    recommended = []
    budget = vram_free_gb or (ram_gb * 0.6 if ram_gb else 4.0)  # use 60% of RAM if no GPU

    for model, req in sorted(MODEL_VRAM_REQUIREMENTS.items(), key=lambda x: -x[1]):
        if req <= budget:
            recommended.append(model)

    return recommended[:5]  # top 5


def get_full_hardware_report() -> Dict[str, Any]:
    """Complete hardware + runtime detection report."""
    cpu = get_cpu_info()
    ram = get_ram_info()
    gpus = get_gpu_info()
    disk = get_disk_info()
    runtimes = detect_local_runtimes()
    ollama_models = get_ollama_models()

    vram_free_gb = None
    if gpus:
        vram_free_gb = gpus[0].get("vram_free_mb", 0) / 1024

    recommendations = recommend_models(vram_free_gb, ram.get("total_gb"))

    return {
        "cpu": cpu,
        "ram": ram,
        "gpus": gpus,
        "disk": disk,
        "local_runtimes": runtimes,
        "ollama_models": ollama_models,
        "recommended_models": recommendations,
        "platform": platform.system(),
    }


# Module-level instance
hardware_detector = type("HardwareDetector", (), {
    "get_report": staticmethod(get_full_hardware_report),
    "get_ollama_models": staticmethod(get_ollama_models),
    "detect_runtimes": staticmethod(detect_local_runtimes),
    "recommend_models": staticmethod(recommend_models),
})()
