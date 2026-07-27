"""
AnalyticsSpecialist — Autonomous Metrics & Performance Employee (Fase 14.3)
==========================================================================
Data analytics & growth performance tracking:
1. Aggregate campaign metrics (ROAS, CTR, Conversion Rate, Retention)
2. Identify bottlenecks & drop-off points in sales funnels
3. Generate actionable optimization recommendations
"""

import logging
from typing import Dict, Any, Optional
from .base_specialist import BaseSpecialist

log = logging.getLogger("analytics_specialist")


class AnalyticsSpecialist(BaseSpecialist):
    @property
    def specialist_id(self) -> str:
        return "analytics_specialist"

    @property
    def display_name(self) -> str:
        return "Analytics & Performance Specialist"

    @property
    def description(self) -> str:
        return "Autonomous employee for business analytics, ROAS, funnel conversion metrics & growth optimization."

    async def execute_task(
        self,
        task_description: str,
        payload: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        payload = payload or {}
        metrics_data = payload.get("data") or task_description

        self.log_mission("Analyzing business performance metrics")

        from ..providers.capability_selector import capability_selector
        prompt = (
            f"DATOS Y MÉTRICAS DE NEGOCIO:\n{metrics_data}\n\n"
            "Analiza las métricas y entrega un informe ejecutivo:\n"
            "1. Diagnóstico de Rendimiento (Fortalezas y Debilidades)\n"
            "2. Identificación del Cuello de Botella Principal\n"
            "3. 3 Acciones Correctivas de Alto Impacto"
        )
        report = capability_selector.generate(
            prompt=prompt,
            capability="reasoning",
            system_prompt="Eres un Data Scientist y Growth Analyst Senior."
        )

        self.remember_result("Analytics Report", report[:300])

        return {
            "status": "success",
            "specialist": self.specialist_id,
            "tenant_id": self.tenant_id,
            "analytics_report": report,
        }
