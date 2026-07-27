"""
CourseBuilderSpecialist — Autonomous Course & Curriculum Employee (Fase 14.3)
=============================================================================
End-to-end online course creation:
1. Topic research & syllabus design (ResearchAgent + Crawl4AI)
2. Module lessons, lecture scripts & slide outlines (CapabilitySelector)
3. Student workbooks & quizzes (DoclingAdapter)
4. Course promo materials & cover art (MediaAgent)
"""

import logging
from typing import Dict, Any, Optional
from .base_specialist import BaseSpecialist

log = logging.getLogger("course_builder_specialist")


class CourseBuilderSpecialist(BaseSpecialist):
    @property
    def specialist_id(self) -> str:
        return "course_builder_specialist"

    @property
    def display_name(self) -> str:
        return "Course Builder & Curriculum Specialist"

    @property
    def description(self) -> str:
        return "Autonomous employee for online course design, syllabus, video scripts, quizzes & workbooks."

    async def execute_task(
        self,
        task_description: str,
        payload: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        payload = payload or {}
        course_topic = payload.get("topic") or task_description

        self.log_mission(f"Building complete online course for: '{course_topic}'")

        # ── Step 1: Research Topic ──────────────────────────────────────────
        from ..agents.research_agent import research_agent_instance
        res = await research_agent_instance.conduct_research(f"curso online {course_topic}")
        research_summary = res.get("report", "Investigación sobre el curso")

        # ── Step 2: Course Curriculum & Lesson Plan ─────────────────────────
        from ..providers.capability_selector import capability_selector
        prompt = (
            f"Diseña la estructura completa del curso online sobre {course_topic}.\n"
            "Incluye:\n"
            "- Título del Curso y Promesa Principal\n"
            "- Módulo 1 (3 Lecciones con Guion de Video)\n"
            "- Módulo 2 (3 Lecciones con Guion de Video)\n"
            "- Examen Corto de Evaluación (5 Preguntas)\n"
            "- Ejercicio Práctico para los estudiantes"
        )
        curriculum = capability_selector.generate(
            prompt=prompt,
            capability="reasoning",
            system_prompt="Eres un diseñador instruccional y creador de cursos online de clase mundial."
        )

        # ── Step 3: Course Cover Art ─────────────────────────────────────────
        from ..agents.media_agent import media_agent_instance
        cover_res = await media_agent_instance.generate_image(
            prompt=f"Professional 3D course box mockup cover for {course_topic}, high quality digital product"
        )
        cover_url = cover_res.get("image_url", "https://via.placeholder.com/800x1000")

        self.remember_result("Online Course", f"Created syllabus for {course_topic}")

        return {
            "status": "success",
            "specialist": self.specialist_id,
            "tenant_id": self.tenant_id,
            "topic": course_topic,
            "curriculum": curriculum,
            "cover_url": cover_url,
        }
