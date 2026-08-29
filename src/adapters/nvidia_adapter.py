"""
NVIDIA NIM Adapter — FLUX.2 Klein 4B Integration for DM AI OS
================================================================
Handles direct HTTP communication with NVIDIA NIM API for FLUX.2 Klein 4B image generation.

Supports:
- Text-to-image
- Image-to-image / reference image / editing
- Formats: PNG, JPG, JPEG (file path, bytes, internal path/URL, or base64)
- Aspect ratios: 1:1, 16:9, 9:16, 4:5, 5:4, 3:2, 2:3
- Seed & steps configuration
- Dynamic response format handling (artifacts base64, OpenAI b64_json, image base64, or raw bytes)
- Quota tracking via provider_history
- SHA-256 hash caching via StorageLayer
"""

import os
import base64
import hashlib
import io
import time
import logging
import httpx
from pathlib import Path
from typing import Dict, Any, Optional, Union
from PIL import Image

from ..config.nvidia_config import nvidia_config, SUPPORTED_IMAGE_FORMATS
from ..storage.storage_layer import storage
from ..providers.provider_history import provider_history

log = logging.getLogger("nvidia_adapter")


class NVIDIAAdapterError(Exception):
    """Base exception for NVIDIA NIM adapter errors."""
    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(message)
        self.status_code = status_code


class NVIDIAAdapter:
    """Adapter for interacting with NVIDIA NIM FLUX.2 Klein 4B endpoint."""

    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None):
        self._override_api_key = api_key
        self._override_base_url = base_url

    @property
    def api_key(self) -> str:
        key = self._override_api_key or nvidia_config.api_key
        if not key:
            raise NVIDIAAdapterError(
                "NVIDIA_API_KEY environment variable is missing. Set NVIDIA_API_KEY before making calls.",
                status_code=401
            )
        return key

    @property
    def base_url(self) -> str:
        return self._override_base_url or nvidia_config.base_url

    def validate_and_encode_image(self, image_input: Union[str, bytes, Path]) -> tuple:
        """
        Validates reference image input and converts it to (base64_str, mime_type, sha256_hash).
        Accepts: local file path, raw bytes, or base64 data string/URL.
        Supported formats: PNG, JPG, JPEG.
        """
        raw_bytes = None
        mime_type = "image/png"

        if isinstance(image_input, (str, Path)):
            str_path = str(image_input)

            # Check if it's already a base64 data URL
            if str_path.startswith("data:image/"):
                header, b64_data = str_path.split(",", 1)
                mime_type = header.split(";")[0].replace("data:", "")
                raw_bytes = base64.b64decode(b64_data)
            elif len(str_path) > 500 and not os.path.exists(str_path):
                # Likely raw base64 string
                try:
                    raw_bytes = base64.b64decode(str_path)
                except Exception:
                    raise NVIDIAAdapterError("Invalid base64 string provided for reference image.")
            else:
                path = Path(str_path)
                if not path.exists():
                    raise NVIDIAAdapterError(f"Reference image file not found at: {path}")

                ext = path.suffix.lstrip(".").lower()
                if ext not in SUPPORTED_IMAGE_FORMATS:
                    raise NVIDIAAdapterError(
                        f"Unsupported image format '.{ext}'. Supported formats: {', '.join(SUPPORTED_IMAGE_FORMATS)}"
                    )

                mime_type = "image/jpeg" if ext in ("jpg", "jpeg") else "image/png"
                raw_bytes = path.read_bytes()

        elif isinstance(image_input, bytes):
            raw_bytes = image_input

        else:
            raise NVIDIAAdapterError(f"Unsupported image input type: {type(image_input)}")

        if not raw_bytes:
            raise NVIDIAAdapterError("Empty image input provided.")

        # Validate image format via PIL
        try:
            with Image.open(io.BytesIO(raw_bytes)) as img:
                img_format = (img.format or "").lower()
                if img_format not in ("png", "jpeg", "jpg"):
                    raise NVIDIAAdapterError(
                        f"Image contents identified as unsupported format '{img_format}'. Supported: PNG, JPG, JPEG."
                    )
        except NVIDIAAdapterError:
            raise
        except Exception as e:
            raise NVIDIAAdapterError(f"Corrupt or unreadable reference image: {e}")

        b64_str = base64.b64encode(raw_bytes).decode("utf-8")
        img_hash = hashlib.sha256(raw_bytes).hexdigest()

        return b64_str, mime_type, img_hash

    async def generate_image(
        self,
        prompt: str,
        *,
        reference_image: Optional[Union[str, bytes, Path]] = None,
        aspect_ratio: str = "1:1",
        seed: Optional[int] = None,
        steps: Optional[int] = None,
        timeout: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None,
        use_cache: bool = True
    ) -> Dict[str, Any]:
        """
        Generates an image via FLUX.2 Klein 4B on NVIDIA NIM.
        Checks cache prior to making external requests.
        """
        if not prompt or not prompt.strip():
            raise NVIDIAAdapterError("Prompt cannot be empty.")

        model_name = nvidia_config.model
        ref_b64 = None
        ref_mime = None
        ref_hash = None

        if reference_image:
            ref_b64, ref_mime, ref_hash = self.validate_and_encode_image(reference_image)

        width, height = nvidia_config.get_dimensions_for_ratio(aspect_ratio)

        # Build cache key payload
        cache_key_data = {
            "provider": "nvidia",
            "model": model_name,
            "prompt": prompt.strip(),
            "aspect_ratio": aspect_ratio,
            "seed": seed,
            "steps": steps,
            "reference_image_hash": ref_hash,
        }

        # Check Cache
        if use_cache:
            cached_result = storage.get_cache("nvidia_flux2", cache_key_data)
            if cached_result:
                log.info(f"[NVIDIAAdapter] CACHE HIT for prompt: '{prompt[:40]}...'")
                cached_result["_cached"] = True
                return cached_result

        # Prepare request payload for NVIDIA NIM
        mode = "image-to-image" if ref_b64 else "text-to-image"
        payload: Dict[str, Any] = {
            "prompt": prompt,
            "aspect_ratio": aspect_ratio,
        }



        if seed is not None:
            payload["seed"] = int(seed)
        if steps is not None:
            payload["steps"] = int(steps)
            payload["num_inference_steps"] = int(steps)
        if metadata:
            payload["metadata"] = metadata
        if ref_b64:
            payload["image"] = f"data:{ref_mime};base64,{ref_b64}"
            payload["reference_image"] = f"data:{ref_mime};base64,{ref_b64}"

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

        request_timeout = timeout or nvidia_config.timeout
        t0 = time.monotonic()
        http_status = None
        error_msg = None
        result_data = None

        log.info(f"[NVIDIAAdapter] Requesting FLUX.2 Klein 4B ({mode}, ratio={aspect_ratio}) at {self.base_url}")

        try:
            async with httpx.AsyncClient(timeout=request_timeout) as client:
                resp = await client.post(self.base_url, json=payload, headers=headers)
                http_status = resp.status_code

                if resp.status_code == 429:
                    error_msg = "HTTP 429: Rate limit exceeded or quota exhausted on NVIDIA NIM."
                    log.error(f"[NVIDIAAdapter] {error_msg}")
                    raise NVIDIAAdapterError(error_msg, status_code=429)

                if resp.status_code == 401 or resp.status_code == 403:
                    error_msg = f"HTTP {resp.status_code}: Unauthorized. Check NVIDIA_API_KEY."
                    log.error(f"[NVIDIAAdapter] {error_msg}")
                    raise NVIDIAAdapterError(error_msg, status_code=resp.status_code)

                resp.raise_for_status()
                content_type = resp.headers.get("content-type", "")

                if "application/json" in content_type:
                    result_data = resp.json()
                else:
                    # Direct binary image response
                    result_data = {"raw_bytes": resp.content, "format": "png"}

        except httpx.TimeoutException as e:
            latency_ms = round((time.monotonic() - t0) * 1000, 1)
            error_msg = f"Request timed out after {request_timeout}s: {e}"
            provider_history.record(
                provider="nvidia", capability="image", prompt=prompt, model=model_name,
                duration_ms=latency_ms, status="error", error=error_msg
            )
            raise NVIDIAAdapterError(error_msg, status_code=408)
        except httpx.HTTPStatusError as e:
            latency_ms = round((time.monotonic() - t0) * 1000, 1)
            error_msg = f"HTTP {e.response.status_code} Error: {e.response.text}"
            provider_history.record(
                provider="nvidia", capability="image", prompt=prompt, model=model_name,
                duration_ms=latency_ms, status="error", error=f"HTTP {e.response.status_code}"
            )
            raise NVIDIAAdapterError(error_msg, status_code=e.response.status_code)
        except NVIDIAAdapterError:
            raise
        except Exception as e:
            latency_ms = round((time.monotonic() - t0) * 1000, 1)
            error_msg = f"Unexpected error during NVIDIA API request: {e}"
            provider_history.record(
                provider="nvidia", capability="image", prompt=prompt, model=model_name,
                duration_ms=latency_ms, status="error", error=str(e)
            )
            raise NVIDIAAdapterError(error_msg)

        latency_ms = round((time.monotonic() - t0) * 1000, 1)

        # Parse generated image base64 / binary bytes
        b64_output = None
        if "raw_bytes" in result_data:
            b64_output = base64.b64encode(result_data["raw_bytes"]).decode("utf-8")
        elif "artifacts" in result_data and isinstance(result_data["artifacts"], list) and len(result_data["artifacts"]) > 0:
            art = result_data["artifacts"][0]
            b64_output = art.get("base64") or art.get("b64_json")
        elif "data" in result_data and isinstance(result_data["data"], list) and len(result_data["data"]) > 0:
            d0 = result_data["data"][0]
            b64_output = d0.get("b64_json") or d0.get("base64")
        elif "image" in result_data and isinstance(result_data["image"], str):
            b64_output = result_data["image"]
            if b64_output.startswith("data:image/"):
                b64_output = b64_output.split(",", 1)[1]

        if not b64_output:
            raise NVIDIAAdapterError(f"Could not extract image from NVIDIA response payload: {result_data}")

        # Save artifact image to storage
        image_bytes = base64.b64decode(b64_output)
        img_filename = f"nvidia_flux2_{int(time.time())}_{hashlib.md5(prompt.encode()).hexdigest()[:8]}.png"
        
        # Save file via storage layer
        storage._ensure_artifacts_dir()
        file_path = storage.artifacts_dir / img_filename
        file_path.write_bytes(image_bytes)

        # Create relative / HTTP URL
        image_url = f"/api/providers/uploads/{img_filename}"

        final_result = {
            "status": "success",
            "provider": "nvidia",
            "model": model_name,
            "prompt": prompt,
            "aspect_ratio": aspect_ratio,
            "width": width,
            "height": height,
            "image_url": image_url,
            "file_path": str(file_path),
            "latency_ms": latency_ms,
            "http_status": http_status or 200,
            "_cached": False
        }

        # Store in cache
        storage.set_cache("nvidia_flux2", cache_key_data, final_result)

        # Record quota & history
        provider_history.record(
            provider="nvidia",
            capability="image",
            prompt=prompt,
            model=model_name,
            account="NVIDIA NIM Account",
            result_url=image_url,
            duration_ms=latency_ms,
            status="ok",
        )

        return final_result


nvidia_adapter = NVIDIAAdapter()
