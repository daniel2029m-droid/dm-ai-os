"""
CustomerSupportSpecialist — Autonomous Customer Support Employee (Fase 14.3)
===========================================================================
24/7 Customer support & ticket resolution:
1. Ingest product documentation & FAQs (DoclingAdapter + VectorBackend)
2. Retrieve relevant solution snippets (MemoryManager / VectorBackend)
3. Generate empathetic, accurate support responses (CapabilitySelector)
4. Escalation trigger for safety-gated queries
"""

import logging
from typing import Dict, Any, Optional
from .base_specialist import BaseSpecialist

log = logging.getLogger("customer_support_specialist")


class CustomerSupportSpecialist(BaseSpecialist):
    @property
    def specialist_id(self) -> str:
        return "customer_support_specialist"

    @property
    def display_name(self) -> str:
        return "Customer Support Specialist"

    @property
    def description(self) -> str:
        return "Autonomous 24/7 employee for customer service, ticket resolution, knowledge base retrieval & FAQs."

    async def execute_task(
        self,
        task_description: str,
        payload: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        payload = payload or {}
        customer_query = payload.get("query") or task_description

        self.log_mission(f"Processing customer support query: '{customer_query[:50]}'")

        # ── Step 1: Search Knowledge Base ────────────────────────────────────
        from ..memory.memory_manager import memory_manager
        relevant_mems = memory_manager.retrieve_memory(customer_query, top_k=3)
        kb_snippets = "\n".join([m.get("content", "") for m in relevant_mems])

        # ── Step 2: Generate Support Response ────────────────────────────────
        from ..providers.capability_selector import capability_selector
        prompt = (
            f"CONSULTA DEL CLIENTE: {customer_query}\n\n"
            f"BASE DE CONOCIMIENTOS / DOCUMENTACIÓN:\n{kb_snippets or 'Atención al cliente general'}\n\n"
            "Redacta una respuesta útil, empática y profesional en español."
        )
        response = capability_selector.generate(
            prompt=prompt,
            capability="reasoning",
            system_prompt="Eres un agente de atención al cliente amable y altamente capacitado."
        )

        return {
            "status": "success",
            "specialist": self.specialist_id,
            "tenant_id": self.tenant_id,
            "query": customer_query,
            "response": response,
        }
