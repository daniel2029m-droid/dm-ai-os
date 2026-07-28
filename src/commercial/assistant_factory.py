"""
AssistantFactory — Commercial SaaS Digital Assistant Platform (Fase 19)
=======================================================================
Converts DM AI OS into a multi-client commercial platform.
Each client gets a fully isolated, pre-configured Digital Assistant
for their specific business type.

22 Business Templates ready to deploy:
  Local trades   : electricista, plomero, refrigeracion, mecanico
  Beauty         : peluqueria, manicura
  Food & retail  : restaurante, kiosco, merceria
  Professionals  : abogado, contador, medico, profesor
  Digital media  : youtube, tiktok, facebook, instagram, fanvue, whatsapp_business
  Financial      : crypto
  Education      : cursos

Each assistant:
  - Has its own TenantContext (zero cross-contamination)
  - Runs a configured specialist bundle
  - Routes tasks to the best-fit specialist automatically
  - Uses all tools the user already owns (Grok, OpenAI, RunPod, Ollama, etc.)
"""

import os
import json
import logging
import sqlite3
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

log = logging.getLogger("assistant_factory")


def _get_default_db() -> Path:
    base_storage = os.getenv("DM_STORAGE_DIR") or os.getenv("DM_DATA_DIR")
    if base_storage:
        base = Path(base_storage)
    elif os.getenv("VERCEL"):
        base = Path("/tmp/Project_State")
    else:
        base = Path(__file__).parent.parent.parent / "Project_State"
    try:
        base.mkdir(parents=True, exist_ok=True)
    except Exception:
        base = Path("/tmp/Project_State")
        base.mkdir(parents=True, exist_ok=True)
    return base / "assistant_factory.db"


# ── Business Templates ─────────────────────────────────────────────────────────

BUSINESS_TEMPLATES: Dict[str, Dict[str, Any]] = {
    # Local trades & services
    "electricista": {
        "display_name": "Asistente para Electricista",
        "specialists": ["local_business_specialist", "whatsapp_specialist", "facebook_specialist", "ads_specialist"],
        "primary": "local_business_specialist",
        "description": "Gestiona tu negocio de electricidad: presencia digital, clientes, publicidad y crecimiento automático.",
    },
    "plomero": {
        "display_name": "Asistente para Plomero",
        "specialists": ["local_business_specialist", "whatsapp_specialist", "facebook_specialist"],
        "primary": "local_business_specialist",
        "description": "Digitaliza tu negocio de plomería y atrae más clientes automáticamente.",
    },
    "refrigeracion": {
        "display_name": "Asistente para Refrigeración",
        "specialists": ["local_business_specialist", "whatsapp_specialist", "ads_specialist"],
        "primary": "local_business_specialist",
        "description": "Crece tu negocio de refrigeración con marketing digital automatizado.",
    },
    "mecanico": {
        "display_name": "Asistente para Mecánico",
        "specialists": ["local_business_specialist", "whatsapp_specialist", "facebook_specialist"],
        "primary": "local_business_specialist",
        "description": "Atrae más clientes a tu taller mecánico con publicidad digital.",
    },
    # Beauty & wellness
    "peluqueria": {
        "display_name": "Asistente para Peluquería",
        "specialists": ["local_business_specialist", "instagram_specialist", "whatsapp_specialist", "content_specialist"],
        "primary": "instagram_specialist",
        "description": "Llena tu agenda de clientes con Instagram y WhatsApp automatizados.",
    },
    "manicura": {
        "display_name": "Asistente para Manicura & Uñas",
        "specialists": ["instagram_specialist", "tiktok_specialist", "whatsapp_specialist", "content_specialist"],
        "primary": "instagram_specialist",
        "description": "Viraliza tu trabajo en Instagram y TikTok para atraer clientas nuevas.",
    },
    # Food & retail
    "restaurante": {
        "display_name": "Asistente para Restaurante",
        "specialists": ["local_business_specialist", "instagram_specialist", "facebook_specialist", "whatsapp_specialist"],
        "primary": "local_business_specialist",
        "description": "Llena tus mesas con marketing gastronómico digital automatizado.",
    },
    "kiosco": {
        "display_name": "Asistente para Kiosco",
        "specialists": ["local_business_specialist", "whatsapp_specialist", "facebook_specialist"],
        "primary": "local_business_specialist",
        "description": "Incrementa las ventas de tu kiosco con presencia digital.",
    },
    "merceria": {
        "display_name": "Asistente para Mercería",
        "specialists": ["local_business_specialist", "instagram_specialist", "whatsapp_specialist"],
        "primary": "instagram_specialist",
        "description": "Vende más en tu mercería con catálogos online y WhatsApp Business.",
    },
    # Professional services
    "abogado": {
        "display_name": "Asistente para Abogado",
        "specialists": ["local_business_specialist", "content_specialist", "seo_specialist", "ads_specialist"],
        "primary": "content_specialist",
        "description": "Atrae más clientes con contenido legal de autoridad y posicionamiento SEO.",
    },
    "contador": {
        "display_name": "Asistente para Contador",
        "specialists": ["local_business_specialist", "content_specialist", "seo_specialist"],
        "primary": "content_specialist",
        "description": "Posiciona tu estudio contable y atrae clientes con contenido especializado.",
    },
    "medico": {
        "display_name": "Asistente para Médico / Clínica",
        "specialists": ["local_business_specialist", "content_specialist", "seo_specialist", "ads_specialist"],
        "primary": "content_specialist",
        "description": "Atrae pacientes con contenido médico de confianza y publicidad segmentada.",
    },
    "profesor": {
        "display_name": "Asistente para Profesor / Tutor",
        "specialists": ["education_specialist", "content_specialist", "course_builder_specialist", "seo_specialist"],
        "primary": "education_specialist",
        "description": "Crea y vende cursos online. Automatiza tu contenido educativo.",
    },
    # Digital media
    "youtube": {
        "display_name": "Asistente para YouTube",
        "specialists": ["youtube_specialist", "content_specialist", "seo_specialist", "analytics_specialist"],
        "primary": "youtube_specialist",
        "description": "Crece tu canal con SEO, scripts de alto CTR y thumbnails automatizados.",
    },
    "tiktok": {
        "display_name": "Asistente para TikTok",
        "specialists": ["tiktok_specialist", "content_specialist", "analytics_specialist"],
        "primary": "tiktok_specialist",
        "description": "Viraliza en TikTok con scripts de hook de 3 segundos y producción automatizada.",
    },
    "facebook": {
        "display_name": "Asistente para Facebook",
        "specialists": ["facebook_specialist", "ads_specialist", "analytics_specialist", "content_specialist"],
        "primary": "facebook_specialist",
        "description": "Crece tu página de Facebook y escala con Meta Ads automatizados.",
    },
    "instagram": {
        "display_name": "Asistente para Instagram",
        "specialists": ["instagram_specialist", "content_specialist", "ads_specialist", "analytics_specialist"],
        "primary": "instagram_specialist",
        "description": "Crece en Instagram con Reels virales y estrategia de contenido automatizada.",
    },
    "fanvue": {
        "display_name": "Asistente para Fanvue / Creator",
        "specialists": ["fanvue_specialist", "content_specialist", "analytics_specialist"],
        "primary": "fanvue_specialist",
        "description": "Crea contenido premium con consistencia facial y gestiona tu cuenta de creador.",
    },
    "whatsapp_business": {
        "display_name": "Asistente para WhatsApp Business",
        "specialists": ["whatsapp_specialist", "customer_support_specialist", "sales_specialist"],
        "primary": "whatsapp_specialist",
        "description": "Automatiza WhatsApp Business: catálogos, respuestas automáticas y campañas.",
    },
    # Financial
    "crypto": {
        "display_name": "Asistente para Crypto",
        "specialists": ["crypto_specialist", "research_specialist", "analytics_specialist"],
        "primary": "crypto_specialist",
        "description": "Monitorea el mercado crypto con análisis automatizados y alertas.",
    },
    # Education
    "cursos": {
        "display_name": "Asistente para Cursos Online",
        "specialists": ["course_builder_specialist", "content_specialist", "seo_specialist", "ads_specialist"],
        "primary": "course_builder_specialist",
        "description": "Crea, lanza y vende cursos online con marketing automatizado.",
    },
    # Generic fallback
    "negocio_local": {
        "display_name": "Asistente para Negocio Local",
        "specialists": ["local_business_specialist", "whatsapp_specialist", "facebook_specialist", "content_specialist"],
        "primary": "local_business_specialist",
        "description": "Digitaliza y automatiza cualquier negocio local.",
    },
}


class AssistantFactory:
    """
    Commercial SaaS platform for creating isolated business digital assistants.
    Each assistant is a fully configured, tenant-isolated specialist bundle.
    """

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or _get_default_db()
        try:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
        except Exception:
            self.db_path = Path("/tmp/Project_State") / "assistant_factory.db"
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS assistants (
                    assistant_id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    business_type TEXT NOT NULL,
                    display_name TEXT NOT NULL,
                    config TEXT DEFAULT '{}',
                    active INTEGER DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                CREATE INDEX IF NOT EXISTS idx_assistants_tenant
                    ON assistants(tenant_id, active);
            """)
            conn.commit()

    # ── Template Discovery ────────────────────────────────────────────────────

    def list_available_templates(self) -> List[Dict[str, str]]:
        """List all available business assistant templates."""
        return [
            {
                "type": k,
                "name": v["display_name"],
                "description": v["description"],
                "specialists": v["specialists"],
            }
            for k, v in BUSINESS_TEMPLATES.items()
        ]

    def _resolve_template(self, business_type: str) -> tuple[Dict[str, Any], str]:
        """Resolve business type to a template, with fuzzy matching fallback."""
        key = business_type.lower().strip()

        # Exact match
        if key in BUSINESS_TEMPLATES:
            return BUSINESS_TEMPLATES[key], key

        # Partial / fuzzy match
        for template_key in BUSINESS_TEMPLATES:
            if template_key in key or key in template_key:
                return BUSINESS_TEMPLATES[template_key], template_key

        # Generic fallback
        template = BUSINESS_TEMPLATES["negocio_local"].copy()
        template["display_name"] = f"Asistente para {business_type.title()}"
        return template, "negocio_local"

    # ── Assistant Lifecycle ───────────────────────────────────────────────────

    def create_assistant(
        self,
        tenant_id: str,
        business_type: str,
        custom_name: Optional[str] = None,
        extra_config: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Create a fully configured, isolated business assistant for a tenant.

        Args:
            tenant_id: Isolated client identifier.
            business_type: Template key (e.g. 'electricista', 'youtube', 'peluqueria').
            custom_name: Optional override display name.
            extra_config: Optional extra config (social credentials, business name, etc.).

        Returns:
            Dict with assistant_id, specialists, primary_specialist, display_name.
        """
        template, resolved_type = self._resolve_template(business_type)
        display_name = custom_name or template["display_name"]
        assistant_id = f"asst_{tenant_id}_{resolved_type}_{uuid.uuid4().hex[:8]}"

        config = {
            "business_type": resolved_type,
            "specialists": template["specialists"],
            "primary_specialist": template["primary"],
            **(extra_config or {}),
        }

        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO assistants "
                "(assistant_id, tenant_id, business_type, display_name, config) "
                "VALUES (?, ?, ?, ?, ?)",
                (assistant_id, tenant_id, resolved_type, display_name, json.dumps(config))
            )
            conn.commit()

        # Ensure tenant isolation exists
        from ..specialists.tenant_manager import tenant_manager
        tenant_manager.get_or_create_tenant(tenant_id, display_name)

        log.info(
            f"[AssistantFactory] Created assistant {assistant_id} "
            f"tenant={tenant_id} type={resolved_type}"
        )

        return {
            "assistant_id": assistant_id,
            "tenant_id": tenant_id,
            "business_type": resolved_type,
            "display_name": display_name,
            "description": template["description"],
            "specialists": template["specialists"],
            "primary_specialist": template["primary"],
            "config": config,
        }

    def get_assistant(self, assistant_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve assistant configuration by ID."""
        with sqlite3.connect(str(self.db_path)) as conn:
            row = conn.execute(
                "SELECT assistant_id, tenant_id, business_type, display_name, config, active "
                "FROM assistants WHERE assistant_id=?",
                (assistant_id,)
            ).fetchone()
        if not row:
            return None
        return {
            "assistant_id": row[0], "tenant_id": row[1], "business_type": row[2],
            "display_name": row[3], "config": json.loads(row[4] or "{}"),
            "active": bool(row[5]),
        }

    def list_assistants(self, tenant_id: str) -> List[Dict[str, Any]]:
        """List all assistants for a tenant."""
        with sqlite3.connect(str(self.db_path)) as conn:
            rows = conn.execute(
                "SELECT assistant_id, business_type, display_name, active, created_at "
                "FROM assistants WHERE tenant_id=? ORDER BY created_at DESC",
                (tenant_id,)
            ).fetchall()
        return [
            {
                "assistant_id": r[0], "business_type": r[1], "display_name": r[2],
                "active": bool(r[3]), "created_at": r[4],
            }
            for r in rows
        ]

    def deactivate_assistant(self, assistant_id: str) -> bool:
        """Deactivate an assistant (soft delete, preserves tenant data)."""
        with sqlite3.connect(str(self.db_path)) as conn:
            affected = conn.execute(
                "UPDATE assistants SET active=0 WHERE assistant_id=?",
                (assistant_id,)
            ).rowcount
            conn.commit()
        return affected > 0

    # ── Task Execution ────────────────────────────────────────────────────────

    async def run_assistant(
        self,
        assistant_id: str,
        task_description: str,
        payload: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Execute a task using the assistant's configured specialist bundle.
        Automatically routes to the best specialist within the bundle.
        Uses any provider the tenant already owns (Grok, OpenAI, Ollama, RunPod...).
        """
        assistant = self.get_assistant(assistant_id)
        if not assistant:
            return {"status": "error", "message": f"Assistant '{assistant_id}' not found"}
        if not assistant["active"]:
            return {"status": "error", "message": "Assistant is deactivated"}

        config = assistant["config"]
        tenant_id = assistant["tenant_id"]
        bundle: List[str] = config.get("specialists", [])
        primary: str = config.get("primary_specialist", "business_specialist")

        from ..specialists.specialist_registry import specialist_registry

        # Route by task intent; fall back to primary if not in bundle
        worker = specialist_registry.route_mission(task_description)
        if worker is None or (bundle and worker.specialist_id not in bundle):
            worker = specialist_registry.get_specialist(primary)

        if worker is None:
            return {"status": "error", "message": "No specialist available"}

        # Enforce tenant isolation
        worker.tenant_id = tenant_id
        worker._tenant_context = None   # Force lazy reload

        result = await worker.execute_task(task_description, payload or {})
        result["assistant_id"] = assistant_id
        result["business_type"] = config.get("business_type")

        log.info(
            f"[AssistantFactory] Assistant {assistant_id} → "
            f"{worker.specialist_id} for tenant {tenant_id}"
        )
        return result


# Module-level singleton
assistant_factory = AssistantFactory()
