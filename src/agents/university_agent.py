"""
UniversityAgent - Academic Tutoring, Study Guides & Concept Explanation (Phase 2 Priority #5).
Uses CapabilityModelSelector for academic reasoning, problem breakdown, and study guide structuring.
"""

import asyncio
import logging
from typing import Dict, Any, List

from ..core.plugin_manager import BasePlugin, plugin_manager
from ..providers.capability_selector import capability_selector

log = logging.getLogger("university_agent")

ACADEMIC_SYSTEM_PROMPT = (
    "You are a Senior University Professor and Academic Tutor. "
    "Explain complex subjects clearly using structured breakdowns, examples, and key formulas or definitions."
)

class UniversityAgent(BasePlugin):
    @property
    def plugin_name(self) -> str:
        return "university"

    @property
    def description(self) -> str:
        return "Academic tutoring, course study guides, exam preparation, and complex concept breakdown agent."

    async def initialize(self) -> bool:
        log.info("[UniversityAgent] Initialized.")
        return True

    async def explain_concept(self, concept: str) -> Dict[str, Any]:
        log.info(f"[UniversityAgent] Explaining concept: '{concept}'...")
        explanation = capability_selector.generate(
            prompt=f"Explain the academic concept '{concept}' for a university student. Include intuition, formal definition, and practical application.",
            capability="reasoning",
            system_prompt=ACADEMIC_SYSTEM_PROMPT
        )
        return {"status": "success", "concept": concept, "explanation": explanation}

    async def create_study_guide(self, subject: str) -> Dict[str, Any]:
        log.info(f"[UniversityAgent] Creating study guide for: '{subject}'...")
        guide = capability_selector.generate(
            prompt=f"Create a structured university-level study guide for '{subject}'. Include core topics, key terms, and self-test questions.",
            capability="summarization",
            system_prompt=ACADEMIC_SYSTEM_PROMPT
        )
        return {"status": "success", "subject": subject, "guide": guide}

    async def execute_action(self, action_name: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        if action_name == "explain_concept":
            concept = payload.get("concept", "Computer Science")
            return await self.explain_concept(concept)

        if action_name == "create_study_guide":
            subject = payload.get("subject", "Mathematics")
            return await self.create_study_guide(subject)

        return {"status": "error", "message": f"Unknown action '{action_name}'."}

# Register instance
university_agent_instance = UniversityAgent()
plugin_manager.register_plugin(university_agent_instance)
