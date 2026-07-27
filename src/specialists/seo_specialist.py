"""
SEOSpecialist — Autonomous Search Engine Optimization Employee (Fase 14.2)
========================================================================
Manages technical & content SEO:
1. Keyword research & SERP analysis (ResearchAgent + Crawl4AI)
2. Meta titles, descriptions, H1-H3 structures & JSON-LD schema (CapabilitySelector)
3. Document & landing page SEO audits (DoclingAdapter)
"""

import logging
from typing import Dict, Any, Optional
from .base_specialist import BaseSpecialist

log = logging.getLogger("seo_specialist")


class SEOSpecialist(BaseSpecialist):
    @property
    def specialist_id(self) -> str:
        return "seo_specialist"

    @property
    def display_name(self) -> str:
        return "SEO Optimization Specialist"

    @property
    def description(self) -> str:
        return "Autonomous employee for keyword research, Google ranking, technical SEO & metadata optimization."

    async def execute_task(
        self,
        task_description: str,
        payload: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        payload = payload or {}
        target_site_or_topic = payload.get("target") or task_description

        self.log_mission(f"Executing SEO strategy for: '{target_site_or_topic}'")

        # ── Step 1: SERP & Competitor Keyword Research ──────────────────────
        from ..agents.research_agent import research_agent_instance
        res = await research_agent_instance.conduct_research(f"seo palabras clave {target_site_or_topic}")
        serp_data = res.get("report", "Datos SERP")

        # ── Step 2: Meta Package & Content Structure ─────────────────────────
        from ..providers.capability_selector import capability_selector
        seo_prompt = (
            f"Diseña la estrategia de SEO completa para {target_site_or_topic}.\n"
            "Incluye:\n"
            "- Meta Título (<60 caracteres, palabra clave principal)\n"
            "- Meta Descripción (<155 caracteres, orientada a CTR)\n"
            "- Estructura de Encabezados (H1, H2, H3)\n"
            "- 5 Palabras Clave secundarias de Larga Cola (Long-Tail)"
        )
        seo_plan = capability_selector.generate(
            prompt=seo_prompt,
            capability="reasoning",
            system_prompt="Eres un consultor SEO Senior experto en posicionamiento Google."
        )

        self.remember_result("SEO Plan", f"Created SEO strategy for {target_site_or_topic}")

        return {
            "status": "success",
            "specialist": self.specialist_id,
            "tenant_id": self.tenant_id,
            "target": target_site_or_topic,
            "seo_plan": seo_plan,
            "serp_data_summary": serp_data[:200],
        }
