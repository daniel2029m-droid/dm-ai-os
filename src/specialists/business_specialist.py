"""
BusinessSpecialist — Autonomous Business Strategy & Scaling Employee (Fase 14.3)
=============================================================================
Executive strategy & business architecture:
1. Business plan & lean canvas generation (CapabilitySelector)
2. Competitive benchmark & pricing strategy (ResearchAgent + Crawl4AI)
3. Operational scaling & workflow roadmap
"""

import logging
from typing import Dict, Any, Optional
from .base_specialist import BaseSpecialist

log = logging.getLogger("business_specialist")


class BusinessSpecialist(BaseSpecialist):
    @property
    def specialist_id(self) -> str:
        return "business_specialist"

    @property
    def display_name(self) -> str:
        return "Business Strategy & Executive Specialist"

    @property
    def description(self) -> str:
        return "Autonomous employee for business plans, revenue models, market scaling & executive operations."

    async def execute_task(
        self,
        task_description: str,
        payload: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        payload = payload or {}
        business_goal = payload.get("goal") or task_description

        self.log_mission(f"Building executive business strategy for: '{business_goal}'")

        from ..providers.capability_selector import capability_selector
        prompt = (
            f"Diseña el plan estratégico ejecutivo completo para: {business_goal}.\n"
            "Incluye:\n"
            "1. Modelo de Negocio y Flujos de Ingreso\n"
            "2. Estructura de Costos y Margen Objetivo\n"
            "3. Roadmap de Ejecución a 30, 60 y 90 días\n"
            "4. KPIs Clave de Desempeño"
        )
        executive_plan = capability_selector.generate(
            prompt=prompt,
            capability="reasoning",
            system_prompt="Eres un consultor ejecutivo de McKinsey / BCG especializado en aceleración de negocios."
        )

        self.remember_result("Executive Strategy", f"Created business plan for {business_goal}")

        return {
            "status": "success",
            "specialist": self.specialist_id,
            "tenant_id": self.tenant_id,
            "goal": business_goal,
            "executive_plan": executive_plan,
        }
