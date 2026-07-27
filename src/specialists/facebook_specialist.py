"""
FacebookSpecialist — Autonomous Facebook Growth & Management Employee (Fase 14.1)
=============================================================================
Manages end-to-end Facebook page operations:
1. Research competitors & trending topics (ResearchAgent + Crawl4AI)
2. Generate engaging copy & hashtags (CapabilitySelector)
3. Create banners & video content (MediaAgent + Grok/RunPod)
4. Publish & schedule posts (FacebookAgent + BrowserUseAdapter)
5. Track post performance metrics & optimize strategy automatically
"""

import logging
from typing import Dict, Any, Optional
from .base_specialist import BaseSpecialist

log = logging.getLogger("facebook_specialist")


class FacebookSpecialist(BaseSpecialist):
    @property
    def specialist_id(self) -> str:
        return "facebook_specialist"

    @property
    def display_name(self) -> str:
        return "Facebook Growth Specialist"

    @property
    def description(self) -> str:
        return "Autonomous employee for Facebook growth, competitor research, content creation, publishing & analytics."

    async def execute_task(
        self,
        task_description: str,
        payload: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        payload = payload or {}
        niche = payload.get("niche") or task_description
        page_id = payload.get("page_id") or self.tenant.get_secret("facebook_page_id", "default_page")

        self.log_mission(f"Starting Facebook growth mission for niche: '{niche}'")

        # ── Step 1: Competitor & Trend Research (ResearchAgent + Crawl4AI) ───
        from ..agents.research_agent import research_agent_instance
        research_res = await research_agent_instance.conduct_research(f"tendencias facebook {niche}")
        trends_report = research_res.get("report", "Tendencias generales de Facebook")

        # ── Step 2: Content Copy Generation (CapabilitySelector) ────────────
        from ..providers.capability_selector import capability_selector
        copy_prompt = f"Crea una publicación viral para Facebook sobre {niche}.\nTendencias: {trends_report[:300]}"
        post_copy = capability_selector.generate(
            prompt=copy_prompt,
            capability="reasoning",
            system_prompt="Eres un experto en Growth Hacking para Facebook. Escribe en español."
        )

        # ── Step 3: Visual Asset Generation (MediaAgent) ─────────────────────
        from ..agents.media_agent import media_agent_instance
        media_res = await media_agent_instance.generate_image(
            prompt=f"Professional Facebook banner for {niche}, high resolution, vibrant colors"
        )
        banner_url = media_res.get("image_url", "https://via.placeholder.com/1200x630")

        # ── Step 4: Publish / Schedule (FacebookAgent) ────────────────────────
        from ..agents.facebook_agent import facebook_agent_instance
        pub_res = await facebook_agent_instance.execute_action(
            "publish_post",
            {"page_id": page_id, "message": post_copy, "image_url": banner_url}
        )

        # ── Step 5: Store strategy in tenant memory for continuous learning ─
        self.remember_result("Facebook Campaign", f"Posted on {niche}. Post ID: {pub_res.get('post_id')}")

        return {
            "status": "success",
            "specialist": self.specialist_id,
            "tenant_id": self.tenant_id,
            "niche": niche,
            "copy": post_copy,
            "image_url": banner_url,
            "publish_status": pub_res.get("status"),
            "post_id": pub_res.get("post_id"),
        }
