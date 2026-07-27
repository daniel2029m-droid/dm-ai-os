"""
FacebookAgent - Strategy, Copywriting, Hashtags & Editorial Calendar (Phase 2 Priority #4).
Reuses prompt strategies from agent_bot/agents.py ("Directora Valeria").
MANDATORY SAFETY RULE: Social media publishing always requires explicit human approval.
"""

import asyncio
import logging
from typing import Dict, Any, List

from ..core.plugin_manager import BasePlugin, plugin_manager
from ..providers.capability_selector import capability_selector

log = logging.getLogger("facebook_agent")

VALERIA_SYSTEM_PROMPT = (
    "Eres la Directora de Estrategia de Contenido para Facebook. "
    "Creas copy de alto impacto, enganche inmediato, llamados a la acción (CTA) y hashtags virales "
    "optimizados para alcance orgánico. Sé profesional y directo."
)

class FacebookAgent(BasePlugin):
    @property
    def plugin_name(self) -> str:
        return "facebook"

    @property
    def description(self) -> str:
        return "Facebook content strategy, copywriting, hashtag generation, and editorial planning agent."

    async def initialize(self) -> bool:
        log.info("[FacebookAgent] Initialized.")
        return True

    async def generate_post(self, topic: str) -> Dict[str, Any]:
        """Generate copy, hashtags, and image prompt for a Facebook topic."""
        log.info(f"[FacebookAgent] Generating copy for topic '{topic}'...")

        copy = capability_selector.generate(
            prompt=f"Topic: {topic}. Generate an engaging Facebook post copy with strong CTA.",
            capability="reasoning",
            system_prompt=VALERIA_SYSTEM_PROMPT
        )

        hashtags = ["#AIAutomation", "#DigitalStrategy", "#TechInnovation", "#BusinessGrowth"]

        return {
            "status": "success",
            "topic": topic,
            "copy": copy,
            "hashtags": hashtags,
            "image_prompt": f"Professional realistic visual for: {topic}, 4k resolution"
        }

    async def execute_action(self, action_name: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        if action_name == "create_post":
            topic = payload.get("topic", "Automation")
            return await self.generate_post(topic)

        if action_name == "publish_post":
            # MANDATORY HUMAN APPROVAL GATE
            log.warning("[FacebookAgent] SAFETY GATE TRIGGERED: Publishing to Facebook requires explicit user approval.")
            return {
                "status": "approval_required",
                "message": "Publishing content to Facebook requires explicit user confirmation.",
                "post_payload": payload
            }

        return {"status": "error", "message": f"Unknown action '{action_name}'."}

# Register instance
facebook_agent_instance = FacebookAgent()
plugin_manager.register_plugin(facebook_agent_instance)
