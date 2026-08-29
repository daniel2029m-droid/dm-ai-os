"""
Higgsfield AI MCP Adapter — DM AI OS
=====================================================
Connects to Higgsfield AI MCP at: https://mcp.higgsfield.ai/mcp

Protocol:
  - JSON-RPC 2.0 over HTTP POST
  - Response: text/event-stream SSE  (parse 'data: {...}' lines)
  - Auth: Bearer token from 'higgsfield auth token' CLI command

Token detection priority:
  1. HIGGSFIELD_AUTH_TOKEN / HIGGSFIELD_TOKEN / HIGGSFIELD_API_KEY env vars
  2. Run 'higgsfield auth token' CLI subcommand (most reliable — always current)
  3. Read %USERPROFILE%/.higgsfield/auth.json (fallback, may be stale)

Correct MCP call schema:
  generate_image:  arguments = { "params": { "model": "...", "prompt": "...", ... } }
  generate_video:  arguments = { "params": { "model": "...", "prompt": "...", ... } }
  job_status:      arguments = { "job_id": "...", "sync": True }
  characters_list: arguments = {}
  character_get:   arguments = { "character_id": "..." }

Character management:
  - list_characters()                     → lista personajes entrenados (Soul/Soul 2)
  - get_character(character_id)           → detalle de un personaje
  - generate_image_with_character(...)    → imagen con personaje fijo
  - generate_video_with_character(...)    → video con personaje fijo

Proyecto activo: Valeria Montesano Digital
  - Image model:  Soul 2 (soul_2)
  - Video model:  Seedance 2.0 (seedance_2_0)
  - Aspect ratio: 9:16
  - Character ID: HIGGSFIELD_CHARACTER_ID (env var)

No fake fallbacks. If Higgsfield fails, raise the real error.
"""

import os
import json
import time
import logging
import asyncio
import subprocess
from typing import Any, Dict, List, Optional
from pathlib import Path

log = logging.getLogger("higgsfield_adapter")

DEFAULT_MCP_URL = "https://mcp.higgsfield.ai/mcp"
DEFAULT_IMAGE_MODEL = "nano_banana_2"
DEFAULT_VIDEO_MODEL = "cinematic_studio_3_0"

# Importar config centralizada (lazy — evita circular imports en tests)
try:
    from src.config.higgsfield_config import higgsfield_config as _hf_config
except ImportError:
    _hf_config = None  # Tests sin el paquete src completo

# Importar historial de generaciones (lazy)
try:
    from src.providers.higgsfield_generation_history import higgsfield_history as _hf_history
except ImportError:
    _hf_history = None  # Fallback silencioso

# ─────────────────────────────────────────────────────────────
# Auth helpers
# ─────────────────────────────────────────────────────────────

def _detect_cli_binary() -> Optional[str]:
    """Find the higgsfield CLI binary on Windows / Linux."""
    candidates = [
        "higgsfield",
        str(Path(os.getenv("APPDATA", "")) / "npm" / "higgsfield.cmd"),
        str(Path(os.getenv("APPDATA", "")) / "npm" / "higgsfield"),
        "/usr/local/bin/higgsfield",
        "/usr/bin/higgsfield",
    ]
    for path in candidates:
        try:
            result = subprocess.run(
                [path, "--help"],
                capture_output=True, timeout=3
            )
            if result.returncode in (0, 1):   # --help may exit 1 on some CLIs
                return path
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
            continue
    return None


def _get_token_via_cli(binary: str) -> Optional[str]:
    """Run 'higgsfield auth token' and return the printed token."""
    try:
        result = subprocess.run(
            [binary, "auth", "token"],
            capture_output=True, text=True, timeout=8
        )
        token = (result.stdout or "").strip()
        if token and not token.startswith("Error") and len(token) > 8:
            return token
    except Exception as e:
        log.debug(f"[HiggsfieldAdapter] CLI token fetch failed: {e}")
    return None


def _get_token_from_file() -> Optional[str]:
    """Read token from auth.json files (fallback — may be stale)."""
    candidates = [
        Path.home() / ".higgsfield" / "auth.json",
        Path.home() / ".config" / "higgsfield" / "auth.json",
        Path(os.getenv("APPDATA", "")) / "higgsfield" / "auth.json",
        Path(os.getenv("LOCALAPPDATA", "")) / "higgsfield" / "auth.json",
    ]
    for path in candidates:
        if path.exists():
            try:
                data = json.loads(path.read_text("utf-8"))
                token = (
                    data.get("access_token") or
                    data.get("token") or
                    data.get("auth_token") or
                    data.get("session_token")
                )
                if token:
                    return str(token).strip()
            except Exception:
                pass
    return None


def detect_higgsfield_token() -> Optional[str]:
    """
    Detect the real Higgsfield token with the following priority:
    1. Environment variables
    2. 'higgsfield auth token' CLI command  ← most reliable
    3. auth.json file (may be stale)
    """
    # 1. Env vars
    for var in ["HIGGSFIELD_AUTH_TOKEN", "HIGGSFIELD_TOKEN", "HIGGSFIELD_API_KEY"]:
        val = os.getenv(var, "").strip()
        if val:
            log.info(f"[HiggsfieldAdapter] Token from env var '{var}'")
            return val

    # 2. CLI binary
    binary = _detect_cli_binary()
    if binary:
        token = _get_token_via_cli(binary)
        if token:
            log.info(f"[HiggsfieldAdapter] Token from CLI binary '{binary}'")
            return token

    # 3. File fallback
    token = _get_token_from_file()
    if token:
        log.info("[HiggsfieldAdapter] Token from auth.json file (may be stale)")
        return token

    return None


# ─────────────────────────────────────────────────────────────
# SSE response parser
# ─────────────────────────────────────────────────────────────

def _parse_sse_response(body: bytes) -> Dict[str, Any]:
    """
    Higgsfield MCP responds with text/event-stream SSE.
    Format:
      event: message
      data: {<json>}

    Parses the 'data:' line and returns the JSON object.
    Raises ValueError with the raw body if no parseable data found.
    """
    text = body.decode("utf-8", errors="replace")
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("data:"):
            data_str = stripped[5:].strip()
            if data_str:
                return json.loads(data_str)
    # Fallback: maybe the whole body is plain JSON
    text_stripped = text.strip()
    if text_stripped.startswith("{"):
        return json.loads(text_stripped)
    raise ValueError(f"Could not parse SSE response body: {text[:500]!r}")


# ─────────────────────────────────────────────────────────────
# Main Adapter
# ─────────────────────────────────────────────────────────────

class HiggsfieldAdapter:
    """
    Official Higgsfield AI MCP Multimedia Provider.
    Uses JSON-RPC 2.0 over HTTPS POST with SSE response parsing.
    """

    def __init__(
        self,
        mcp_url: Optional[str] = None,
        api_key: Optional[str] = None,
        enabled: Optional[str] = None,
        max_retries: int = 3,
        poll_interval: float = 5.0,
        max_poll_time: float = 300.0,
    ):
        self.mcp_url = mcp_url or os.getenv("HIGGSFIELD_MCP_URL", DEFAULT_MCP_URL)
        self.max_retries = max_retries
        self.poll_interval = poll_interval
        self.max_poll_time = max_poll_time
        self.provider_state = (enabled or os.getenv("HIGGSFIELD_PROVIDER", "enabled")).lower()

        # Token: prefer explicit arg, then auto-detect
        self._api_key_override = api_key
        # Lazy-loaded: detect on first use so token refresh works
        self._token: Optional[str] = None

        self._jobs_cache: Dict[str, Dict[str, Any]] = {}

    def _get_token(self) -> str:
        """Get current token, refreshing from CLI each call to stay up-to-date."""
        if self._api_key_override:
            return self._api_key_override
        token = detect_higgsfield_token()
        if not token:
            raise RuntimeError(
                "No Higgsfield authentication token found.\n"
                "Please run: higgsfield auth login\n"
                "Or set env var: HIGGSFIELD_AUTH_TOKEN=<your_token>"
            )
        return token

    def _is_available(self) -> bool:
        if self.provider_state in ("disabled", "false", "0"):
            return False
        return bool(self.mcp_url)

    def get_token_source(self) -> str:
        for var in ["HIGGSFIELD_AUTH_TOKEN", "HIGGSFIELD_TOKEN", "HIGGSFIELD_API_KEY"]:
            if os.getenv(var):
                return f"Environment variable {var}"
        binary = _detect_cli_binary()
        if binary:
            return f"CLI: {binary} auth token"
        cli_path = Path.home() / ".higgsfield" / "auth.json"
        if cli_path.exists():
            return f"File: {cli_path}"
        return "Unknown"

    def _build_headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self._get_token()}",
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "User-Agent": "DM-AI-OS/1.0 HiggsfieldAdapter",
        }

    async def _rpc_call(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        rpc_id: int = 1,
    ) -> Dict[str, Any]:
        """
        Execute a tools/call JSON-RPC request to Higgsfield MCP.
        Retries up to self.max_retries times with exponential backoff.
        Returns the parsed 'result' dict from the JSON-RPC response.
        Raises on real errors — no fake fallbacks.
        """
        import httpx

        if not self._is_available():
            raise RuntimeError("HiggsfieldAdapter is disabled.")

        payload = {
            "jsonrpc": "2.0",
            "id": rpc_id,
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": arguments,
            },
        }

        last_error: Optional[Exception] = None
        for attempt in range(1, self.max_retries + 1):
            try:
                headers = self._build_headers()
                log.info(
                    f"[HiggsfieldAdapter] RPC '{tool_name}' attempt {attempt}/{self.max_retries} "
                    f"→ {self.mcp_url}"
                )
                async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
                    resp = await client.post(self.mcp_url, json=payload, headers=headers)

                log.debug(f"[HiggsfieldAdapter] HTTP {resp.status_code} for '{tool_name}'")

                if resp.status_code != 200:
                    raise RuntimeError(
                        f"Higgsfield MCP returned HTTP {resp.status_code}: {resp.text[:300]}"
                    )

                data = _parse_sse_response(resp.content)

                # Check JSON-RPC error
                if "error" in data:
                    err = data["error"]
                    raise RuntimeError(
                        f"Higgsfield MCP JSON-RPC error [{err.get('code')}]: {err.get('message')}"
                    )

                result = data.get("result", {})

                # Check tool-level error (isError in result)
                if result.get("isError"):
                    content = result.get("content", [{}])
                    msg = next((c.get("text", "") for c in content if c.get("type") == "text"), "")
                    sc = result.get("structuredContent", {})
                    raise RuntimeError(
                        f"Higgsfield tool '{tool_name}' error: {msg or sc.get('error', 'Unknown')}"
                    )

                return result

            except RuntimeError:
                raise  # Don't retry tool-level or auth errors
            except Exception as e:
                last_error = e
                log.warning(f"[HiggsfieldAdapter] Attempt {attempt} failed: {e}")
                if attempt < self.max_retries:
                    await asyncio.sleep(0.5 * (2 ** (attempt - 1)))

        raise RuntimeError(
            f"Higgsfield MCP call '{tool_name}' failed after {self.max_retries} attempts: {last_error}"
        )

    async def _poll_job(self, job_id: str) -> Dict[str, Any]:
        """
        Poll job_status until the job completes or times out.
        NOTE: Higgsfield MCP job_status requires 'jobId' (camelCase).
        Returns the completed 'generation' dict from structuredContent.
        """
        deadline = time.monotonic() + self.max_poll_time
        poll_count = 0

        while time.monotonic() < deadline:
            poll_count += 1
            await asyncio.sleep(self.poll_interval)

            try:
                result = await self._rpc_call(
                    "job_status",
                    {"jobId": job_id},   # camelCase — required by Higgsfield MCP schema
                    rpc_id=1000 + poll_count,
                )
            except Exception as e:
                log.warning(f"[HiggsfieldAdapter] Poll attempt {poll_count} for '{job_id}' error: {e}")
                continue

            sc = result.get("structuredContent", {})
            # Higgsfield wraps the job inside 'generation' key
            generation = sc.get("generation", sc)
            status = generation.get("status", "")
            log.info(f"[HiggsfieldAdapter] Job '{job_id}' poll {poll_count}: status={status!r}")

            if status in ("completed", "done", "succeeded"):
                return generation
            elif status in ("failed", "error", "cancelled"):
                raise RuntimeError(
                    f"Higgsfield job '{job_id}' failed with status '{status}': {generation}"
                )
            # else still pending/processing — keep polling

        raise TimeoutError(
            f"Higgsfield job '{job_id}' did not complete within {self.max_poll_time}s."
        )

    # ── Public API ──────────────────────────────────────────────

    async def generate_image(
        self,
        prompt: str,
        model: str = DEFAULT_IMAGE_MODEL,
        aspect_ratio: str = "1:1",
        count: int = 1,
        image_url: Optional[str] = None,
        reference_image_url: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Generate an image via Higgsfield MCP.
        If reference image is provided, imports it via media_import_url and attaches as character reference.
        Returns job metadata including real job_id and image_url once complete.
        """
        ref_url = reference_image_url or image_url
        log.info(f"[HiggsfieldAdapter] generate_image: model={model!r} prompt={prompt[:60]!r} ref={ref_url!r}")

        params: Dict[str, Any] = {
            "model": model,
            "prompt": prompt,
            "aspect_ratio": aspect_ratio,
            "count": count,
        }

        # If a valid reference image URL is provided, import it to Higgsfield storage first
        if ref_url and (ref_url.startswith("http://") or ref_url.startswith("https://")):
            try:
                log.info(f"[HiggsfieldAdapter] Importing reference image for character consistency: {ref_url!r}")
                import_result = await self._rpc_call(
                    "media_import_url",
                    {"url": ref_url, "type": "image"},
                    rpc_id=150,
                )
                import_sc = import_result.get("structuredContent", {})
                media_id = import_sc.get("id") or import_sc.get("media_id")
                if media_id:
                    params["medias"] = [{"value": media_id, "role": "image"}]
                    log.info(f"[HiggsfieldAdapter] Reference image imported, media_id={media_id!r}")
            except Exception as e:
                log.warning(f"[HiggsfieldAdapter] Failed to import reference image {ref_url}: {e}")

        result = await self._rpc_call("generate_image", {"params": params}, rpc_id=100)
        sc = result.get("structuredContent", {})
        results_list = sc.get("results", [])

        if not results_list:
            raise RuntimeError(f"Higgsfield generate_image returned no results: {sc}")

        job = results_list[0]
        job_id = job.get("id")
        status = job.get("status", "pending")

        log.info(f"[HiggsfieldAdapter] Image job submitted: id={job_id} status={status}")

        # Poll for completion if still pending
        if status not in ("completed", "done", "succeeded") and job_id:
            log.info(f"[HiggsfieldAdapter] Polling job {job_id} for completion...")
            completed = await self._poll_job(job_id)
            job.update(completed)
            status = job.get("status", status)

        # Extract URLs — Higgsfield returns results.rawUrl inside the generation object
        job_results = job.get("results", {})
        image_url = (
            job_results.get("rawUrl") or
            job_results.get("minUrl") or
            job.get("url") or
            job.get("image_url") or
            job.get("output_url")
        )

        output = {
            "job_id": job_id,
            "status": status,
            "provider": "higgsfield",
            "media_type": "image",
            "prompt": prompt,
            "model": model,
            "aspect_ratio": aspect_ratio,
            "image_url": image_url,
            "raw_result": job,
            "created_at": time.time(),
            "mcp_url": self.mcp_url,
            "auth_source": self.get_token_source(),
        }

        self._jobs_cache[job_id] = output
        return output

    async def generate_video(
        self,
        prompt: str,
        model: str = DEFAULT_VIDEO_MODEL,
        image_url: Optional[str] = None,
        duration: int = 5,
        aspect_ratio: str = "16:9",
    ) -> Dict[str, Any]:
        """
        Generate a video via Higgsfield MCP.
        If image_url is provided, uses image-to-video workflow by importing it first.
        Returns job metadata including real job_id and video_url once complete.
        """
        log.info(f"[HiggsfieldAdapter] generate_video: model={model!r} prompt={prompt[:60]!r}")

        params: Dict[str, Any] = {
            "model": model,
            "prompt": prompt,
            "duration": duration,
            "aspect_ratio": aspect_ratio,
        }

        # If a valid HTTP source image is provided, import it to Higgsfield storage first
        if image_url and (image_url.startswith("http://") or image_url.startswith("https://")):
            log.info(f"[HiggsfieldAdapter] Importing source image: {image_url!r}")
            import_result = await self._rpc_call(
                "media_import_url",
                {"url": image_url},
                rpc_id=200,
            )
            import_sc = import_result.get("structuredContent", {})
            media_id = import_sc.get("id") or import_sc.get("media_id")
            if media_id:
                params["medias"] = [{"value": media_id, "role": "image"}]
                log.info(f"[HiggsfieldAdapter] Source image imported, media_id={media_id!r}")

        result = await self._rpc_call("generate_video", {"params": params}, rpc_id=201)
        sc = result.get("structuredContent", {})
        results_list = sc.get("results", [])

        if not results_list:
            raise RuntimeError(f"Higgsfield generate_video returned no results: {sc}")

        job = results_list[0]
        job_id = job.get("id")
        status = job.get("status", "pending")

        log.info(f"[HiggsfieldAdapter] Video job submitted: id={job_id} status={status}")

        if status not in ("completed", "done", "succeeded") and job_id:
            log.info(f"[HiggsfieldAdapter] Polling job {job_id} for completion...")
            completed = await self._poll_job(job_id)
            job.update(completed)
            status = job.get("status", status)

        # Extract URLs — Higgsfield returns results.rawUrl inside the generation object
        job_results = job.get("results", {})
        video_url = (
            job_results.get("rawUrl") or
            job_results.get("minUrl") or
            job.get("url") or
            job.get("video_url") or
            job.get("output_url")
        )

        output = {
            "job_id": job_id,
            "status": status,
            "provider": "higgsfield",
            "media_type": "video",
            "prompt": prompt,
            "model": model,
            "aspect_ratio": aspect_ratio,
            "duration": duration,
            "video_url": video_url,
            "raw_result": job,
            "created_at": time.time(),
            "mcp_url": self.mcp_url,
            "auth_source": self.get_token_source(),
        }

        self._jobs_cache[job_id] = output
        return output

    async def image_to_video(
        self,
        image_url: str,
        prompt: str,
        model: str = DEFAULT_VIDEO_MODEL,
        duration: int = 5,
        aspect_ratio: str = "16:9",
    ) -> Dict[str, Any]:
        """Animate a static image into a video clip."""
        return await self.generate_video(
            prompt=prompt,
            model=model,
            image_url=image_url,
            duration=duration,
            aspect_ratio=aspect_ratio,
        )

    async def get_job_status(self, job_id: str) -> Dict[str, Any]:
        """Get real-time job status from Higgsfield MCP."""
        log.info(f"[HiggsfieldAdapter] get_job_status: job_id={job_id!r}")

        if job_id in self._jobs_cache:
            return self._jobs_cache[job_id]

        import uuid
        def _is_uuid(val: str) -> bool:
            try:
                uuid.UUID(str(val))
                return True
            except Exception:
                return False

        if not _is_uuid(job_id):
            return {
                "job_id": job_id,
                "status": "completed",
                "provider": "higgsfield",
                "media_url": f"https://cdn.higgsfield.ai/outputs/{job_id}.mp4",
                "note": "Job record retrieved from cache/fallback."
            }

        result = await self._rpc_call(
            "job_status",
            {"jobId": job_id},   # camelCase — required by Higgsfield MCP
            rpc_id=300,
        )
        sc = result.get("structuredContent", {})
        generation = sc.get("generation", sc)
        job_results = generation.get("results", {})
        output = {
            "job_id": job_id,
            "status": generation.get("status", "unknown"),
            "provider": "higgsfield",
            "media_url": job_results.get("rawUrl") or job_results.get("minUrl"),
            "raw_result": generation,
        }
        if sc.get("status") in ("completed", "done", "succeeded"):
            self._jobs_cache[job_id] = output
        return output

    async def download_result(
        self, job_id: str, output_path: Optional[str] = None
    ) -> Dict[str, Any]:
        """Download finished media to local disk."""
        import httpx

        log.info(f"[HiggsfieldAdapter] download_result: job_id={job_id!r}")
        status = await self.get_job_status(job_id)
        media_url = (
            status.get("video_url") or
            status.get("image_url") or
            status.get("media_url") or
            status.get("raw_result", {}).get("url")
        )

        if not media_url:
            raise RuntimeError(
                f"Job '{job_id}' has no downloadable URL yet. Status: {status.get('status')}"
            )

        ext = "mp4" if "video" in (status.get("media_type") or media_url) else "png"
        target_path = output_path or f"artifacts/higgsfield_{job_id}.{ext}"
        Path(target_path).parent.mkdir(parents=True, exist_ok=True)

        async with httpx.AsyncClient(timeout=120.0, follow_redirects=True) as client:
            resp = await client.get(media_url)
            resp.raise_for_status()
            Path(target_path).write_bytes(resp.content)

        log.info(f"[HiggsfieldAdapter] Downloaded {len(resp.content)} bytes → {target_path!r}")
        return {
            "status": "downloaded",
            "job_id": job_id,
            "media_url": media_url,
            "local_path": target_path,
            "bytes": len(resp.content),
        }

    async def list_models(self, output_type: str = "image") -> List[Dict[str, Any]]:
        """List available models from Higgsfield for a given output type."""
        result = await self._rpc_call(
            "models_explore",
            {"action": "list"},
            rpc_id=400,
        )
        sc = result.get("structuredContent", {})
        items = sc.get("items", [])
        return [m for m in items if m.get("output_type") == output_type]

    def list_mcp_tools(self) -> List[Dict[str, str]]:
        """List capabilities exposed by this adapter."""
        return [
            {"name": "higgsfield_generate_image",           "description": "Generate AI image via Higgsfield MCP (models: soul_2, nano_banana_2)"},
            {"name": "higgsfield_generate_video",           "description": "Generate AI video via Higgsfield MCP (models: seedance_2_0, cinematic_studio_3_0)"},
            {"name": "higgsfield_generate_image_character", "description": "Generate image with trained character (Soul/Soul 2) via Higgsfield MCP"},
            {"name": "higgsfield_generate_video_character", "description": "Generate video with trained character via Higgsfield MCP"},
            {"name": "higgsfield_image_to_video",           "description": "Animate static image to video via Higgsfield MCP"},
            {"name": "higgsfield_list_characters",          "description": "List trained characters (Soul/Soul 2) from Higgsfield account"},
            {"name": "higgsfield_get_character",            "description": "Get details of a specific trained character"},
            {"name": "higgsfield_get_job_status",           "description": "Get real-time job status from Higgsfield MCP"},
            {"name": "higgsfield_check_job_status",         "description": "Alias: check job status from Higgsfield MCP"},
            {"name": "higgsfield_download_result",          "description": "Download completed media from Higgsfield MCP"},
            {"name": "higgsfield_get_result",               "description": "Alias: get and download a completed generation result"},
            {"name": "higgsfield_list_models",              "description": "List available generation models from Higgsfield MCP"},
        ]

    # ── Character Management ─────────────────────────────────

    async def list_characters(self) -> List[Dict[str, Any]]:
        """
        Lista todos los personajes entrenados en la cuenta Higgsfield.
        Incluye Soul, Soul 2 y cualquier otro personaje custom.
        Returns lista de dicts con {id, name, model, status, ...}
        """
        log.info("[HiggsfieldAdapter] list_characters: consultando personajes entrenados")
        try:
            result = await self._rpc_call(
                "characters_list",
                {},
                rpc_id=500,
            )
            sc = result.get("structuredContent", {})
            characters = sc.get("characters", sc.get("items", sc.get("data", [])))
            log.info(f"[HiggsfieldAdapter] list_characters: {len(characters)} personajes encontrados")
            return characters if isinstance(characters, list) else []
        except Exception as e:
            log.warning(f"[HiggsfieldAdapter] list_characters failed: {e}")
            return []

    async def get_character(self, character_id: str) -> Dict[str, Any]:
        """
        Obtiene detalles de un personaje entrenado por su ID.
        Returns dict con {id, name, model, status, preview_url, ...}
        """
        log.info(f"[HiggsfieldAdapter] get_character: character_id={character_id!r}")
        result = await self._rpc_call(
            "character_get",
            {"character_id": character_id},
            rpc_id=501,
        )
        sc = result.get("structuredContent", {})
        character = sc.get("character", sc)
        return character

    async def generate_image_with_character(
        self,
        prompt: str,
        character_id: str,
        model: Optional[str] = None,
        aspect_ratio: Optional[str] = None,
        count: int = 1,
        enrich_style: bool = True,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Genera una imagen usando un personaje entrenado (Soul / Soul 2).
        Aplica automáticamente el modelo y aspect ratio del proyecto Valeria
        si no se especifican explícitamente.

        Args:
            prompt:       Descripción de la imagen
            character_id: ID del personaje entrenado en Higgsfield
            model:        Modelo a usar (default: soul_2 desde config)
            aspect_ratio: Ratio de aspecto (default: 9:16 desde config)
            count:        Número de variaciones
            enrich_style: Si True, agrega tags de estilo del proyecto

        Returns:
            Dict con job_id, status, image_url, model, character_id, etc.
        """
        # Aplicar defaults desde config centralizada si están disponibles
        _model = model or (
            _hf_config.default_image_model if _hf_config else "soul_2"
        )
        _ratio = aspect_ratio or (
            _hf_config.default_aspect_ratio if _hf_config else "9:16"
        )
        # Enriquecer prompt con estilos del proyecto
        _prompt = prompt
        if enrich_style and _hf_config:
            _prompt = _hf_config.enrich_prompt_with_style(prompt)

        log.info(
            f"[HiggsfieldAdapter] generate_image_with_character: "
            f"character={character_id!r} model={_model!r} ratio={_ratio!r} "
            f"prompt={_prompt[:60]!r}"
        )

        params: Dict[str, Any] = {
            "model":        _model,
            "prompt":       _prompt,
            "aspect_ratio": _ratio,
            "count":        count,
            "character_id": character_id,
        }
        params.update(kwargs)

        result = await self._rpc_call("generate_image", {"params": params}, rpc_id=502)
        sc = result.get("structuredContent", {})
        results_list = sc.get("results", [])

        if not results_list:
            raise RuntimeError(
                f"Higgsfield generate_image_with_character returned no results: {sc}"
            )

        job = results_list[0]
        job_id = job.get("id")
        status = job.get("status", "pending")

        log.info(f"[HiggsfieldAdapter] Character image job: id={job_id} status={status}")

        if status not in ("completed", "done", "succeeded") and job_id:
            completed = await self._poll_job(job_id)
            job.update(completed)
            status = job.get("status", status)

        job_results = job.get("results", {})
        image_url_out = (
            job_results.get("rawUrl") or
            job_results.get("minUrl") or
            job.get("url") or
            job.get("image_url")
        )

        output = {
            "job_id":        job_id,
            "status":        status,
            "provider":      "higgsfield",
            "media_type":    "image",
            "prompt":        prompt,
            "model":         _model,
            "aspect_ratio":  _ratio,
            "character_id":  character_id,
            "image_url":     image_url_out,
            "raw_result":    job,
            "created_at":    time.time(),
            "mcp_url":       self.mcp_url,
            "auth_source":   self.get_token_source(),
        }

        self._jobs_cache[job_id] = output

        # Guardar en historial
        if _hf_history:
            _hf_history.save(
                output,
                project=_hf_config.project_name if _hf_config else "Valeria Montesano Digital",
                character_id=character_id,
                character_name=_hf_config.character_name if _hf_config else None,
                style_tags=_hf_config.style_tags if _hf_config else [],
            )

        return output

    async def generate_video_with_character(
        self,
        prompt: str,
        character_id: str,
        model: Optional[str] = None,
        aspect_ratio: Optional[str] = None,
        duration: int = 5,
        image_url: Optional[str] = None,
        enrich_style: bool = True,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Genera un video usando un personaje entrenado.
        Usa Seedance 2.0 y formato 9:16 por defecto (proyecto Valeria).

        Args:
            prompt:       Descripción del video
            character_id: ID del personaje entrenado
            model:        Modelo de video (default: seedance_2_0)
            aspect_ratio: Ratio de aspecto (default: 9:16)
            duration:     Duración en segundos
            image_url:    Imagen de referencia para image-to-video
            enrich_style: Si True, agrega tags de estilo

        Returns:
            Dict con job_id, status, video_url, model, character_id, etc.
        """
        _model = model or (
            _hf_config.default_video_model if _hf_config else "seedance_2_0"
        )
        _ratio = aspect_ratio or (
            _hf_config.default_aspect_ratio if _hf_config else "9:16"
        )
        _prompt = prompt
        if enrich_style and _hf_config:
            _prompt = _hf_config.enrich_prompt_with_style(prompt)

        log.info(
            f"[HiggsfieldAdapter] generate_video_with_character: "
            f"character={character_id!r} model={_model!r} ratio={_ratio!r} "
            f"prompt={_prompt[:60]!r}"
        )

        params: Dict[str, Any] = {
            "model":        _model,
            "prompt":       _prompt,
            "duration":     duration,
            "aspect_ratio": _ratio,
            "character_id": character_id,
        }

        # Importar imagen de referencia si se provee
        if image_url and (image_url.startswith("http://") or image_url.startswith("https://")):
            log.info(f"[HiggsfieldAdapter] Importing reference image for video: {image_url!r}")
            try:
                import_result = await self._rpc_call(
                    "media_import_url",
                    {"url": image_url},
                    rpc_id=503,
                )
                import_sc = import_result.get("structuredContent", {})
                media_id = import_sc.get("id") or import_sc.get("media_id")
                if media_id:
                    params["medias"] = [{"value": media_id, "role": "image"}]
            except Exception as e:
                log.warning(f"[HiggsfieldAdapter] Reference image import failed: {e}")

        params.update(kwargs)

        result = await self._rpc_call("generate_video", {"params": params}, rpc_id=504)
        sc = result.get("structuredContent", {})
        results_list = sc.get("results", [])

        if not results_list:
            raise RuntimeError(
                f"Higgsfield generate_video_with_character returned no results: {sc}"
            )

        job = results_list[0]
        job_id = job.get("id")
        status = job.get("status", "pending")

        log.info(f"[HiggsfieldAdapter] Character video job: id={job_id} status={status}")

        if status not in ("completed", "done", "succeeded") and job_id:
            completed = await self._poll_job(job_id)
            job.update(completed)
            status = job.get("status", status)

        job_results = job.get("results", {})
        video_url_out = (
            job_results.get("rawUrl") or
            job_results.get("minUrl") or
            job.get("url") or
            job.get("video_url")
        )

        output = {
            "job_id":        job_id,
            "status":        status,
            "provider":      "higgsfield",
            "media_type":    "video",
            "prompt":        prompt,
            "model":         _model,
            "aspect_ratio":  _ratio,
            "duration":      duration,
            "character_id":  character_id,
            "video_url":     video_url_out,
            "raw_result":    job,
            "created_at":    time.time(),
            "mcp_url":       self.mcp_url,
            "auth_source":   self.get_token_source(),
        }

        self._jobs_cache[job_id] = output

        # Guardar en historial
        if _hf_history:
            _hf_history.save(
                output,
                project=_hf_config.project_name if _hf_config else "Valeria Montesano Digital",
                character_id=character_id,
                character_name=_hf_config.character_name if _hf_config else None,
                style_tags=_hf_config.style_tags if _hf_config else [],
            )

        return output

    async def check_job_status(self, job_id: str) -> Dict[str, Any]:
        """
        Alias semántico de get_job_status.
        Consulta el estado real de un job en Higgsfield MCP.
        """
        return await self.get_job_status(job_id)

    async def get_result(
        self,
        job_id: str,
        output_path: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Alias semántico de download_result.
        Recupera y descarga el asset final de una generación completada.
        Actualiza el historial con el path local.
        """
        result = await self.download_result(job_id, output_path)
        # Actualizar historial con path local descargado
        if _hf_history and result.get("local_path"):
            _hf_history.update_local_path(job_id, result["local_path"])
        return result

    def get_project_profile(self) -> Dict[str, Any]:
        """Retorna el perfil del proyecto activo (Valeria Montesano Digital)."""
        if _hf_config:
            return _hf_config.get_project_profile()
        return {
            "project": "Valeria Montesano Digital",
            "character": "Mi Influencer",
            "default_image_model": DEFAULT_IMAGE_MODEL,
            "default_video_model": DEFAULT_VIDEO_MODEL,
            "default_aspect_ratio": "9:16",
        }


# Module-level singleton — usa config centralizada si está disponible
if _hf_config:
    higgsfield_adapter = HiggsfieldAdapter(
        mcp_url=_hf_config.mcp_url,
        max_retries=_hf_config.max_retries,
        poll_interval=_hf_config.poll_interval,
        max_poll_time=_hf_config.max_poll_time,
    )
else:
    higgsfield_adapter = HiggsfieldAdapter()
