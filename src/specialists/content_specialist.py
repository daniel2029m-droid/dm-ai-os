"""
ContentSpecialist — Autonomous Content Creator & Copywriter (Fase 14.2)
========================================================================
Manages omnichannel content creation:
1. Editorial calendars & content strategy
2. Long-form blog posts & email newsletters (CapabilitySelector + Docling)
3. Micro-copy for social media (Facebook, Instagram, TikTok, LinkedIn)
4. Visual asset generation (MediaAgent)
"""

import logging
from typing import Dict, Any, Optional
from .base_specialist import BaseSpecialist

log = logging.getLogger("content_specialist")


class ContentSpecialist(BaseSpecialist):
    @property
    def specialist_id(self) -> str:
        return "content_specialist"

    @property
    def display_name(self) -> str:
        return "Omnichannel Content Specialist"

    @property
    def description(self) -> str:
        return "Autonomous employee for blog posts, newsletters, social copy & editorial calendar management."

    async def execute_task(
        self,
        task_description: str,
        payload: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        payload = payload or {}
        topic = payload.get("topic") or task_description

        self.log_mission(f"Creating content package for: '{topic}'")

        # ── Step 1: Long-Form Article & Social Copy ─────────────────────────
        from ..providers.capability_selector import capability_selector
        prompt = (
            f"Escribe un artículo completo de blog (800 palabras) sobre {topic}.\n"
            "Incluye un resumen ejecutivo y 3 publicaciones cortas adaptadas para redes sociales."
        )
        content_body = capability_selector.generate(
            prompt=prompt,
            capability="reasoning",
            system_prompt="Eres un redactor y estratega de contenido senior."
        )

        # ── Step 2: Featured Image ───────────────────────────────────────────
        from ..agents.media_agent import media_agent_instance
        media_res = await media_agent_instance.generate_image(
            prompt=f"Featured blog post illustration for {topic}, modern digital artwork"
        )
        featured_img = media_res.get("image_url", "https://via.placeholder.com/1200x630")

        self.remember_result("Content Package", f"Created blog & social content for {topic}")

        return {
            "status": "success",
            "specialist": self.specialist_id,
            "tenant_id": self.tenant_id,
            "topic": topic,
            "content": content_body,
            "image_url": featured_img,
        }
