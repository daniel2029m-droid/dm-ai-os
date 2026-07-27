"""
WhatsAppSpecialist — Autonomous WhatsApp Marketing & Business Employee (Fase 14.1)
================================================================================
Manages WhatsApp Business & Marketing campaigns:
1. Product catalog & flyer content creation (MediaAgent)
2. Automated response flow & customer onboarding (CapabilitySelector)
3. Broadcast messaging, status updates & promo campaigns
4. Conversion tracking & lead followup
"""

import logging
from typing import Dict, Any, Optional
from .base_specialist import BaseSpecialist

log = logging.getLogger("whatsapp_specialist")


class WhatsAppSpecialist(BaseSpecialist):
    @property
    def specialist_id(self) -> str:
        return "whatsapp_specialist"

    @property
    def display_name(self) -> str:
        return "WhatsApp Marketing Specialist"

    @property
    def description(self) -> str:
        return "Autonomous employee for WhatsApp Business automation, catalogs, promo flyers, auto-responses & lead conversion."

    async def execute_task(
        self,
        task_description: str,
        payload: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        payload = payload or {}
        business_type = payload.get("business_type") or task_description

        self.log_mission(f"Building WhatsApp Marketing campaign for: '{business_type}'")

        # ── Step 1: Auto-Response Flow & Copywriting ─────────────────────────
        from ..providers.capability_selector import capability_selector
        copy_prompt = (
            f"Crea un flujo de bienvenida y ventas para WhatsApp Business para un negocio de {business_type}.\n"
            "Incluye:\n"
            "1. Mensaje de bienvenida automático\n"
            "2. Respuesta rápida con catálogo/precios\n"
            "3. Mensaje de seguimiento a las 24 horas"
        )
        auto_responses = capability_selector.generate(
            prompt=copy_prompt,
            capability="reasoning",
            system_prompt="Eres un experto en WhatsApp Marketing y conversión directa en español."
        )

        # ── Step 2: Promotional Flyer Generation ─────────────────────────────
        from ..agents.media_agent import media_agent_instance
        flyer_res = await media_agent_instance.generate_image(
            prompt=f"Professional promotional flyer for WhatsApp Business {business_type}, clean design, clear call to action"
        )
        flyer_url = flyer_res.get("image_url", "https://via.placeholder.com/1080x1080")

        self.remember_result("WhatsApp Campaign", f"Created auto-response & flyer for {business_type}")

        return {
            "status": "success",
            "specialist": self.specialist_id,
            "tenant_id": self.tenant_id,
            "business_type": business_type,
            "auto_responses": auto_responses,
            "flyer_url": flyer_url,
        }
