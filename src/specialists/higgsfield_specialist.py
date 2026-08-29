"""
HiggsfieldSpecialist — Specialist de Media para Valeria Montesano Digital
=========================================================================
Digital employee especializado en generación de imágenes y videos con
el personaje entrenado de Valeria Montesano (Soul / Soul 2, Seedance 2.0).

Flujo completo:
  1. Detectar tipo de generación (imagen/video)
  2. Seleccionar modelo según tipo (Soul 2 / Seedance 2.0)
  3. Aplicar aspect ratio 9:16 y estilos de marca
  4. Generar con personaje configurado (HIGGSFIELD_CHARACTER_ID)
  5. Monitorear job hasta completar
  6. Guardar en historial de generaciones
  7. Guardar memoria del resultado
  8. Retornar asset final

Proyecto:    Valeria Montesano Digital
Personaje:   Mi Influencer
Imagen:      Soul 2
Video:       Seedance 2.0
Formato:     9:16
Estilo:      Luxury lifestyle, Photorealistic, Premium cinematic,
             Facebook-safe, Advertiser-friendly
"""

import logging
import os
from typing import Dict, Any, Optional

from .base_specialist import BaseSpecialist
from ..adapters.higgsfield_adapter import higgsfield_adapter

log = logging.getLogger("higgsfield_specialist")

# Lazy-import para evitar circularidades en tests
try:
    from ..config.higgsfield_config import higgsfield_config as _cfg
except ImportError:
    _cfg = None

try:
    from ..providers.higgsfield_generation_history import higgsfield_history as _history
except ImportError:
    _history = None


class HiggsfieldSpecialist(BaseSpecialist):
    """
    Specialist de Higgsfield AI para el proyecto Valeria Montesano Digital.
    Genera imágenes y videos con el personaje entrenado usando Soul 2 / Seedance 2.0.
    """

    @property
    def specialist_id(self) -> str:
        return "higgsfield_specialist"

    @property
    def display_name(self) -> str:
        return "Higgsfield AI Video & Media Specialist"

    @property
    def description(self) -> str:
        return (
            "Specialized Digital Employee for cinematic AI video generation, "
            "text-to-video, image-to-video animation, and visual media synthesis "
            "powered by Higgsfield AI MCP Connector (https://mcp.higgsfield.ai/mcp). "
            "Proyecto: Valeria Montesano Digital — Soul 2 / Seedance 2.0 / 9:16."
        )

    # ── Propiedades del proyecto activo ───────────────────────

    @property
    def _character_id(self) -> Optional[str]:
        """Character ID del personaje activo (desde config o env var)."""
        if _cfg and _cfg.has_character:
            return _cfg.character_id
        return os.getenv("HIGGSFIELD_CHARACTER_ID")

    @property
    def _default_image_model(self) -> str:
        return _cfg.default_image_model if _cfg else "soul_2"

    @property
    def _default_video_model(self) -> str:
        return _cfg.default_video_model if _cfg else "seedance_2_0"

    @property
    def _default_aspect_ratio(self) -> str:
        return _cfg.default_aspect_ratio if _cfg else "9:16"

    @property
    def _project_name(self) -> str:
        return _cfg.project_name if _cfg else "Valeria Montesano Digital"

    @property
    def _character_name(self) -> str:
        return _cfg.character_name if _cfg else "Mi Influencer"

    # ── Flujo principal ────────────────────────────────────────

    async def execute_task(
        self,
        task_description: str,
        payload: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Ejecuta una tarea de generación multimedia.

        DM AI OS llama este método cuando el usuario solicita:
        "Crear imagen de Valeria en un rooftop de Buenos Aires"
        "Generar video de Valeria caminando en Palermo"

        Flujo:
          1. Determinar tipo: imagen o video
          2. Seleccionar modelo automáticamente
          3. Generar con personaje si está configurado
          4. Monitorear job hasta completar
          5. Guardar en historial
          6. Guardar en memoria del sistema
          7. Retornar asset final
        """
        payload = payload or {}

        # Parámetros de la tarea
        prompt = payload.get("prompt", task_description)
        image_url = payload.get("image_url")
        duration = payload.get("duration", 5)
        aspect_ratio = payload.get("aspect_ratio", self._default_aspect_ratio)
        model = payload.get("model")
        character_id = payload.get("character_id", self._character_id)
        enrich_style = payload.get("enrich_style", True)

        # Detectar tipo de generación
        task_low = task_description.lower()
        mode = payload.get("mode", "")
        is_video = (
            mode == "generate_video" or
            any(w in task_low for w in [
                "video", "animacion", "animar", "movimiento", "clip",
                "anima", "mueve", "genera video", "crea video", "movie"
            ])
        )
        is_image_to_video = (
            mode == "image_to_video" or
            (image_url and ("animar" in task_low or "anima" in task_low))
        )

        self.log_mission(
            f"Task: {task_description[:80]!r} | "
            f"tipo={'video' if (is_video or is_image_to_video) else 'imagen'} | "
            f"character_id={character_id!r} | "
            f"proyecto={self._project_name}"
        )

        # ── Selección de método de generación ──────────────────

        if is_image_to_video and image_url:
            # Image-to-video: animar imagen estática
            res = await self._generate_image_to_video(
                prompt=prompt,
                image_url=image_url,
                character_id=character_id,
                duration=duration,
                aspect_ratio=aspect_ratio,
                model=model,
            )
        elif is_video:
            # Text-to-video
            res = await self._generate_video(
                prompt=prompt,
                character_id=character_id,
                duration=duration,
                aspect_ratio=aspect_ratio,
                model=model,
                enrich_style=enrich_style,
            )
        else:
            # Text-to-image (default)
            res = await self._generate_image(
                prompt=prompt,
                character_id=character_id,
                aspect_ratio=aspect_ratio,
                model=model,
                enrich_style=enrich_style,
            )

        # ── Guardar historial y memoria ────────────────────────

        media_type = res.get("media_type", "unknown")
        output_url = res.get("image_url") or res.get("video_url") or ""
        job_id = res.get("job_id", "")

        summary = (
            f"[{self._project_name}] {media_type.capitalize()} generado | "
            f"job={job_id} | model={res.get('model')} | url={output_url}"
        )
        self.remember_result(task_description, summary)

        self.log_mission(f"✅ Completado: {media_type} | job_id={job_id} | url={output_url}")

        return {
            "status": "success",
            "specialist": self.display_name,
            "tenant_id": self.tenant_id,
            "mission": task_description,
            "project": self._project_name,
            "character": self._character_name,
            "character_id": character_id,
            "media_type": media_type,
            "job_id": job_id,
            "output_url": output_url,
            "model": res.get("model"),
            "aspect_ratio": res.get("aspect_ratio", aspect_ratio),
            "higgsfield_result": res,
            "mcp_url": higgsfield_adapter.mcp_url,
        }

    # ── Métodos internos de generación ────────────────────────

    async def _generate_image(
        self,
        prompt: str,
        character_id: Optional[str],
        aspect_ratio: str,
        model: Optional[str],
        enrich_style: bool,
    ) -> Dict[str, Any]:
        """Genera imagen — con personaje si está configurado."""
        _model = model or self._default_image_model
        if character_id:
            self.log_mission(f"Generando imagen con personaje: model={_model}, ratio={aspect_ratio}")
            return await higgsfield_adapter.generate_image_with_character(
                prompt=prompt,
                character_id=character_id,
                model=_model,
                aspect_ratio=aspect_ratio,
                enrich_style=enrich_style,
            )
        else:
            self.log_mission(f"Generando imagen sin personaje: model={_model}, ratio={aspect_ratio}")
            return await higgsfield_adapter.generate_image(
                prompt=prompt,
                model=_model,
                aspect_ratio=aspect_ratio,
            )

    async def _generate_video(
        self,
        prompt: str,
        character_id: Optional[str],
        duration: int,
        aspect_ratio: str,
        model: Optional[str],
        enrich_style: bool,
    ) -> Dict[str, Any]:
        """Genera video — con personaje si está configurado."""
        _model = model or self._default_video_model
        if character_id:
            self.log_mission(f"Generando video con personaje: model={_model}, ratio={aspect_ratio}, duration={duration}s")
            return await higgsfield_adapter.generate_video_with_character(
                prompt=prompt,
                character_id=character_id,
                model=_model,
                aspect_ratio=aspect_ratio,
                duration=duration,
                enrich_style=enrich_style,
            )
        else:
            self.log_mission(f"Generando video sin personaje: model={_model}, ratio={aspect_ratio}")
            return await higgsfield_adapter.generate_video(
                prompt=prompt,
                model=_model,
                aspect_ratio=aspect_ratio,
                duration=duration,
            )

    async def _generate_image_to_video(
        self,
        prompt: str,
        image_url: str,
        character_id: Optional[str],
        duration: int,
        aspect_ratio: str,
        model: Optional[str],
    ) -> Dict[str, Any]:
        """Anima una imagen estática a video."""
        _model = model or self._default_video_model
        self.log_mission(f"Animando imagen a video: model={_model}, ratio={aspect_ratio}")
        if character_id:
            return await higgsfield_adapter.generate_video_with_character(
                prompt=prompt,
                character_id=character_id,
                model=_model,
                aspect_ratio=aspect_ratio,
                duration=duration,
                image_url=image_url,
                enrich_style=False,  # No enriquecer en image-to-video
            )
        return await higgsfield_adapter.image_to_video(
            image_url=image_url,
            prompt=prompt,
            model=_model,
            duration=duration,
            aspect_ratio=aspect_ratio,
        )

    # ── API pública extendida ──────────────────────────────────

    async def list_characters(self) -> list:
        """Lista los personajes entrenados de la cuenta."""
        self.log_mission("Consultando personajes entrenados en Higgsfield")
        return await higgsfield_adapter.list_characters()

    async def get_character(self, character_id: str) -> Dict[str, Any]:
        """Obtiene detalles de un personaje entrenado."""
        self.log_mission(f"Obteniendo personaje: {character_id}")
        return await higgsfield_adapter.get_character(character_id)

    async def check_job_status(self, job_id: str) -> Dict[str, Any]:
        """Consulta el estado de un job asíncrono."""
        self.log_mission(f"Consultando estado del job: {job_id}")
        return await higgsfield_adapter.check_job_status(job_id)

    async def get_result(self, job_id: str, output_path: Optional[str] = None) -> Dict[str, Any]:
        """Descarga el resultado final de un job completado."""
        self.log_mission(f"Recuperando resultado del job: {job_id}")
        return await higgsfield_adapter.get_result(job_id, output_path)

    def get_project_profile(self) -> Dict[str, Any]:
        """Retorna el perfil completo del proyecto Valeria Montesano Digital."""
        return higgsfield_adapter.get_project_profile()

    def get_generation_history(self, limit: int = 20) -> list:
        """Retorna el historial de generaciones del proyecto."""
        if _history:
            return _history.get_by_project(self._project_name, limit=limit)
        return []
