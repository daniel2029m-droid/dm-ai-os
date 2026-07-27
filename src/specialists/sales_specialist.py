"""
SalesSpecialist — Autonomous Sales & Conversion Employee (Fase 14.2)
====================================================================
Manages sales pipelines & conversion closing:
1. Sales funnel strategy & offer structuring
2. Cold outreach scripts (Email, LinkedIn, WhatsApp, Direct Messages)
3. Objection handling scripts & FAQ responses
4. Closing sequences & lead nurturing
"""

import logging
from typing import Dict, Any, Optional
from .base_specialist import BaseSpecialist

log = logging.getLogger("sales_specialist")


class SalesSpecialist(BaseSpecialist):
    @property
    def specialist_id(self) -> str:
        return "sales_specialist"

    @property
    def display_name(self) -> str:
        return "Sales & Conversion Specialist"

    @property
    def description(self) -> str:
        return "Autonomous employee for sales funnels, closing scripts, objection handling & lead conversion."

    async def execute_task(
        self,
        task_description: str,
        payload: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        payload = payload or {}
        product_or_offer = payload.get("offer") or task_description

        self.log_mission(f"Building sales conversion framework for: '{product_or_offer}'")

        from ..providers.capability_selector import capability_selector
        prompt = (
            f"Crea el manual de ventas y cierre de alta conversión para {product_or_offer}.\n"
            "Incluye:\n"
            "1. Pitch de ventas de 60 segundos (Elevator Pitch)\n"
            "2. Manejo de las 3 objeciones principales ('Está caro', 'Lo voy a pensar', 'No tengo tiempo')\n"
            "3. Script de Cierre Directo por mensaje"
        )
        sales_playbook = capability_selector.generate(
            prompt=prompt,
            capability="reasoning",
            system_prompt="Eres un director de ventas de alto rendimiento especializado en cierres directos."
        )

        self.remember_result("Sales Playbook", f"Created sales conversion playbook for {product_or_offer}")

        return {
            "status": "success",
            "specialist": self.specialist_id,
            "tenant_id": self.tenant_id,
            "offer": product_or_offer,
            "sales_playbook": sales_playbook,
        }
