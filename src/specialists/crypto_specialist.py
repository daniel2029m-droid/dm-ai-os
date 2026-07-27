"""
CryptoSpecialist — Autonomous Crypto & Financial Market Employee (Fase 14.3)
===========================================================================
Manages cryptocurrency & market intelligence:
1. Crypto news & trend tracking (ResearchAgent + Crawl4AI)
2. Tokenomics & project fundamental analysis (DoclingAdapter)
3. Market sentiment analysis & executive summaries (CapabilitySelector)
"""

import logging
from typing import Dict, Any, Optional
from .base_specialist import BaseSpecialist

log = logging.getLogger("crypto_specialist")


class CryptoSpecialist(BaseSpecialist):
    @property
    def specialist_id(self) -> str:
        return "crypto_specialist"

    @property
    def display_name(self) -> str:
        return "Crypto & Financial Market Specialist"

    @property
    def description(self) -> str:
        return "Autonomous employee for crypto news, market sentiment, tokenomics & fundamental analysis."

    async def execute_task(
        self,
        task_description: str,
        payload: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        payload = payload or {}
        token_or_topic = payload.get("token") or task_description

        self.log_mission(f"Analyzing crypto market trends for: '{token_or_topic}'")

        from ..agents.research_agent import research_agent_instance
        res = await research_agent_instance.conduct_research(f"crypto noticias {token_or_topic}")
        report = res.get("report", "Noticias de crypto")

        self.remember_result(f"Crypto Analysis: {token_or_topic}", report[:400])

        return {
            "status": "success",
            "specialist": self.specialist_id,
            "tenant_id": self.tenant_id,
            "token": token_or_topic,
            "market_report": report,
        }
