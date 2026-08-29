"""
DM AI OS — Higgsfield Generation History
==========================================
Historial persistente de todas las generaciones de Higgsfield AI.
Almacenado en SQLite. Incluye deduplicación por job_id.

Proyecto activo: Valeria Montesano Digital
Character: Mi Influencer

Garantiza:
  - Sin generaciones duplicadas (check por job_id)
  - Historial filtrable por proyecto, personaje, tipo de media
  - Recuperación de assets por character_id
  - Stats de uso por modelo y proyecto
"""

import json
import time
import logging
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional

log = logging.getLogger("higgsfield_generation_history")

_DB_PATH = Path(__file__).parent.parent.parent / "logs" / "higgsfield_generations.db"


class HiggsfieldGenerationHistory:
    """
    Historial dedicado de generaciones Higgsfield AI.
    Almacena todos los jobs: imágenes y videos generados,
    con información de personaje, proyecto y URLs de output.
    """

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or _DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        """Crear esquema si no existe."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS higgsfield_generations (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id          TEXT    UNIQUE NOT NULL,
                    project         TEXT    DEFAULT 'Valeria Montesano Digital',
                    character_id    TEXT,
                    character_name  TEXT,
                    media_type      TEXT    NOT NULL,
                    model           TEXT,
                    prompt          TEXT,
                    aspect_ratio    TEXT,
                    style_tags      TEXT,
                    output_url      TEXT,
                    local_path      TEXT,
                    status          TEXT    DEFAULT 'pending',
                    mcp_url         TEXT,
                    auth_source     TEXT,
                    raw_result_json TEXT,
                    created_at      REAL    NOT NULL,
                    updated_at      REAL
                )
            """)
            # Índices para consultas frecuentes
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_hg_project
                ON higgsfield_generations (project)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_hg_character
                ON higgsfield_generations (character_id)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_hg_media_type
                ON higgsfield_generations (media_type)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_hg_created
                ON higgsfield_generations (created_at DESC)
            """)
            conn.commit()
        log.debug(f"[HiggsfieldGenerationHistory] DB ready at {self.db_path}")

    # ── Escritura ──────────────────────────────────────────────

    def save(
        self,
        generation_result: Dict[str, Any],
        *,
        project: str = "Valeria Montesano Digital",
        character_id: Optional[str] = None,
        character_name: Optional[str] = None,
        style_tags: Optional[List[str]] = None,
    ) -> Optional[int]:
        """
        Persiste una generación en el historial.
        Deduplicación automática por job_id — no guarda duplicados.

        Args:
            generation_result: Dict retornado por HiggsfieldAdapter.generate_image/video
            project: Nombre del proyecto (default: Valeria Montesano Digital)
            character_id: ID del personaje entrenado usado
            character_name: Nombre display del personaje
            style_tags: Tags de estilo aplicados

        Returns:
            ID del registro creado, o None si ya existía (duplicado)
        """
        job_id = generation_result.get("job_id")
        if not job_id:
            log.warning("[HiggsfieldGenerationHistory] save() called without job_id — skipping")
            return None

        # Check deduplicación
        if self.already_exists(job_id):
            log.info(f"[HiggsfieldGenerationHistory] Job {job_id!r} ya existe — sin duplicar")
            # Actualizar URL si ahora está disponible
            output_url = (
                generation_result.get("image_url") or
                generation_result.get("video_url") or
                generation_result.get("media_url")
            )
            if output_url:
                self._update_url(job_id, output_url, generation_result.get("status", "completed"))
            return None

        media_type = generation_result.get("media_type", "unknown")
        output_url = (
            generation_result.get("image_url") or
            generation_result.get("video_url") or
            generation_result.get("media_url")
        )
        now = time.time()

        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute(
                    """
                    INSERT INTO higgsfield_generations
                        (job_id, project, character_id, character_name, media_type,
                         model, prompt, aspect_ratio, style_tags, output_url,
                         local_path, status, mcp_url, auth_source,
                         raw_result_json, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        job_id,
                        project,
                        character_id,
                        character_name,
                        media_type,
                        generation_result.get("model"),
                        (generation_result.get("prompt") or "")[:1000],
                        generation_result.get("aspect_ratio"),
                        json.dumps(style_tags or []),
                        output_url,
                        generation_result.get("local_path"),
                        generation_result.get("status", "pending"),
                        generation_result.get("mcp_url"),
                        generation_result.get("auth_source"),
                        json.dumps(generation_result.get("raw_result") or {}),
                        generation_result.get("created_at", now),
                        now,
                    )
                )
                conn.commit()
                row_id = cursor.lastrowid
                log.info(
                    f"[HiggsfieldGenerationHistory] Saved {media_type} job {job_id!r} "
                    f"(id={row_id}, project={project!r})"
                )
                return row_id
        except sqlite3.IntegrityError:
            # UNIQUE constraint — raza de condición con already_exists()
            log.info(f"[HiggsfieldGenerationHistory] Duplicate job_id {job_id!r} — skipped")
            return None

    def _update_url(self, job_id: str, output_url: str, status: str):
        """Actualizar URL y status de un job existente."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE higgsfield_generations SET output_url=?, status=?, updated_at=? WHERE job_id=?",
                (output_url, status, time.time(), job_id)
            )
            conn.commit()

    def update_local_path(self, job_id: str, local_path: str):
        """Registrar path local del archivo descargado."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE higgsfield_generations SET local_path=?, updated_at=? WHERE job_id=?",
                (local_path, time.time(), job_id)
            )
            conn.commit()

    # ── Consultas ──────────────────────────────────────────────

    def already_exists(self, job_id: str) -> bool:
        """Verificar si un job_id ya fue guardado (deduplicación)."""
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT id FROM higgsfield_generations WHERE job_id=?", (job_id,)
            ).fetchone()
        return row is not None

    def get_recent(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Últimas N generaciones ordenadas por fecha descendente."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM higgsfield_generations ORDER BY created_at DESC LIMIT ?",
                (limit,)
            ).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def get_by_project(self, project: str, limit: int = 50) -> List[Dict[str, Any]]:
        """Historial filtrado por nombre de proyecto."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM higgsfield_generations WHERE project=? ORDER BY created_at DESC LIMIT ?",
                (project, limit)
            ).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def get_by_character(
        self,
        character_id: str,
        media_type: Optional[str] = None,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """Generaciones de un personaje específico, opcionalmente filtradas por tipo."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            if media_type:
                rows = conn.execute(
                    """SELECT * FROM higgsfield_generations
                       WHERE character_id=? AND media_type=?
                       ORDER BY created_at DESC LIMIT ?""",
                    (character_id, media_type, limit)
                ).fetchall()
            else:
                rows = conn.execute(
                    """SELECT * FROM higgsfield_generations
                       WHERE character_id=?
                       ORDER BY created_at DESC LIMIT ?""",
                    (character_id, limit)
                ).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def get_by_media_type(
        self,
        media_type: str,
        project: Optional[str] = None,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """Generaciones filtradas por tipo de media (image/video)."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            if project:
                rows = conn.execute(
                    """SELECT * FROM higgsfield_generations
                       WHERE media_type=? AND project=?
                       ORDER BY created_at DESC LIMIT ?""",
                    (media_type, project, limit)
                ).fetchall()
            else:
                rows = conn.execute(
                    """SELECT * FROM higgsfield_generations
                       WHERE media_type=?
                       ORDER BY created_at DESC LIMIT ?""",
                    (media_type, limit)
                ).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def get_by_job_id(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Recuperar una generación específica por job_id."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM higgsfield_generations WHERE job_id=?", (job_id,)
            ).fetchone()
        return self._row_to_dict(row) if row else None

    def get_stats(self) -> Dict[str, Any]:
        """Estadísticas de uso por proyecto, modelo y tipo de media."""
        with sqlite3.connect(self.db_path) as conn:
            total = conn.execute(
                "SELECT COUNT(*) FROM higgsfield_generations"
            ).fetchone()[0]

            by_type = conn.execute(
                "SELECT media_type, COUNT(*) FROM higgsfield_generations GROUP BY media_type"
            ).fetchall()

            by_model = conn.execute(
                "SELECT model, COUNT(*) FROM higgsfield_generations GROUP BY model"
            ).fetchall()

            by_project = conn.execute(
                "SELECT project, COUNT(*) FROM higgsfield_generations GROUP BY project"
            ).fetchall()

            by_character = conn.execute(
                """SELECT character_name, COUNT(*)
                   FROM higgsfield_generations
                   WHERE character_id IS NOT NULL
                   GROUP BY character_id""".strip()
            ).fetchall()

            completed = conn.execute(
                "SELECT COUNT(*) FROM higgsfield_generations WHERE status IN ('completed','done','succeeded')"
            ).fetchone()[0]

        return {
            "total_generations":  total,
            "completed":          completed,
            "by_media_type":      {r[0]: r[1] for r in by_type},
            "by_model":           {r[0]: r[1] for r in by_model},
            "by_project":         {r[0]: r[1] for r in by_project},
            "by_character":       {r[0]: r[1] for r in by_character},
        }

    # ── Helpers ────────────────────────────────────────────────

    @staticmethod
    def _row_to_dict(row) -> Dict[str, Any]:
        """Convertir sqlite3.Row a dict, deserializando JSON columns."""
        d = dict(row)
        # Deserializar style_tags
        if d.get("style_tags"):
            try:
                d["style_tags"] = json.loads(d["style_tags"])
            except Exception:
                d["style_tags"] = []
        # Deserializar raw_result_json
        if d.get("raw_result_json"):
            try:
                d["raw_result"] = json.loads(d["raw_result_json"])
            except Exception:
                d["raw_result"] = {}
            del d["raw_result_json"]
        return d


# ── Singleton ──────────────────────────────────────────────────
higgsfield_history = HiggsfieldGenerationHistory()
