"""
TikTokSpecialist — Autonomous TikTok Viral Employee (Fase 14.1)
================================================================
Manages TikTok growth & video production:
1. Research viral hooks, audio trends & challenges (Crawl4AI)
2. Scriptwriting with 3-second attention hooks (CapabilitySelector)
3. Video generation & animation payloads (MediaAgent + Grok/RunPod)
4. Automated posting & hashtag strategy (BrowserUseAdapter)
"""

import logging
from typing import Dict, Any, Optional
from .base_specialist import BaseSpecialist

log = logging.getLogger("tiktok_specialist")


class TikTokSpecialist(BaseSpecialist):
    @property
    def specialist_id(self) -> str:
        return "tiktok_specialist"

    @property
    def display_name(self) -> str:
        return "TikTok Viral Specialist"

    @property
    def description(self) -> str:
        return "Autonomous employee for TikTok scripts, 3-second viral hooks, video creation & trend scaling."

    async def execute_task(
        self,
        task_description: str,
        payload: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        payload = payload or {}
        topic = payload.get("topic") or task_description

        self.log_mission(f"Creating TikTok video campaign for: '{topic}'")

        # ── Step 1: Research TikTok Trends ──────────────────────────────────
        from ..agents.research_agent import research_agent_instance
        res = await research_agent_instance.conduct_research(f"tiktok trends viral {topic}")
        trends = res.get("report", "Tendencias de TikTok")

        # ── Step 2: Scriptwriting with Hook ─────────────────────────────────
        from ..providers.capability_selector import capability_selector
        script_prompt = (
            f"Escribe un guion de TikTok de 30 segundos sobre {topic}.\n"
            "Estructura obligatoria:\n"
            "1. HOOK (0-3s): Frase impactante que detenga el scroll.\n"
            "2. DESARROLLO (3-20s): Explicación directa y dinámica.\n"
            "3. CTA (20-30s): Llamado a la acción claro."
        )
        script = capability_selector.generate(
            prompt=script_prompt,
            capability="reasoning",
            system_prompt="Eres un guionista experto de TikTok en español."
        )

        # ── Step 3: Video Payload Generation ─────────────────────────────────
        from ..agents.media_agent import media_agent_instance
        video_payload = await media_agent_instance.generate_video(
            image_filename="tiktok_cover.png",
            prompt=f"Dynamic vertical TikTok video for {topic}, 30 seconds, viral hook"
        )

        self.remember_result("TikTok Video", f"Created 30s TikTok script & video for {topic}")

        return {
            "status": "success",
            "specialist": self.specialist_id,
            "tenant_id": self.tenant_id,
            "topic": topic,
            "script": script,
            "video_payload": video_payload,
        }
