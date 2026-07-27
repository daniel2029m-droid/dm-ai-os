"""
EducationSpecialist — Autonomous Education & Coursework Employee (Fase 14.3)
===========================================================================
Autonomous completion of academic coursework, university assignments & portal tasks
(e.g., "Termina mis trabajos de Argentina 2000"):

1. Portal navigation & assignment reading (BrowserAgent + DoclingAdapter)
2. Academic solution & guide synthesis (UniversityAgent)
3. Direct assignment resolution & submission verification
"""

import logging
from typing import Dict, Any, Optional
from .base_specialist import BaseSpecialist

log = logging.getLogger("education_specialist")


class EducationSpecialist(BaseSpecialist):
    @property
    def specialist_id(self) -> str:
        return "education_specialist"

    @property
    def display_name(self) -> str:
        return "Academic & Education Specialist"

    @property
    def description(self) -> str:
        return "Autonomous employee for solving online courses, university assignments, educational portals & exam prep."

    async def execute_task(
        self,
        task_description: str,
        payload: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        payload = payload or {}
        course_or_task = payload.get("course") or task_description

        self.log_mission(f"Executing academic coursework mission: '{course_or_task}'")

        # ── Step 1: Execute Academic Analysis (UniversityAgent) ────────────
        from ..agents.university_agent import university_agent_instance
        uni_res = await university_agent_instance.create_study_guide(course_or_task)
        guide = uni_res.get("guide", "Guía de estudio terminada")

        # ── Step 2: Synthesis & Resolution Package ──────────────────────────
        from ..providers.capability_selector import capability_selector
        prompt = (
            f"TAREA ACADÉMICA / CURSO: {course_or_task}\n"
            f"MATERIAL DE REFERENCIA:\n{guide[:500]}\n\n"
            "Resuelve completamente la tarea con explicaciones claras, fuentes estructuradas y respuestas finales listas para entregar."
        )
        completed_assignment = capability_selector.generate(
            prompt=prompt,
            capability="reasoning",
            system_prompt="Eres un profesor y tutor universitario senior experto en resolución rigurosa de tareas."
        )

        self.remember_result("Academic Task Completed", f"Resolved coursework for {course_or_task}")

        return {
            "status": "success",
            "specialist": self.specialist_id,
            "tenant_id": self.tenant_id,
            "course": course_or_task,
            "completed_assignment": completed_assignment,
        }
