"""
DM AI OS — Provider Manager
============================
Central AI Provider Manager. ALL agents route through here.
Never access Claude, Gemini, Higgsfield, Ollama etc. directly.

Features:
- Provider registry with adapters
- AI Router: AUTO selects best available provider
- Automatic fallback when a provider fails (rate limit, 401, 429, 500, timeout)
- Free trial tracking per provider
- Account management (login/logout per provider)
"""

import os
import time
import json
import logging
import asyncio
import subprocess
from typing import Any, Dict, List, Optional, Tuple
from pathlib import Path
from enum import Enum

log = logging.getLogger("provider_manager")

_STATE_FILE = Path(os.getenv("APPDATA", Path.home())) / ".dm_ai_os" / "provider_state.json"


from .base_adapter import BaseProviderAdapter, ProviderStatus, ProviderCapability


# Concrete adapters: Higgsfield
# ─────────────────────────────────────────────────────────────

class HiggsfieldProviderAdapter(BaseProviderAdapter):

    id = "higgsfield"
    display_name = "Higgsfield AI"
    capabilities = [
        ProviderCapability.IMAGE,
        ProviderCapability.VIDEO,
        ProviderCapability.CHARACTER_MGMT,
        ProviderCapability.JOB_STATUS,
        ProviderCapability.ASSET_RETRIEVAL,
    ]
    is_local = False

    def __init__(self):
        from src.adapters.higgsfield_adapter import HiggsfieldAdapter
        self._adapter = HiggsfieldAdapter()

    def get_account_info(self) -> str:
        try:
            auth_file = Path.home() / ".higgsfield" / "auth.json"
            if auth_file.exists():
                data = json.loads(auth_file.read_text("utf-8"))
                return data.get("user", "Authenticated")
        except Exception:
            pass
        return "Unknown"

    async def health_check(self) -> Tuple[ProviderStatus, float, str]:
        import httpx
        try:
            token = self._adapter._get_token()
        except Exception:
            return (ProviderStatus.AUTH_EXPIRED, 0.0, self.get_account_info())

        t0 = time.monotonic()
        try:
            payload = {
                "jsonrpc": "2.0", "id": 1, "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "dm-ai-os", "version": "1.0"}
                }
            }
            async with httpx.AsyncClient(timeout=8.0) as client:
                r = await client.post(
                    self._adapter.mcp_url,
                    json=payload,
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Content-Type": "application/json",
                        "Accept": "application/json, text/event-stream"
                    }
                )
            latency = round((time.monotonic() - t0) * 1000, 1)
            if r.status_code == 200:
                return (ProviderStatus.AVAILABLE, latency, self.get_account_info())
            elif r.status_code in (401, 403):
                return (ProviderStatus.AUTH_EXPIRED, latency, self.get_account_info())
            else:
                return (ProviderStatus.UNAVAILABLE, latency, self.get_account_info())
        except Exception as e:
            latency = round((time.monotonic() - t0) * 1000, 1)
            log.warning(f"[ProviderManager] Higgsfield health check failed: {e}")
            return (ProviderStatus.UNAVAILABLE, latency, self.get_account_info())

    async def generate_image(self, prompt: str, **kwargs) -> Dict[str, Any]:
        res = await self._adapter.generate_image(prompt, **kwargs)
        url = res.get("image_url") or ""
        if url:
            res["choices"] = [{
                "message": {
                    "role": "assistant",
                    "content": f"🖼️ **Imagen generada por Higgsfield AI:**\n\n![Imagen]({url})\n\n[📥 Descargar Imagen]({url}) [🌐 Ver HD]({url})"
                }
            }]
        return res

    async def generate_video(self, prompt: str, **kwargs) -> Dict[str, Any]:
        res = await self._adapter.generate_video(prompt, **kwargs)
        url = res.get("video_url") or res.get("image_url") or ""
        ref = kwargs.get("image_url") or ""
        if url:
            label = "Video animado" if ref else "Video generado"
            res["choices"] = [{
                "message": {
                    "role": "assistant",
                    "content": f"🎬 **{label} por Higgsfield AI:**\n\n![Video]({url})\n\n[📥 Descargar Video]({url}) [🌐 Ver Resultado]({url})"
                }
            }]
        return res

    async def chat(self, messages: List[Dict], **kwargs) -> Dict[str, Any]:
        """When chat is called on Higgsfield adapter, generate image or video based on prompt."""
        prompt = messages[-1].get("content", "") if messages else "Genera una imagen"
        image_url = kwargs.pop("image_url", None)
        log.info(f"[HiggsfieldProviderAdapter] Routing chat prompt to image/video generation: '{prompt[:40]}...' ref={image_url!r}")

        is_video = any(w in prompt.lower() for w in ["video", "animacion", "animar", "movimiento", "clip", "anima", "mueve"])

        if is_video or image_url:
            # Image-to-video: if reference provided, animate it; otherwise text-to-video
            res = await self.generate_video(prompt=prompt, image_url=image_url, **kwargs)
            url = res.get("video_url") or res.get("image_url") or ""
            return {
                "choices": [{
                    "message": {
                        "role": "assistant",
                        "content": f"🎬 **Video generado por Higgsfield AI:**\n\n![Video]({url})\n\n[📥 Descargar Video]({url}) [🌐 Ver Resultado]({url})"
                    }
                }],
                "result": res,
                "video_url": url,
                "_provider_used": "higgsfield"
            }
        else:
            res = await self.generate_image(prompt=prompt, image_url=image_url, **kwargs)
            url = res.get("image_url") or ""
            return {
                "choices": [{
                    "message": {
                        "role": "assistant",
                        "content": f"🖼️ **Imagen generada por Higgsfield AI:**\n\n![Imagen]({url})\n\n[📥 Descargar Imagen]({url}) [🌐 Ver HD]({url})"
                    }
                }],
                "result": res,
                "image_url": url,
                "_provider_used": "higgsfield"
            }

    async def trigger_login(self) -> Dict[str, Any]:
        """Run 'higgsfield auth login' to open browser OAuth flow."""
        binary_candidates = [
            str(Path(os.getenv("APPDATA", "")) / "npm" / "higgsfield.cmd"),
            "higgsfield",
        ]
        binary = None
        for b in binary_candidates:
            try:
                result = subprocess.run([b, "--help"], capture_output=True, timeout=3)
                if result.returncode in (0, 1):
                    binary = b
                    break
            except Exception:
                continue

        if not binary:
            return {"status": "error", "message": "higgsfield CLI not found. Install with: npm install -g @higgsfield-ai/higgsfield"}

        try:
            # Launch login in background (opens browser)
            subprocess.Popen([binary, "auth", "login"])
            return {
                "status": "pending",
                "message": "Higgsfield login opened in browser. Complete authentication there, then click 'Test Connection'."
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}

    async def logout(self) -> Dict[str, Any]:
        binary_candidates = [
            str(Path(os.getenv("APPDATA", "")) / "npm" / "higgsfield.cmd"),
            "higgsfield",
        ]
        for b in binary_candidates:
            try:
                result = subprocess.run([b, "auth", "logout"], capture_output=True, timeout=5)
                return {"status": "ok", "message": "Logged out from Higgsfield."}
            except Exception:
                continue
        return {"status": "error", "message": "higgsfield CLI not found"}

    # ── Character Management ─────────────────────────────────

    async def list_characters(self) -> list:
        """Lista personajes entrenados (Soul/Soul 2) de la cuenta Higgsfield."""
        return await self._adapter.list_characters()

    async def get_character(self, character_id: str) -> Dict[str, Any]:
        """Detalles de un personaje entrenado por su ID."""
        return await self._adapter.get_character(character_id)

    async def check_job_status(self, job_id: str) -> Dict[str, Any]:
        """Estado real de un job asíncrono en Higgsfield MCP."""
        return await self._adapter.check_job_status(job_id)

    async def get_result(
        self, job_id: str, output_path: Optional[str] = None
    ) -> Dict[str, Any]:
        """Descarga el asset final de un job completado."""
        return await self._adapter.get_result(job_id, output_path)

    def get_project_profile(self) -> Dict[str, Any]:
        """Perfil del proyecto activo (Valeria Montesano Digital)."""
        return self._adapter.get_project_profile()


# ─────────────────────────────────────────────────────────────
# Concrete adapters: Ollama (local)
# ─────────────────────────────────────────────────────────────

class OllamaProviderAdapter(BaseProviderAdapter):
    id = "ollama"
    display_name = "Ollama (Local)"
    capabilities = [ProviderCapability.CHAT, ProviderCapability.CODE, ProviderCapability.LOCAL]
    is_local = True

    def __init__(self, base_url: str = "http://localhost:11434"):
        self.base_url = base_url.rstrip("/")

    def get_account_info(self) -> str:
        return "Local"

    async def health_check(self) -> Tuple[ProviderStatus, float, str]:
        import httpx
        t0 = time.monotonic()
        try:
            async with httpx.AsyncClient(timeout=4.0) as client:
                r = await client.get(f"{self.base_url}/api/tags")
            latency = round((time.monotonic() - t0) * 1000, 1)
            if r.status_code == 200:
                models = r.json().get("models", [])
                account = f"{len(models)} models"
                return (ProviderStatus.AVAILABLE, latency, account)
            return (ProviderStatus.UNAVAILABLE, latency, "No response")
        except Exception:
            latency = round((time.monotonic() - t0) * 1000, 1)
            return (ProviderStatus.UNAVAILABLE, latency, "Not running")

    async def chat(self, messages: List[Dict], model: str = "qwen2.5:1.5b", **kwargs) -> Dict[str, Any]:
        import httpx
        import os
        num_ctx = kwargs.get("num_ctx") or int(os.getenv("OLLAMA_NUM_CTX", "32768"))
        timeout_sec = kwargs.get("timeout") or float(os.getenv("OLLAMA_TIMEOUT", "120.0"))
        payload = {
            "model": model,
            "messages": messages,
            "stream": False,
            "options": {
                "num_ctx": num_ctx
            }
        }
        async with httpx.AsyncClient(timeout=timeout_sec) as client:
            r = await client.post(f"{self.base_url}/api/chat", json=payload)
        r.raise_for_status()
        return r.json()

    async def get_models(self) -> List[Dict[str, Any]]:
        import httpx
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                r = await client.get(f"{self.base_url}/api/tags")
            if r.status_code != 200:
                return []
            models = []
            for m in r.json().get("models", []):
                name = m.get("name", "")
                if name:
                    models.append({
                        "id": name,
                        "name": name,
                        "free": True,
                        "local": True,
                        "status": "available"
                    })
            return models
        except Exception:
            return []


# ─────────────────────────────────────────────────────────────
# Stub adapters for cloud providers (placeholders for future integration)
# ─────────────────────────────────────────────────────────────

class _CloudStubAdapter(BaseProviderAdapter):
    """Placeholder for cloud provider — shows as configurable in Settings."""
    capabilities = [ProviderCapability.CHAT, ProviderCapability.CODE]
    is_local = False

    def __init__(self, env_key: str):
        self._env_key = env_key

    def get_account_info(self) -> str:
        key = os.getenv(self._env_key, "")
        if key:
            return f"API Key: {key[:8]}..."
        return "Not configured"

    async def health_check(self) -> Tuple[ProviderStatus, float, str]:
        key = os.getenv(self._env_key, "")
        if not key:
            return (ProviderStatus.AUTH_EXPIRED, 0.0, "No API key")
        return (ProviderStatus.UNKNOWN, 0.0, self.get_account_info())

    async def trigger_login(self) -> Dict[str, Any]:
        return {
            "status": "env_required",
            "message": f"Set environment variable {self._env_key} with your API key.",
            "env_var": self._env_key
        }

    async def chat(self, messages: List[Dict], **kwargs) -> Dict[str, Any]:
        key = os.getenv(self._env_key, "")
        if not key:
            raise RuntimeError(f"No API key configured for {self.display_name} ({self._env_key}). Auto-fallback triggered.")
        
        # If API key is set, delegate to OpenAI-compatible endpoint
        import httpx
        payload = {
            "model": kwargs.get("model", "gpt-4o"),
            "messages": messages
        }
        async with httpx.AsyncClient(timeout=60.0) as client:
            r = await client.post("https://api.openai.com/v1/chat/completions", json=payload, headers={"Authorization": f"Bearer {key}"})
        r.raise_for_status()
        return r.json()


class ClaudeProviderAdapter(_CloudStubAdapter):
    id = "claude"
    display_name = "Claude (Anthropic)"
    def __init__(self):
        super().__init__("ANTHROPIC_API_KEY")

class GeminiProviderAdapter(_CloudStubAdapter):
    id = "gemini"
    display_name = "Gemini (Google)"
    def __init__(self):
        super().__init__("GEMINI_API_KEY")

class OpenAIProviderAdapter(_CloudStubAdapter):
    id = "openai"
    display_name = "GPT (OpenAI)"
    def __init__(self):
        super().__init__("OPENAI_API_KEY")

class GrokProviderAdapter(_CloudStubAdapter):
    id = "grok"
    display_name = "Grok (xAI)"
    def __init__(self):
        super().__init__("XAI_API_KEY")

class DeepSeekProviderAdapter(_CloudStubAdapter):
    id = "deepseek"
    display_name = "DeepSeek Local"
    is_local = True
    def __init__(self):
        super().__init__("DEEPSEEK_API_KEY")

class QwenProviderAdapter(_CloudStubAdapter):
    id = "qwen"
    display_name = "Qwen Local"
    is_local = True
    def __init__(self):
        super().__init__("QWEN_API_KEY")


# ─────────────────────────────────────────────────────────────
# Provider Manager — singleton
# ─────────────────────────────────────────────────────────────

# Fallback error codes that trigger auto-routing to next provider
FALLBACK_TRIGGERS = {
    "rate_limit", "no_credits", "out of credits", "credits", "trial_expired",
    "auth_expired", "expired", "timeout", "500", "429", "401", "403", "invalid_grant"
}

# Priority order for AUTO routing (chat capability)
AUTO_CHAT_PRIORITY = ["ollama", "openrouter", "nvidia", "claude", "gemini", "openai", "grok", "deepseek", "qwen"]
# Priority order for image/video AUTO routing (Prioritizes ComfyUI Google Colab T4 when READY)
AUTO_MEDIA_PRIORITY = ["comfyui", "higgsfield", "nvidia", "runpod", "runpod_video"]


class ProviderManager:
    """
    Central registry and router for all AI providers.
    All agents must use this — never import adapters directly.
    """

    def __init__(self):
        self._providers: Dict[str, BaseProviderAdapter] = {}
        self._health_cache: Dict[str, Tuple[ProviderStatus, float, str, float]] = {}
        self._cache_ttl = 60.0  # seconds
        self._state: Dict[str, Any] = self._load_state()
        self._register_defaults()

    def _register_defaults(self):
        # ComfyUI Remote Provider (Google Colab Tesla T4)
        try:
            from .comfyui_provider import ComfyUIProviderAdapter
            self.register(ComfyUIProviderAdapter())
        except Exception as e:
            log.warning(f"[ProviderManager] ComfyUI registration skipped: {e}")

        # Media providers
        try:
            self.register(HiggsfieldProviderAdapter())
        except Exception as e:
            log.warning(f"[ProviderManager] Higgsfield registration skipped: {e}")

        try:
            from .nvidia_provider import NVIDIAImageProviderAdapter
            self.register(NVIDIAImageProviderAdapter())
        except Exception as e:
            log.warning(f"[ProviderManager] NVIDIA registration skipped: {e}")

        try:
            from .openrouter_provider import OpenRouterProviderAdapter
            self.register(OpenRouterProviderAdapter())
        except Exception as e:
            log.warning(f"[ProviderManager] OpenRouter registration skipped: {e}")

        # Local providers
        self.register(OllamaProviderAdapter())

        # Antigravity Remote Bridge Provider (v1.5.2)
        try:
            from src.integrations.antigravity.provider_adapter import AntigravityProviderAdapter
            self.register(AntigravityProviderAdapter())
        except Exception as e:
            log.warning(f"[ProviderManager] Antigravity registration skipped: {e}")

        # Cloud stub providers
        for cls in [ClaudeProviderAdapter, GeminiProviderAdapter, OpenAIProviderAdapter,
                    GrokProviderAdapter, DeepSeekProviderAdapter, QwenProviderAdapter]:
            try:
                self.register(cls())
            except Exception as e:
                log.warning(f"[ProviderManager] {cls.__name__} registration skipped: {e}")


    def register(self, adapter: BaseProviderAdapter):
        self._providers[adapter.id] = adapter
        log.info(f"[ProviderManager] Registered provider: {adapter.display_name} ({adapter.id})")

    def get(self, provider_id: str) -> Optional[BaseProviderAdapter]:
        if provider_id == "runpod" and "runpod" not in self._providers:
            try:
                from .runpod_provider import RunPodImageProviderAdapter
                self.register(RunPodImageProviderAdapter())
            except Exception:
                pass
        if provider_id == "runpod_video" and "runpod_video" not in self._providers:
            try:
                from .runpod_video_provider import RunPodVideoProviderAdapter
                self.register(RunPodVideoProviderAdapter())
            except Exception:
                pass
        return self._providers.get(provider_id)

    def list_providers(self) -> List[Dict[str, Any]]:
        result = []
        for pid, adapter in self._providers.items():
            state = self._state.get(pid, {})
            result.append({
                "id": pid,
                "name": adapter.display_name,
                "is_local": adapter.is_local,
                "capabilities": [c.value for c in adapter.capabilities],
                "account": adapter.get_account_info(),
                "trial_expires": state.get("trial_expires"),
                "auth_date": state.get("auth_date"),
            })
        return result

    async def get_all_available_models(self) -> List[Dict[str, Any]]:
        """
        Query all registered providers and return structured provider & model list.
        """
        results = [
            {
                "provider_id": "auto",
                "provider_name": "✨ Auto (Recomendado)",
                "is_local": False,
                "models": [{
                    "id": "auto",
                    "name": "Auto (Mejor Proveedor Disponible)",
                    "free": True,
                    "local": False,
                    "status": "available"
                }]
            }
        ]

        # Standard static fallback model maps for cloud providers
        static_models_map = {
            "claude": [
                {"id": "claude-3-5-sonnet-20241022", "name": "Claude 3.5 Sonnet", "free": False, "local": False, "status": "available"},
                {"id": "claude-3-5-haiku-20241022", "name": "Claude 3.5 Haiku", "free": False, "local": False, "status": "available"}
            ],
            "gemini": [
                {"id": "gemini-1.5-flash", "name": "Gemini 1.5 Flash", "free": True, "local": False, "status": "available"},
                {"id": "gemini-1.5-pro", "name": "Gemini 1.5 Pro", "free": False, "local": False, "status": "available"}
            ],
            "openai": [
                {"id": "gpt-4o", "name": "GPT-4o", "free": False, "local": False, "status": "available"},
                {"id": "gpt-4o-mini", "name": "GPT-4o Mini", "free": False, "local": False, "status": "available"}
            ],
            "grok": [
                {"id": "grok-beta", "name": "Grok Beta", "free": False, "local": False, "status": "available"},
                {"id": "grok-2-vision-1212", "name": "Grok 2 Vision", "free": False, "local": False, "status": "available"}
            ],
            "deepseek": [
                {"id": "deepseek-chat", "name": "DeepSeek V3", "free": False, "local": False, "status": "available"},
                {"id": "deepseek-reasoner", "name": "DeepSeek R1", "free": False, "local": False, "status": "available"}
            ],
            "qwen": [
                {"id": "qwen-max", "name": "Qwen Max", "free": False, "local": False, "status": "available"},
                {"id": "qwen-plus", "name": "Qwen Plus", "free": False, "local": False, "status": "available"}
            ],
            "higgsfield": [
                {"id": "higgsfield-image", "name": "Higgsfield Image (Soul 2)", "free": True, "local": False, "status": "available"},
                {"id": "higgsfield-video", "name": "Higgsfield Video (Animate)", "free": True, "local": False, "status": "available"}
            ],
            "comfyui": [
                {"id": "face_swap", "name": "🎭 Face Swap / Transferencia de Rostro [INSTANTÁNEO]", "free": True, "local": False, "status": "available"},
                {"id": "flux1_schnell", "name": "⚡ FLUX.1 Schnell (Ultra-Fotorealista HD) [TOP]", "free": True, "local": False, "status": "available"},
                {"id": "flux1_kontext", "name": "🎨 FLUX.1 Kontext (Edición In-Context y Consistencia)", "free": True, "local": False, "status": "available"},
                {"id": "qwen25_vl", "name": "👁️ Qwen2.5-VL Multimodal (Análisis Visual y Comprensión)", "free": True, "local": False, "status": "available"},
                {"id": "sdxl_base", "name": "📸 SDXL Juggernaut v9 (Selfie iPhone) [TOP]", "free": True, "local": False, "status": "available"},
                {"id": "wan22_i2v", "name": "🎬 Wan 2.1 Video (Animación Cinemática I2V)", "free": True, "local": False, "status": "available"},
                {"id": "ltx_video", "name": "🎥 LTX-Video 0.9.5 (Generación de Video Rápido)", "free": True, "local": False, "status": "available"},
                {"id": "f5_tts", "name": "🎙️ F5-TTS (Clonación de Voz de Valeria)", "free": True, "local": False, "status": "available"},
                {"id": "sd15_base", "name": "🖼️ SD 1.5 Base (Sin Censura)", "free": True, "local": False, "status": "available"}
            ]


        }

        for pid, adapter in self._providers.items():
            models = []
            if hasattr(adapter, "get_models"):
                try:
                    models = await adapter.get_models()
                except Exception as e:
                    log.warning(f"[ProviderManager] Error getting models for {pid}: {e}")

            if not models and pid in static_models_map:
                models = static_models_map[pid]

            if not models:
                # Default generic entry if no models returned
                models = [{
                    "id": f"{pid}-default",
                    "name": f"{adapter.display_name} Standard",
                    "free": adapter.is_local,
                    "local": adapter.is_local,
                    "status": "available"
                }]

            results.append({
                "provider_id": pid,
                "provider_name": adapter.display_name,
                "is_local": adapter.is_local,
                "account": adapter.get_account_info(),
                "models": models
            })

        return results

    async def health_check(self, provider_id: str, force: bool = False) -> Dict[str, Any]:
        """Return cached or fresh health check result for a provider."""
        now = time.monotonic()
        cached = self._health_cache.get(provider_id)
        if cached and not force and (now - cached[3]) < self._cache_ttl:
            status, latency, account, _ = cached
        else:
            adapter = self._providers.get(provider_id)
            if not adapter:
                return {"status": "unknown", "latency_ms": 0, "account": "N/A"}
            status, latency, account = await adapter.health_check()
            self._health_cache[provider_id] = (status, latency, account, now)

        return {
            "provider_id": provider_id,
            "status": status.value,
            "latency_ms": latency,
            "account": account
        }

    async def health_check_all(self) -> List[Dict[str, Any]]:
        tasks = [self.health_check(pid, force=True) for pid in self._providers]
        return await asyncio.gather(*tasks)

    async def trigger_login(self, provider_id: str) -> Dict[str, Any]:
        adapter = self._providers.get(provider_id)
        if not adapter:
            return {"status": "error", "message": f"Provider '{provider_id}' not found"}
        result = await adapter.trigger_login()
        if result.get("status") in ("ok", "pending"):
            self._update_state(provider_id, {"auth_date": time.time()})
        return result

    async def logout(self, provider_id: str) -> Dict[str, Any]:
        adapter = self._providers.get(provider_id)
        if not adapter:
            return {"status": "error", "message": f"Provider '{provider_id}' not found"}
        result = await adapter.logout()
        # Invalidate cache
        self._health_cache.pop(provider_id, None)
        return result

    # ── AI Router ──────────────────────────────────────────────

    async def route_chat(
        self,
        messages: List[Dict],
        preferred_provider: str = "auto",
        **kwargs
    ) -> Dict[str, Any]:
        """
        Route a chat request through AUTO or specific provider.
        STRICT ENFORCEMENT: If preferred_provider != 'auto', NO fallback occurs on failure.
        """
        prompt = messages[-1].get("content", "") if messages else ""
        prompt_low = prompt.lower().strip()
        image_url = kwargs.get("image_url")
        request_type = (kwargs.get("request_type") or kwargs.get("mode") or kwargs.get("intent") or "").lower()

        # SAFE ROUTING (False-Positive Prevention):
        # Generic conversational words ("modelo", "crea", "genera", "generar", "mujer", "chica", "gym", "outfit")
        # are explicitly excluded from triggering image routing on CHAT requests (e.g., "¿Qué modelo utilizas?").
        # Only explicit request_type metadata or unambiguous visual creation phrases will trigger route_image().
        if request_type == "image":
            is_image = True
            is_video = False
        elif request_type == "video":
            is_image = False
            is_video = True
        else:
            explicit_image_phrases = [
                "crea una imagen", "crear una imagen", "genera una imagen", "generar una imagen",
                "crea un dibujo", "crear un dibujo", "genera un dibujo", "generar un dibujo",
                "crea una foto", "crear una foto", "genera una foto", "generar una foto",
                "crea un retrato", "crear un retrato", "genera un retrato", "generar un retrato",
                "dibuja una", "dibuja un", "generar imagen", "crear imagen",
                "generate an image", "create an image", "draw an image", "make an image",
                "generate a picture", "create a picture", "draw a picture", "make a picture",
                "generate a photo", "create a photo", "draw a photo", "make a photo"
            ]
            explicit_video_phrases = [
                "crea un video", "crear un video", "genera un video", "generar un video",
                "crea una animacion", "crear una animacion", "genera una animacion", "generar una animacion",
                "generate a video", "create a video", "make a video", "animate this", "animate image"
            ]

            is_image = any(phrase in prompt_low for phrase in explicit_image_phrases)
            is_video = any(phrase in prompt_low for phrase in explicit_video_phrases)

        # Image-to-video: reference image + explicit video prompt → animate it
        if image_url and not is_image and is_video:
            return await self.route_video(prompt=prompt, preferred_provider="higgsfield", **kwargs)

        if preferred_provider in ("higgsfield", "comfyui") or (preferred_provider == "auto" and (is_video or is_image)):
            if is_video:
                return await self.route_video(prompt=prompt, preferred_provider=preferred_provider, **kwargs)
            else:
                return await self.route_image(prompt=prompt, preferred_provider=preferred_provider, **kwargs)

        # ── EXPLICIT PROVIDER SELECTION (NO FALLBACK) ────────────
        if preferred_provider and preferred_provider != "auto":
            adapter = self._providers.get(preferred_provider)
            if not adapter:
                raise RuntimeError(f"Provider '{preferred_provider}' is not registered or supported in DM AI OS.")
            if not hasattr(adapter, "chat"):
                raise RuntimeError(f"Provider '{preferred_provider}' does not support chat capability.")

            log.info(f"[ProviderManager] Executing explicit chat routing for provider '{preferred_provider}' model={kwargs.get('model')!r}")
            # Direct invocation without fallback wrapping
            res = await adapter.chat(messages=messages, **kwargs)
            if isinstance(res, dict):
                res["_provider_used"] = preferred_provider
            return res

        # ── AUTO ROUTING (WITH FALLBACK) ──────────────────────────
        priority = AUTO_CHAT_PRIORITY
        try:
            return await self._route_with_fallback("chat", priority, messages=messages, **kwargs)
        except Exception as err:
            log.warning(f"[ProviderManager] All provider adapters failed for chat in AUTO mode ({err}). Delegating to BrainPipeline...")
            from src.api.brain_pipeline import brain_pipeline
            bp_res = await brain_pipeline.process(user_prompt=prompt, user_id="daniel")
            return {
                "choices": [{
                    "message": {
                        "role": "assistant",
                        "content": bp_res.get("response", bp_res.get("result", "Respuesta procesada por DM AI OS."))
                    }
                }],
                "result": bp_res,
                "_provider_used": "dm_brain_pipeline"
            }

    async def route_image(
        self,
        prompt: str,
        preferred_provider: str = "auto",
        **kwargs
    ) -> Dict[str, Any]:
        """Route image generation with auto-fallback or explicit execution."""
        if preferred_provider and preferred_provider != "auto":
            adapter = self._providers.get(preferred_provider)
            if not adapter or not hasattr(adapter, "generate_image"):
                raise RuntimeError(f"Provider '{preferred_provider}' does not support image generation.")
            res = await adapter.generate_image(prompt=prompt, **kwargs)
            res["_provider_used"] = preferred_provider
            return res

        priority = AUTO_MEDIA_PRIORITY
        return await self._route_with_fallback("generate_image", priority, prompt=prompt, **kwargs)

    async def route_video(
        self,
        prompt: str,
        preferred_provider: str = "auto",
        **kwargs
    ) -> Dict[str, Any]:
        """Route video generation with auto-fallback or explicit execution."""
        if preferred_provider and preferred_provider != "auto":
            adapter = self._providers.get(preferred_provider)
            if not adapter or not hasattr(adapter, "generate_video"):
                raise RuntimeError(f"Provider '{preferred_provider}' does not support video generation.")
            res = await adapter.generate_video(prompt=prompt, **kwargs)
            res["_provider_used"] = preferred_provider
            return res

        priority = AUTO_MEDIA_PRIORITY
        return await self._route_with_fallback("generate_video", priority, prompt=prompt, **kwargs)

    async def _route_with_fallback(
        self,
        capability: str,
        priority: List[str],
        **kwargs
    ) -> Dict[str, Any]:
        """Try providers in priority order; auto-fallback on FALLBACK_TRIGGERS."""
        errors = []
        for provider_id in priority:
            adapter = self._providers.get(provider_id)
            if not adapter:
                continue
            if not hasattr(adapter, capability):
                continue
            if not adapter.is_configured():
                log.info(
                    f"[Router] Skipping {provider_id}: credentials not configured"
                )
                continue

            try:
                method = getattr(adapter, capability)
                result = await method(**kwargs)
                result["_provider_used"] = provider_id
                log.info(f"[ProviderManager] '{capability}' handled by '{provider_id}'")
                return result
            except Exception as e:
                err_str = str(e).lower()
                is_fallback = True  # Always fallback during AUTO routing
                log.warning(f"[ProviderManager] Provider '{provider_id}' failed for '{capability}': {e}")
                errors.append({"provider": provider_id, "error": str(e), "fallback": is_fallback})

        raise RuntimeError(
            f"All providers failed for '{capability}': {errors}"
        )







        # Local providers
        self.register(OllamaProviderAdapter())

        # Cloud stub providers
        for cls in [ClaudeProviderAdapter, GeminiProviderAdapter, OpenAIProviderAdapter,
                    GrokProviderAdapter, DeepSeekProviderAdapter, QwenProviderAdapter]:
            try:
                self.register(cls())
            except Exception as e:
                log.warning(f"[ProviderManager] {cls.__name__} registration skipped: {e}")

    def register(self, adapter: BaseProviderAdapter):
        self._providers[adapter.id] = adapter
        log.info(f"[ProviderManager] Registered provider: {adapter.display_name} ({adapter.id})")

    def get(self, provider_id: str) -> Optional[BaseProviderAdapter]:
        if provider_id == "runpod" and "runpod" not in self._providers:
            try:
                from .runpod_provider import RunPodImageProviderAdapter
                self.register(RunPodImageProviderAdapter())
            except Exception:
                pass
        if provider_id == "runpod_video" and "runpod_video" not in self._providers:
            try:
                from .runpod_video_provider import RunPodVideoProviderAdapter
                self.register(RunPodVideoProviderAdapter())
            except Exception:
                pass
        return self._providers.get(provider_id)


    def list_providers(self) -> List[Dict[str, Any]]:
        result = []
        for pid, adapter in self._providers.items():
            state = self._state.get(pid, {})
            result.append({
                "id": pid,
                "name": adapter.display_name,
                "is_local": adapter.is_local,
                "capabilities": [c.value for c in adapter.capabilities],
                "account": adapter.get_account_info(),
                "trial_expires": state.get("trial_expires"),
                "auth_date": state.get("auth_date"),
            })
        return result

    async def health_check(self, provider_id: str, force: bool = False) -> Dict[str, Any]:
        """Return cached or fresh health check result for a provider."""
        now = time.monotonic()
        cached = self._health_cache.get(provider_id)
        if cached and not force and (now - cached[3]) < self._cache_ttl:
            status, latency, account, _ = cached
        else:
            adapter = self._providers.get(provider_id)
            if not adapter:
                return {"status": "unknown", "latency_ms": 0, "account": "N/A"}
            status, latency, account = await adapter.health_check()
            self._health_cache[provider_id] = (status, latency, account, now)

        return {
            "provider_id": provider_id,
            "status": status.value,
            "latency_ms": latency,
            "account": account
        }

    async def health_check_all(self) -> List[Dict[str, Any]]:
        tasks = [self.health_check(pid, force=True) for pid in self._providers]
        return await asyncio.gather(*tasks)

    async def trigger_login(self, provider_id: str) -> Dict[str, Any]:
        adapter = self._providers.get(provider_id)
        if not adapter:
            return {"status": "error", "message": f"Provider '{provider_id}' not found"}
        result = await adapter.trigger_login()
        if result.get("status") in ("ok", "pending"):
            self._update_state(provider_id, {"auth_date": time.time()})
        return result

    async def logout(self, provider_id: str) -> Dict[str, Any]:
        adapter = self._providers.get(provider_id)
        if not adapter:
            return {"status": "error", "message": f"Provider '{provider_id}' not found"}
        result = await adapter.logout()
        # Invalidate cache
        self._health_cache.pop(provider_id, None)
        return result

    # ── AI Router ──────────────────────────────────────────────

    async def route_chat(
        self,
        messages: List[Dict],
        preferred_provider: str = "auto",
        **kwargs
    ) -> Dict[str, Any]:
        """
        Route a chat request through AUTO or specific provider.
        Falls back automatically on failures to local Ollama or BrainPipeline.
        """
        prompt = messages[-1].get("content", "") if messages else ""
        prompt_low = prompt.lower().strip()
        image_url = kwargs.get("image_url")
        request_type = (kwargs.get("request_type") or kwargs.get("mode") or kwargs.get("intent") or "").lower()

        # SAFE ROUTING (False-Positive Prevention):
        # Generic conversational words ("modelo", "crea", "genera", "generar", "mujer", "chica", "gym", "outfit")
        # are explicitly excluded from triggering image routing on CHAT requests (e.g., "¿Qué modelo utilizas?").
        # Only explicit request_type metadata or unambiguous visual creation phrases will trigger route_image().
        if request_type == "image":
            is_image = True
            is_video = False
        elif request_type == "video":
            is_image = False
            is_video = True
        else:
            explicit_image_phrases = [
                "crea una imagen", "crear una imagen", "genera una imagen", "generar una imagen",
                "crea un dibujo", "crear un dibujo", "genera un dibujo", "generar un dibujo",
                "crea una foto", "crear una foto", "genera una foto", "generar una foto",
                "crea un retrato", "crear un retrato", "genera un retrato", "generar un retrato",
                "dibuja una", "dibuja un", "generar imagen", "crear imagen",
                "generate an image", "create an image", "draw an image", "make an image",
                "generate a picture", "create a picture", "draw a picture", "make a picture",
                "generate a photo", "create a photo", "draw a photo", "make a photo"
            ]
            explicit_video_phrases = [
                "crea un video", "crear un video", "genera un video", "generar un video",
                "crea una animacion", "crear una animacion", "genera una animacion", "generar una animacion",
                "generate a video", "create a video", "make a video", "animate this", "animate image"
            ]

            is_image = any(phrase in prompt_low for phrase in explicit_image_phrases)
            is_video = any(phrase in prompt_low for phrase in explicit_video_phrases)

        # Image-to-video: reference image + explicit video prompt → animate it
        if image_url and not is_image and is_video:
            return await self.route_video(prompt=prompt, preferred_provider="higgsfield", **kwargs)

        if preferred_provider in ("higgsfield", "comfyui") or (preferred_provider == "auto" and (is_video or is_image)):
            if is_video:
                return await self.route_video(prompt=prompt, preferred_provider=preferred_provider, **kwargs)
            else:
                return await self.route_image(prompt=prompt, preferred_provider=preferred_provider, **kwargs)

        # ── EXPLICIT PROVIDER SELECTION (NO FALLBACK) ────────────
        if preferred_provider and preferred_provider != "auto":
            adapter = self._providers.get(preferred_provider)
            if not adapter:
                raise RuntimeError(f"Provider '{preferred_provider}' is not registered or supported in DM AI OS.")
            if not hasattr(adapter, "chat"):
                raise RuntimeError(f"Provider '{preferred_provider}' does not support chat capability.")

            log.info(f"[ProviderManager] Executing explicit chat routing for provider '{preferred_provider}' model={kwargs.get('model')!r}")
            res = await adapter.chat(messages=messages, **kwargs)
            if isinstance(res, dict):
                res["_provider_used"] = preferred_provider
            return res

        # ── AUTO ROUTING (WITH FALLBACK) ──────────────────────────
        priority = AUTO_CHAT_PRIORITY
        try:
            return await self._route_with_fallback("chat", priority, messages=messages, **kwargs)
        except Exception as err:
            log.warning(f"[ProviderManager] All provider adapters failed for chat in AUTO mode ({err}). Delegating to BrainPipeline...")
            from src.api.brain_pipeline import brain_pipeline
            bp_res = await brain_pipeline.process(user_prompt=prompt, user_id="daniel")
            return {
                "choices": [{
                    "message": {
                        "role": "assistant",
                        "content": bp_res.get("response", bp_res.get("result", "Respuesta procesada por DM AI OS."))
                    }
                }],
                "result": bp_res,
                "_provider_used": "dm_brain_pipeline"
            }

    async def route_image(
        self,
        prompt: str,
        preferred_provider: str = "auto",
        **kwargs
    ) -> Dict[str, Any]:
        """Route image generation with auto-fallback or explicit execution."""
        if preferred_provider and preferred_provider != "auto":
            adapter = self._providers.get(preferred_provider)
            if not adapter or not hasattr(adapter, "generate_image"):
                raise RuntimeError(f"Provider '{preferred_provider}' does not support image generation.")
            res = await adapter.generate_image(prompt=prompt, **kwargs)
            res["_provider_used"] = preferred_provider
            return res

        priority = AUTO_MEDIA_PRIORITY
        return await self._route_with_fallback("generate_image", priority, prompt=prompt, **kwargs)

    async def route_video(
        self,
        prompt: str,
        preferred_provider: str = "auto",
        **kwargs
    ) -> Dict[str, Any]:
        """Route video generation with auto-fallback or explicit execution."""
        if preferred_provider and preferred_provider != "auto":
            adapter = self._providers.get(preferred_provider)
            if not adapter or not hasattr(adapter, "generate_video"):
                raise RuntimeError(f"Provider '{preferred_provider}' does not support video generation.")
            res = await adapter.generate_video(prompt=prompt, **kwargs)
            res["_provider_used"] = preferred_provider
            return res

        priority = AUTO_MEDIA_PRIORITY
        return await self._route_with_fallback("generate_video", priority, prompt=prompt, **kwargs)

    async def _route_with_fallback(
        self,
        capability: str,
        priority: List[str],
        **kwargs
    ) -> Dict[str, Any]:
        """Try providers in priority order; auto-fallback on FALLBACK_TRIGGERS."""
        errors = []
        for provider_id in priority:
            adapter = self._providers.get(provider_id)
            if not adapter:
                continue
            if not hasattr(adapter, capability):
                continue

            try:
                method = getattr(adapter, capability)
                result = await method(**kwargs)
                result["_provider_used"] = provider_id
                log.info(f"[ProviderManager] '{capability}' handled by '{provider_id}'")
                return result
            except Exception as e:
                err_str = str(e).lower()
                is_fallback = True  # Always fallback during AUTO routing
                log.warning(f"[ProviderManager] Provider '{provider_id}' failed for '{capability}': {e}")
                errors.append({"provider": provider_id, "error": str(e), "fallback": is_fallback})

        raise RuntimeError(
            f"All providers failed for '{capability}': {errors}"
        )

    # ── State persistence ──────────────────────────────────────

    def _load_state(self) -> Dict[str, Any]:
        try:
            if _STATE_FILE.exists():
                return json.loads(_STATE_FILE.read_text("utf-8"))
        except Exception:
            pass
        return {}

    def _save_state(self):
        try:
            _STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
            _STATE_FILE.write_text(json.dumps(self._state, indent=2), encoding="utf-8")
        except Exception as e:
            log.warning(f"[ProviderManager] State save failed: {e}")

    def _update_state(self, provider_id: str, data: Dict):
        if provider_id not in self._state:
            self._state[provider_id] = {}
        self._state[provider_id].update(data)
        self._save_state()


# Module-level singleton
provider_manager = ProviderManager()
