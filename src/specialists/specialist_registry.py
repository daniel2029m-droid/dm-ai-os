"""
SpecialistRegistry — Central Hub for Digital Employees (Fase 14.1)
===================================================================
Registers and orchestrates all 20 Autonomous Business Specialist Workers.
Allows natural-language intent routing to match user goals to the right specialist.
"""

import logging
from typing import Dict, Any, List, Optional, Type
from .base_specialist import BaseSpecialist

log = logging.getLogger("specialist_registry")


class SpecialistRegistry:
    """Registry holding all active digital employee specialists."""

    def __init__(self):
        self._specialists: Dict[str, BaseSpecialist] = {}

    def register(self, specialist: BaseSpecialist):
        """Register a specialist instance."""
        self._specialists[specialist.specialist_id] = specialist
        log.info(f"[SpecialistRegistry] Registered worker: '{specialist.display_name}' ({specialist.specialist_id})")

    def get_specialist(self, specialist_id: str) -> Optional[BaseSpecialist]:
        """Retrieve specialist by ID."""
        return self._specialists.get(specialist_id)

    def list_specialists(self) -> List[Dict[str, str]]:
        """List all available digital employees."""
        return [
            {
                "id": s.specialist_id,
                "name": s.display_name,
                "description": s.description,
            }
            for s in self._specialists.values()
        ]

    def route_mission(self, user_goal: str) -> Optional[BaseSpecialist]:
        """
        Keyword-based intent routing to pick the best digital employee for a mission.
        """
        goal_lower = user_goal.lower()

        keywords = {
            "facebook": "facebook_specialist",
            "instagram": "instagram_specialist",
            "tiktok": "tiktok_specialist",
            "youtube": "youtube_specialist",
            "fanvue": "fanvue_specialist",
            "valeria": "fanvue_specialist",
            "montesano": "fanvue_specialist",
            "whatsapp": "whatsapp_specialist",
            "seo": "seo_specialist",
            "investiga": "research_specialist",
            "contenido": "content_specialist",
            "ads": "ads_specialist",
            "publicidad": "ads_specialist",
            "anuncios": "ads_specialist",
            "crypto": "crypto_specialist",
            "soporte": "customer_support_specialist",
            "atencion": "customer_support_specialist",
            "educacion": "education_specialist",
            "trabajo": "education_specialist",
            "negocio": "local_business_specialist",
            "emprendimiento": "business_specialist",
            "electricista": "local_business_specialist",
            "analytics": "analytics_specialist",
            "metricas": "analytics_specialist",
            "automatiza": "automation_specialist",
            "ventas": "sales_specialist",
            "curso": "course_builder_specialist",
            "workflow": "workflow_specialist",
        }

        for kw, spec_id in keywords.items():
            if kw in goal_lower:
                if spec_id in self._specialists:
                    log.info(f"[SpecialistRegistry] Routed goal '{user_goal[:40]}' -> '{spec_id}'")
                    return self._specialists[spec_id]

        # Default fallback: business_specialist if registered
        return self._specialists.get("business_specialist") or list(self._specialists.values())[0] if self._specialists else None


# Module-level singleton
specialist_registry = SpecialistRegistry()
