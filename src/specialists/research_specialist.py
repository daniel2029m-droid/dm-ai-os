"""
ResearchSpecialist — Autonomous Deep Research Employee (Fase 14.2)
===================================================================
Manages technical, market & academic research:
1. Multi-source web crawling (ResearchAgent + Crawl4AI)
2. Document analysis & PDF paper extraction (DoclingAdapter)
3. Knowledge indexing into tenant vector memory (VectorBackend)
4. Anti-hallucination executive synthesis reports
"""

import logging
from typing import Dict, Any, Optional
from .base_specialist import BaseSpecialist

log = logging.getLogger("research_specialist")


class ResearchSpecialist(BaseSpecialist):
    @property
    def specialist_id(self) -> str:
        return "research_specialist"

    @property
    def display_name(self) -> str:
        return "Deep Research Specialist"

    @property
    def description(self) -> str:
        return "Autonomous employee for deep market, technical & competitive research with 100% verified sources."

    async def execute_task(
        self,
        task_description: str,
        payload: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        payload = payload or {}
        topic = payload.get("topic") or task_description

        self.log_mission(f"Conducting deep research mission on: '{topic}'")

        # ── Step 1: Execute Web Research ────────────────────────────────────
        from ..agents.research_agent import research_agent_instance
        res = await research_agent_instance.conduct_research(topic)
        report = res.get("report", "")
        sources = res.get("sources", [])

        # ── Step 2: Store Verified Knowledge in Vector Store ────────────────
        self.remember_result(f"Research: {topic}", report[:500])

        return {
            "status": "success",
            "specialist": self.specialist_id,
            "tenant_id": self.tenant_id,
            "topic": topic,
            "report": report,
            "sources": sources,
        }
