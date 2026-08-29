"""
DM AI OS — Providers REST API Router
======================================
Exposes Settings > AI Providers via REST endpoints.
Used by the frontend for the AI Providers panel.
"""

import os
import json
import time
import uuid
import asyncio
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, UploadFile, File, Request
from fastapi.responses import JSONResponse, FileResponse
from pydantic import BaseModel

from src.providers.provider_manager import provider_manager
from src.providers.hardware_detector import get_full_hardware_report, get_ollama_models
from src.providers.provider_history import provider_history
from src.storage.storage_layer import storage

providers_router = APIRouter(prefix="/api/providers", tags=["providers"])
log = __import__("logging").getLogger("providers_router")

UPLOAD_DIR = Path("deployment") / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


# ── GET /api/providers ─────────────────────────────────────────

@providers_router.get("")
async def list_all_providers():
    """List all registered providers with metadata."""
    return provider_manager.list_providers()


# ── GET /api/providers/models ───────────────────────────────────

@providers_router.get("/models")
async def get_all_models():
    """List all available providers and their models (free/paid, local/cloud)."""
    models = await provider_manager.get_all_available_models()
    return models


# ── GET /api/providers/health ───────────────────────────────────

@providers_router.get("/health")
async def health_all_providers():
    """Run health check on all providers (with latency)."""
    results = await provider_manager.health_check_all()
    return results


# ── GET /api/providers/{provider_id}/health ─────────────────────

@providers_router.get("/{provider_id}/health")
async def health_one_provider(provider_id: str):
    """Run health check on a single provider (fresh, no cache)."""
    result = await provider_manager.health_check(provider_id, force=True)
    return result


# ── POST /api/providers/{provider_id}/login ──────────────────────

@providers_router.post("/{provider_id}/login")
async def login_provider(provider_id: str):
    """
    Trigger account login for a provider.
    For Higgsfield: opens browser OAuth via 'higgsfield auth login'.
    """
    result = await provider_manager.trigger_login(provider_id)
    return result


# ── POST /api/providers/{provider_id}/logout ─────────────────────

@providers_router.post("/{provider_id}/logout")
async def logout_provider(provider_id: str):
    """Log out / disconnect a provider account."""
    result = await provider_manager.logout(provider_id)
    return result


# ── POST /api/providers/higgsfield/switch-account ─────────────────
# Flujo completo: logout → login → polling del nuevo token

def _get_higgsfield_binary() -> Optional[str]:
    """Locate the higgsfield CLI binary."""
    candidates = [
        str(Path(os.getenv("APPDATA", "")) / "npm" / "higgsfield.cmd"),
        str(Path(os.getenv("APPDATA", "")) / "npm" / "higgsfield"),
        "higgsfield",
    ]
    for b in candidates:
        try:
            result = subprocess.run([b, "--help"], capture_output=True, timeout=3)
            if result.returncode in (0, 1):
                return b
        except Exception:
            continue
    return None


def _read_higgsfield_token() -> Optional[str]:
    """Read current token from CLI binary or ~/.higgsfield/auth.json"""
    binary = _get_higgsfield_binary()
    if binary:
        try:
            res = subprocess.run([binary, "auth", "token"], capture_output=True, text=True, timeout=3)
            token = (res.stdout or "").strip()
            if token and not token.startswith("Error") and len(token) > 8:
                return token
        except Exception:
            pass

    auth_file = Path.home() / ".higgsfield" / "auth.json"
    if not auth_file.exists():
        return None
    try:
        data = json.loads(auth_file.read_text(encoding="utf-8"))
        return data.get("token") or data.get("access_token") or data.get("id_token")
    except Exception:
        return None


def _read_higgsfield_account() -> Optional[str]:
    """Read current account email from ~/.higgsfield/auth.json"""
    auth_file = Path.home() / ".higgsfield" / "auth.json"
    if not auth_file.exists():
        return None
    try:
        data = json.loads(auth_file.read_text(encoding="utf-8"))
        return (
            data.get("email")
            or data.get("user", {}).get("email")
            or data.get("profile", {}).get("email")
        )
    except Exception:
        return None


# Global state for login polling
_login_state: Dict[str, Any] = {
    "provider": None,
    "started_at": 0,
    "old_token": None,
    "status": "idle",
    "oauth_url": None,
    "_proc": None,
}


def _run_higgsfield_login_bg(binary: str, state: dict):
    """Background thread: runs 'higgsfield auth login', captures OAuth URL from stdout."""
    try:
        proc = subprocess.Popen(
            [binary, "auth", "login"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        state["_proc"] = proc
        for line in proc.stdout:
            line = line.strip()
            log.info(f"[HF-Login] {line}")
            # Look specifically for the Clerk OAuth URL (not localhost callback)
            if "clerk.higgsfield.ai" in line or "authorize" in line.lower():
                import re
                m = re.search(r"https://\S+", line)
                if m:
                    state["oauth_url"] = m.group(0)
        proc.wait(timeout=300)
    except Exception as e:
        log.warning(f"[HF-Login] background thread error: {e}")


@providers_router.post("/higgsfield/switch-account")
async def higgsfield_switch_account():
    """
    Account switching:
    1. Clear auth.json & env vars
    2. Run 'higgsfield auth login' in background thread to capture OAuth URL
    3. Return OAuth URL for UI to display as clickable link
    4. Client polls /higgsfield/login-status until token appears
    """
    import threading
    global _login_state

    # Kill any previous login process
    old_proc = _login_state.get("_proc")
    if old_proc:
        try:
            old_proc.kill()
        except Exception:
            pass

    # Clear env vars
    for var in ["HIGGSFIELD_AUTH_TOKEN", "HIGGSFIELD_TOKEN", "HIGGSFIELD_API_KEY"]:
        os.environ.pop(var, None)

    old_token = _read_higgsfield_token()

    # Delete stale auth.json
    auth_file = Path.home() / ".higgsfield" / "auth.json"
    if auth_file.exists():
        try:
            auth_file.unlink()
        except Exception:
            pass

    # Reset state before launching thread
    _login_state.update({
        "provider": "higgsfield",
        "started_at": time.time(),
        "old_token": old_token,
        "status": "waiting",
        "oauth_url": None,
        "_proc": None,
    })

    # Start background thread to run CLI login and capture OAuth URL
    binary = _get_higgsfield_binary()
    if binary:
        t = threading.Thread(
            target=_run_higgsfield_login_bg,
            args=(binary, _login_state),
            daemon=True,
        )
        t.start()
        # Wait up to 4s for the OAuth URL to appear in thread output
        for _ in range(8):
            await asyncio.sleep(0.5)
            if _login_state.get("oauth_url"):
                break

    oauth_url = _login_state.get("oauth_url") or "https://cloud.higgsfield.ai"

    return {
        "status": "waiting",
        "login_url": oauth_url,
        "message": "Haz clic en el botón de abajo para iniciar sesión con Google.",
        "instructions": [
            "1. Haz clic en 'Abrir Login de Higgsfield' para abrir el navegador",
            "2. Elige tu cuenta de Gmail (3 días gratis por cuenta nueva)",
            "3. Esta pantalla se actualizará automáticamente al terminar",
        ],
    }


@providers_router.get("/higgsfield/login-status")
async def higgsfield_login_status():
    """
    Poll this endpoint to check if a new Higgsfield account was authenticated.
    Returns:
    - status: 'waiting' | 'success' | 'timeout' | 'idle'
    - oauth_url: current OAuth URL (updated each poll so UI can refresh button)
    - account: new account email if success
    """
    global _login_state

    oauth_url = _login_state.get("oauth_url") or "https://cloud.higgsfield.ai"

    if _login_state["status"] != "waiting":
        return {"status": _login_state["status"], "account": _read_higgsfield_account(), "oauth_url": oauth_url}

    elapsed = time.time() - _login_state["started_at"]

    # Timeout after 5 minutes
    if elapsed > 300:
        _login_state["status"] = "timeout"
        return {"status": "timeout", "message": "Tiempo de espera agotado. Intenta nuevamente.", "oauth_url": oauth_url}

    # Check if token appeared (new login completed)
    current_token = _read_higgsfield_token()
    old_token = _login_state.get("old_token")
    token_changed = current_token and current_token != old_token
    account = _read_higgsfield_account()

    if token_changed or (current_token and not old_token):
        _login_state["status"] = "success"
        # Also inject token into running adapter
        try:
            from src.providers.provider_manager import provider_manager
            adapter = provider_manager.get("higgsfield")
            if adapter and hasattr(adapter, "_adapter") and adapter._adapter:
                adapter._adapter._api_key_override = current_token
                adapter._adapter._token = current_token
        except Exception:
            pass
        return {
            "status": "success",
            "account": account or "Cuenta Higgsfield",
            "message": f"¡Sesión iniciada! Cuenta: {account or 'Higgsfield'}",
            "oauth_url": oauth_url,
        }

    return {
        "status": "waiting",
        "elapsed_seconds": int(elapsed),
        "message": "Esperando autenticación en el navegador..."
    }


# ── POST /api/providers/higgsfield/set-token ─────────────────────

class SetTokenRequest(BaseModel):
    token: str

@providers_router.post("/higgsfield/set-token")
async def higgsfield_set_token(req: SetTokenRequest):
    """
    Set Higgsfield Auth Token / API Key directly from UI.
    Saves to ~/.higgsfield/auth.json and updates runtime env vars & adapter.
    """
    token = req.token.strip()
    if not token:
        raise HTTPException(status_code=400, detail="Token o API Key no puede estar vacía.")

    os.environ["HIGGSFIELD_AUTH_TOKEN"] = token
    os.environ["HIGGSFIELD_TOKEN"] = token
    os.environ["HIGGSFIELD_API_KEY"] = token

    auth_file = Path.home() / ".higgsfield" / "auth.json"
    auth_file.parent.mkdir(parents=True, exist_ok=True)
    auth_data = {
        "access_token": token,
        "token": token,
        "type": "bearer",
        "saved_at": time.time()
    }
    auth_file.write_text(json.dumps(auth_data, indent=2), encoding="utf-8")

    # Force re-check adapter health safely
    adapter = provider_manager.get("higgsfield")
    if adapter:
        # Set token on inner adapter if it exists
        if hasattr(adapter, "_adapter") and adapter._adapter:
            adapter._adapter._api_key_override = token
            adapter._adapter._token = token
        if hasattr(adapter, "auth_token"):
            adapter.auth_token = token
        try:
            await provider_manager.health_check("higgsfield", force=True)
        except Exception as err:
            log.warning(f"Health check after set-token warning: {err}")

    return {
        "status": "success",
        "message": "¡Token de Higgsfield guardado correctamente! Ya puedes generar imágenes y videos.",
        "token_snippet": f"{token[:8]}..." if len(token) > 8 else "***"
    }


# ── POST /api/providers/route/chat ───────────────────────────────

class ChatRouteRequest(BaseModel):
    messages: List[Dict[str, str]]
    provider: str = "auto"
    model: Optional[str] = None
    image_url: Optional[str] = None
    reference_image_url: Optional[str] = None

@providers_router.post("/route/chat")
async def route_chat(req: ChatRouteRequest):
    """
    Route a chat request through the AI Router.
    Provider 'auto' → selects best available provider automatically.
    """
    t0 = time.perf_counter()
    try:
        ref_url = req.reference_image_url or req.image_url
        result = await provider_manager.route_chat(
            req.messages,
            preferred_provider=req.provider,
            **({"model": req.model} if req.model else {}),
            **({"image_url": ref_url} if ref_url else {})
        )
        elapsed = round((time.perf_counter() - t0) * 1000, 1)
        result["_routing_ms"] = elapsed
        return result
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))


# ── POST /api/providers/route/image ──────────────────────────────

class MediaRouteRequest(BaseModel):
    prompt: str
    provider: str = "auto"
    model: Optional[str] = None
    aspect_ratio: str = "1:1"
    count: int = 1
    image_url: Optional[str] = None
    reference_image_url: Optional[str] = None

@providers_router.post("/route/image")
async def route_image(req: MediaRouteRequest):
    """Route image generation through AI Router."""
    t0 = time.perf_counter()
    try:
        ref_url = req.reference_image_url or req.image_url
        result = await provider_manager.route_image(
            req.prompt,
            preferred_provider=req.provider,
            aspect_ratio=req.aspect_ratio,
            count=req.count,
            **({"model": req.model} if req.model else {}),
            **({"image_url": ref_url} if ref_url else {})
        )
        elapsed = round((time.perf_counter() - t0) * 1000, 1)
        result["_routing_ms"] = elapsed

        # Record to history
        provider_history.record(
            provider=result.get("_provider_used", req.provider),
            capability="image",
            prompt=req.prompt,
            model=result.get("model"),
            account=result.get("auth_source"),
            result_url=result.get("image_url"),
            duration_ms=elapsed,
            status="ok",
        )
        return result
    except Exception as e:
        provider_history.record(
            provider=req.provider, capability="image",
            prompt=req.prompt, status="error", error=str(e)
        )
        raise HTTPException(status_code=503, detail=str(e))


# ── POST /api/providers/route/video ──────────────────────────────

class VideoRouteRequest(BaseModel):
    prompt: str
    provider: str = "auto"
    model: Optional[str] = None
    image_url: Optional[str] = None
    duration: int = 5
    aspect_ratio: str = "16:9"

@providers_router.post("/route/video")
async def route_video(req: VideoRouteRequest):
    """Route video generation through AI Router."""
    t0 = time.perf_counter()
    try:
        result = await provider_manager.route_video(
            req.prompt,
            preferred_provider=req.provider,
            image_url=req.image_url,
            duration=req.duration,
            aspect_ratio=req.aspect_ratio,
            **({"model": req.model} if req.model else {})
        )
        elapsed = round((time.perf_counter() - t0) * 1000, 1)
        result["_routing_ms"] = elapsed

        provider_history.record(
            provider=result.get("_provider_used", req.provider),
            capability="video",
            prompt=req.prompt,
            model=result.get("model"),
            account=result.get("auth_source"),
            result_url=result.get("video_url"),
            duration_ms=elapsed,
            status="ok",
        )
        return result
    except Exception as e:
        provider_history.record(
            provider=req.provider, capability="video",
            prompt=req.prompt, status="error", error=str(e)
        )
        raise HTTPException(status_code=503, detail=str(e))


# ── GET /api/providers/hardware ──────────────────────────────────

@providers_router.get("/hardware")
async def get_hardware():
    """Hardware report: CPU, RAM, GPU, VRAM, disk, local models."""
    report = get_full_hardware_report()
    return report


# ── GET /api/providers/hardware/models ───────────────────────────

@providers_router.get("/hardware/models")
async def get_local_models():
    """List Ollama models currently available locally."""
    return {"models": get_ollama_models()}


# ── GET /api/providers/history ────────────────────────────────────

@providers_router.get("/history")
async def get_history(limit: int = 50):
    """Recent AI provider usage history."""
    return {
        "entries": provider_history.get_recent(limit),
        "stats": provider_history.get_stats(),
    }


# ── GET /api/providers/history/{provider_id} ──────────────────────

@providers_router.get("/history/{provider_id}")
async def get_provider_history(provider_id: str, limit: int = 20):
    """Usage history for a specific provider."""
    return {
        "provider_id": provider_id,
        "entries": provider_history.get_by_provider(provider_id, limit),
    }


# ── Media Upload Endpoints (Influencer / Image Reference) ─────────

@providers_router.post("/upload-media")
async def upload_media(file: UploadFile = File(...), request: Request = None):
    """Upload a reference image file (influencer photo, etc) for Image-to-Image / Higgsfield MCP."""
    try:
        suffix = Path(file.filename).suffix or ".jpg"
        filename = f"ref_{int(time.time())}_{uuid.uuid4().hex[:8]}{suffix}"
        dest_path = UPLOAD_DIR / filename
        content = await file.read()
        dest_path.write_bytes(content)

        # Build public HTTP URL
        base_url = str(request.base_url).rstrip("/") if request else "http://127.0.0.1:8000"
        public_url = f"{base_url}/api/providers/uploads/{filename}"

        return {
            "status": "ok",
            "filename": filename,
            "url": public_url,
            "media_type": file.content_type or "image/jpeg"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Upload failed: {e}")


@providers_router.get("/uploads/{filename}")
async def get_uploaded_media(filename: str):
    """Serve uploaded reference images and generated media artifacts."""
    file_path = UPLOAD_DIR / filename
    if not file_path.exists():
        file_path = storage.artifacts_dir / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Media file not found")
    return FileResponse(file_path)
