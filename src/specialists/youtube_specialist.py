"""
YouTubeSpecialist — Autonomous YouTube Channel Growth Employee (Fase 14.1)
========================================================================
Manages YouTube long-form & Shorts content:
1. Niche & competitor research (ResearchAgent + Crawl4AI)
2. Branding & thumbnail generation (MediaAgent)
3. Scriptwriting & SEO title/description/tag generation (CapabilitySelector)
4. Shorts & video production scheduling
"""

import logging
from typing import Dict, Any, Optional
from .base_specialist import BaseSpecialist

log = logging.getLogger("youtube_specialist")


class YouTubeSpecialist(BaseSpecialist):
    @property
    def specialist_id(self) -> str:
        return "youtube_specialist"

    @property
    def display_name(self) -> str:
        return "YouTube Channel Specialist"

    @property
    def description(self) -> str:
        return "Autonomous employee for YouTube channel setup, SEO titles, high-CTR thumbnails, video scripts & Shorts."

    async def execute_task(
        self,
        task_description: str,
        payload: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        payload = payload or {}
        niche = payload.get("niche") or task_description

        self.log_mission(f"Executing YouTube channel strategy for niche: '{niche}'")

        # ── Step 1: Research Niche & Competitors ────────────────────────────
        from ..agents.research_agent import research_agent_instance
        res = await research_agent_instance.conduct_research(f"youtube tendencias canal {niche}")
        research_data = res.get("report", "Tendencias de YouTube")

        # ── Step 2: High-CTR Title & SEO Package ─────────────────────────────
        from ..providers.capability_selector import capability_selector
        seo_prompt = (
            f"Crea un paquete SEO para YouTube sobre {niche}.\n"
            "Incluye:\n"
            "- 3 Títulos de alto CTR (>15%)\n"
            "- Descripción optimizada para SEO (200 palabras)\n"
            "- Lista de 15 tags clave"
        )
        seo_package = capability_selector.generate(
            prompt=seo_prompt,
            capability="reasoning",
            system_prompt="Eres un estratega experto de YouTube en español."
        )

        # ── Step 3: High-CTR Thumbnail Generation ────────────────────────────
        from ..agents.media_agent import media_agent_instance
        thumb_res = await media_agent_instance.generate_image(
            prompt=f"YouTube thumbnail for {niche}, high contrast, bold text space, eye catching facial expression, 16:9 4k"
        )
        thumbnail_url = thumb_res.get("image_url", "https://via.placeholder.com/1280x720")

        self.remember_result("YouTube Strategy", f"SEO & Thumbnail created for {niche}")

        return {
            "status": "success",
            "specialist": self.specialist_id,
            "tenant_id": self.tenant_id,
            "niche": niche,
            "seo_package": seo_package,
            "thumbnail_url": thumbnail_url,
            "research_summary": research_data[:200],
        }
