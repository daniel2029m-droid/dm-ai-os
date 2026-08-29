"""
Facebook OCR Metrics Extractor
==============================
When metrics exist only as graphics/charts, take screenshots and run OCR
via VisionAdapter / CapabilitySelector, then normalize structured values.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .paths import get_screenshots_dir

log = logging.getLogger("facebook.ocr_extractor")

# Patterns for common metric labels (ES + EN)
_METRIC_PATTERNS: List[Tuple[str, re.Pattern]] = [
    ("followers", re.compile(r"(?:seguidores|followers|fans)\s*[:\-]?\s*([\d.,]+\s*[kKmMbB]?)", re.I)),
    ("reach", re.compile(r"(?:alcance|reach)\s*[:\-]?\s*([\d.,]+\s*[kKmMbB]?)", re.I)),
    ("views", re.compile(r"(?:visualizaciones|views|reproducciones)\s*[:\-]?\s*([\d.,]+\s*[kKmMbB]?)", re.I)),
    ("impressions", re.compile(r"(?:impresiones|impressions)\s*[:\-]?\s*([\d.,]+\s*[kKmMbB]?)", re.I)),
    ("revenue", re.compile(r"(?:ingresos|revenue|ganancias|earnings)\s*[:\-]?\s*\$?\s*([\d.,]+)", re.I)),
    ("rpm", re.compile(r"(?:rpm)\s*[:\-]?\s*\$?\s*([\d.,]+)", re.I)),
    ("engagement_rate", re.compile(r"(?:engagement|interacci[oó]n|tasa de interacci[oó]n)\s*[:\-]?\s*([\d.,]+)\s*%?", re.I)),
    ("comments", re.compile(r"(?:comentarios|comments)\s*[:\-]?\s*([\d.,]+)", re.I)),
    ("shares", re.compile(r"(?:compartidos|shares)\s*[:\-]?\s*([\d.,]+)", re.I)),
    ("likes", re.compile(r"(?:me gusta|likes|reactions)\s*[:\-]?\s*([\d.,]+)", re.I)),
]


def parse_number(raw: str) -> Optional[float]:
    """Parse numbers like 1.2K, 3,4M, 12.345,67 or 12,345.67."""
    if raw is None:
        return None
    s = str(raw).strip().replace(" ", "").replace("$", "").replace("%", "")
    if not s:
        return None
    multiplier = 1.0
    if s[-1] in "kK":
        multiplier = 1_000.0
        s = s[:-1]
    elif s[-1] in "mM":
        multiplier = 1_000_000.0
        s = s[:-1]
    elif s[-1] in "bB":
        multiplier = 1_000_000_000.0
        s = s[:-1]
    # European vs US decimal
    if "," in s and "." in s:
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s:
        parts = s.split(",")
        if len(parts[-1]) == 2:
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    try:
        return float(s) * multiplier
    except ValueError:
        return None


def extract_metrics_from_text(text: str) -> Dict[str, float]:
    """Pull structured metric values from OCR / plain text."""
    found: Dict[str, float] = {}
    if not text:
        return found
    for name, pattern in _METRIC_PATTERNS:
        m = pattern.search(text)
        if m:
            val = parse_number(m.group(1))
            if val is not None:
                found[name] = val
    # Standalone currency lines
    for m in re.finditer(r"\$\s*([\d.,]+)", text):
        val = parse_number(m.group(1))
        if val is not None and "revenue" not in found:
            found["revenue"] = val
            break
    return found


class FacebookOCRExtractor:
    """Screenshot + OCR pipeline for graphic-only Facebook metrics."""

    def __init__(self, screenshots_dir: Optional[Path] = None):
        self.screenshots_dir = screenshots_dir or get_screenshots_dir()
        self.screenshots_dir.mkdir(parents=True, exist_ok=True)

    def save_screenshot_bytes(self, image_bytes: bytes, label: str = "metric") -> str:
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        safe = re.sub(r"[^a-zA-Z0-9_-]+", "_", label)[:40]
        path = self.screenshots_dir / f"{safe}_{ts}.png"
        path.write_bytes(image_bytes)
        return str(path)

    async def capture_page_screenshot(self, page, label: str = "metric", full_page: bool = False) -> bytes:
        """Capture screenshot from Playwright page. Returns PNG bytes."""
        image_bytes = await page.screenshot(full_page=full_page, type="png")
        self.save_screenshot_bytes(image_bytes, label=label)
        return image_bytes

    def ocr_image_bytes(
        self,
        image_bytes: bytes,
        prompt: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Run OCR via VisionAdapter when available, else CapabilitySelector vision.
        Always attempts regex normalization of returned text.
        """
        prompt = prompt or (
            "Extrae TODAS las métricas numéricas visibles en esta captura de Facebook "
            "Business Suite o Professional Dashboard. "
            "Incluye: seguidores, alcance, visualizaciones, impresiones, ingresos, "
            "RPM, engagement, comentarios, compartidos, me gusta, edad, género, país. "
            "Devuelve cada métrica en formato 'etiqueta: valor' una por línea."
        )

        analysis_text = ""
        model_used = None
        source = "none"

        # Prefer VisionAdapter
        try:
            from src.adapters.vision_adapter import vision_adapter
            result = vision_adapter.analyze_image(
                image_bytes=image_bytes,
                prompt=prompt,
                subtask="ocr",
                system_prompt="Eres un motor OCR preciso para paneles de analytics de Facebook/Meta.",
            )
            if result and result.get("analysis"):
                analysis_text = result["analysis"]
                model_used = result.get("model")
                source = "vision_adapter"
        except Exception as e:
            log.debug("[OCR] VisionAdapter failed: %s", e)

        if not analysis_text:
            try:
                import base64
                from src.providers.capability_selector import capability_selector
                b64 = base64.b64encode(image_bytes).decode("utf-8")
                analysis_text = capability_selector.generate(
                    prompt=prompt,
                    capability="ocr",
                    system_prompt="Eres un motor OCR preciso para métricas de Facebook.",
                    images=[b64],
                )
                source = "capability_selector"
                model_used = "ocr"
            except Exception as e:
                log.warning("[OCR] CapabilitySelector OCR failed: %s", e)
                analysis_text = ""

        # Fallback: try pytesseract if installed and no LLM text
        if not analysis_text or "offline" in analysis_text.lower() or "unreachable" in analysis_text.lower():
            tesseract_text = self._tesseract_ocr(image_bytes)
            if tesseract_text:
                analysis_text = tesseract_text
                source = "pytesseract"
                model_used = "tesseract"

        metrics = extract_metrics_from_text(analysis_text or "")
        return {
            "status": "success" if (analysis_text or metrics) else "empty",
            "raw_text": analysis_text or "",
            "metrics": metrics,
            "model": model_used,
            "source": source,
        }

    def _tesseract_ocr(self, image_bytes: bytes) -> str:
        try:
            import io
            from PIL import Image
            import pytesseract
            img = Image.open(io.BytesIO(image_bytes))
            return pytesseract.image_to_string(img, lang="eng+spa") or ""
        except ImportError:
            return ""
        except Exception as e:
            log.debug("[OCR] tesseract failed: %s", e)
            return ""

    async def extract_from_page(
        self,
        page,
        label: str = "fb_metrics",
        full_page: bool = False,
        extra_prompt: Optional[str] = None,
    ) -> Dict[str, Any]:
        image_bytes = await self.capture_page_screenshot(page, label=label, full_page=full_page)
        result = self.ocr_image_bytes(image_bytes, prompt=extra_prompt)
        result["screenshot_label"] = label
        result["bytes_len"] = len(image_bytes)
        return result

    def normalize_and_merge(
        self,
        *metric_dicts: Dict[str, float],
    ) -> Dict[str, float]:
        """Merge multiple metric dicts; later values override earlier."""
        merged: Dict[str, float] = {}
        for d in metric_dicts:
            if not d:
                continue
            for k, v in d.items():
                if isinstance(v, (int, float)) and not isinstance(v, bool):
                    merged[k] = float(v)
        return merged


facebook_ocr = FacebookOCRExtractor()
