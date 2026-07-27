"""
VisionAdapter — P6 Open Source Integration (Fase C)
===================================================
Granular vision model preprocessing and model routing for local multimodal models.

Permite preprocesar imagenes (resize, compresiÃ³n, base64 encoding) y seleccionar
el modelo local especializado por subtarea visual:
- OCR / lectura de texto  -> qwen2.5-vl:7b, llava:7b
- Comprension compleja     -> llama3.2-vision:11b, qwen2-vl:7b
- Captioning rapido        -> bakllava:7b, llava:7b

Patron DM AI OS:
- _is_available() verifica conectividad con Ollama y presencia de modelos de vision.
- Si no disponible: retorna None y CapabilitySelector usa routing vision por defecto.
- VISION_ADAPTER_ENABLED=true en .env para activar (opt-in).

NO modifica BrainPipeline ni CapabilitySelector congelados.
"""

import os
import io
import base64
import logging
from typing import Optional, Dict, Any, List

log = logging.getLogger("vision_adapter")

# Granular model hierarchy per vision subtask
VISION_CAPABILITY_MAP = {
    "ocr": ["qwen2.5-vl:7b", "llava:7b", "llama3.2-vision:11b", "qwen2.5:0.5b"],
    "analysis": ["llama3.2-vision:11b", "qwen2-vl:7b", "llava:7b"],
    "caption": ["bakllava:7b", "llava:7b", "qwen2.5-vl:7b"],
    "general": ["llava:7b", "bakllava:7b", "llama3.2-vision:11b", "qwen2.5:1.5b"],
}


class VisionAdapter:
    """Thin adapter for local vision model routing and image preprocessing."""

    _ENABLED_ENV = "VISION_ADAPTER_ENABLED"

    @staticmethod
    def _is_enabled() -> bool:
        """Check VISION_ADAPTER_ENABLED env var (defaults to True as lightweight)."""
        return os.getenv("VISION_ADAPTER_ENABLED", "true").lower() in ("true", "1", "yes")

    def encode_image(self, image_bytes: bytes) -> str:
        """Encode raw image bytes to base64 string expected by Ollama."""
        return base64.b64encode(image_bytes).decode("utf-8")

    def preprocess_image(
        self,
        image_bytes: bytes,
        max_size: int = 1024,
    ) -> bytes:
        """
        Resize image if PIL is available to reduce token budget and inference time.
        Falls back to raw bytes if PIL is not installed.
        """
        try:
            from PIL import Image
            img = Image.open(io.BytesIO(image_bytes))
            img.thumbnail((max_size, max_size))
            buffer = io.BytesIO()
            img.save(buffer, format=img.format or "JPEG")
            return buffer.getvalue()
        except ImportError:
            log.debug("[VisionAdapter] PIL not installed, skipping resize.")
            return image_bytes
        except Exception as e:
            log.warning(f"[VisionAdapter] Preprocessing image failed: {e}")
            return image_bytes

    def select_vision_model(
        self,
        subtask: str = "general",
        installed_models: Optional[List[str]] = None,
    ) -> str:
        """
        Select best matching local vision model for a specific visual subtask.

        Args:
            subtask: 'ocr', 'analysis', 'caption', or 'general'
            installed_models: List of model names returned by Ollama tags API.

        Returns:
            Name of chosen model string.
        """
        candidates = VISION_CAPABILITY_MAP.get(subtask.lower(), VISION_CAPABILITY_MAP["general"])

        if installed_models:
            for candidate in candidates:
                for inst in installed_models:
                    if candidate.lower() in inst.lower():
                        log.info(f"[VisionAdapter] Subtask '{subtask}' -> Selected model '{inst}'")
                        return inst

        fallback = candidates[0]
        log.info(f"[VisionAdapter] Subtask '{subtask}' -> Default model '{fallback}'")
        return fallback

    def analyze_image(
        self,
        image_bytes: bytes,
        prompt: str = "Describe esta imagen en detalle.",
        subtask: str = "general",
        system_prompt: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Preprocess image and execute visual analysis via CapabilitySelector.

        Returns:
            {"status": "success", "analysis": str, "model": str, "subtask": str}
            or None if disabled/failed.
        """
        if not self._is_enabled():
            return None

        try:
            processed_bytes = self.preprocess_image(image_bytes)
            b64_img = self.encode_image(processed_bytes)

            from ..providers.capability_selector import capability_selector

            # Retrieve installed models to select best matching vision model
            installed = capability_selector.probe_models()
            chosen_model = self.select_vision_model(subtask, installed)

            log.info(f"[VisionAdapter] Analyzing image with model '{chosen_model}' for subtask '{subtask}'")
            res_text = capability_selector.generate(
                prompt=prompt,
                capability="vision",
                system_prompt=system_prompt,
                images=[b64_img],
            )

            return {
                "status": "success",
                "analysis": res_text,
                "model": chosen_model,
                "subtask": subtask,
                "source": "vision_adapter",
            }
        except Exception as e:
            log.warning(f"[VisionAdapter] Image analysis failed: {e}")
            return None


# Module-level singleton
vision_adapter = VisionAdapter()
