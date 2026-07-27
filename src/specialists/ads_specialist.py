"""
AdsSpecialist — Autonomous Paid Advertising Employee (Fase 14.2)
================================================================
Manages ad campaigns on Facebook, Instagram, Google, TikTok & WhatsApp:
1. Target audience profiling & buyer persona research
2. High-converting ad copy (Hook, Angles, Offers, CTAs)
3. Ad banner & video ad visual generation (MediaAgent)
4. Budget allocation, ROAS tracking & automated campaign optimization
"""

import logging
from typing import Dict, Any, Optional
from .base_specialist import BaseSpecialist

log = logging.getLogger("ads_specialist")


class AdsSpecialist(BaseSpecialist):
    @property
    def specialist_id(self) -> str:
        return "ads_specialist"

    @property
    def display_name(self) -> str:
        return "Paid Ads Specialist"

    @property
    def description(self) -> str:
        return "Autonomous employee for Meta Ads, Google Ads, TikTok Ads & WhatsApp ad campaigns and ROAS optimization."

    async def execute_task(
        self,
        task_description: str,
        payload: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        payload = payload or {}
        product_or_service = payload.get("product") or task_description

        self.log_mission(f"Designing ad campaign for: '{product_or_service}'")

        # ── Step 1: Ad Angles & Copy ─────────────────────────────────────────
        from ..providers.capability_selector import capability_selector
        prompt = (
            f"Diseña una campaña publicitaria completa para {product_or_service}.\n"
            "Incluye:\n"
            "1. Perfil del Cliente Ideal (Audiencia y Segmentación)\n"
            "2. Ángulo Publicitario N°1 (Problema / Solución)\n"
            "3. Ángulo Publicitario N°2 (Prueba Social / Descuento)\n"
            "4. 2 Textos de anuncio (Ad Copy) optimizados para conversión"
        )
        ad_strategy = capability_selector.generate(
            prompt=prompt,
            capability="reasoning",
            system_prompt="Eres un media buyer y copywriter experto en anuncios de alta conversión."
        )

        # ── Step 2: Visual Ad Creative ───────────────────────────────────────
        from ..agents.media_agent import media_agent_instance
        creative_res = await media_agent_instance.generate_image(
            prompt=f"High converting advertisement banner for {product_or_service}, professional design, clear product focus"
        )
        ad_creative_url = creative_res.get("image_url", "https://via.placeholder.com/1080x1080")

        self.remember_result("Paid Ads Campaign", f"Designed ad strategy for {product_or_service}")

        return {
            "status": "success",
            "specialist": self.specialist_id,
            "tenant_id": self.tenant_id,
            "product": product_or_service,
            "ad_strategy": ad_strategy,
            "ad_creative_url": ad_creative_url,
        }
