"""
Higgsfield AI — Configuración Centralizada para DM AI OS
=========================================================
Todas las variables se leen desde el entorno.
Nunca hardcodear credenciales en este archivo.

Variables de entorno soportadas:
  HIGGSFIELD_AUTH_TOKEN    — Token OAuth (prioridad 1)
  HIGGSFIELD_TOKEN         — Token alternativo (prioridad 2)
  HIGGSFIELD_API_KEY       — API Key (prioridad 3)
  HIGGSFIELD_MCP_URL       — URL del MCP server (default oficial)
  HIGGSFIELD_WORKSPACE_ID  — Workspace ID de la cuenta
  HIGGSFIELD_CHARACTER_ID  — Character ID del personaje entrenado
  HIGGSFIELD_DEFAULT_IMAGE_MODEL  — Modelo default para imágenes
  HIGGSFIELD_DEFAULT_VIDEO_MODEL  — Modelo default para videos
  HIGGSFIELD_DEFAULT_ASPECT_RATIO — Ratio de aspecto default
  HIGGSFIELD_PROJECT_NAME  — Nombre del proyecto activo
  HIGGSFIELD_CHARACTER_NAME — Nombre del personaje activo
  HIGGSFIELD_PROVIDER      — Estado del proveedor (enabled/disabled)
  HIGGSFIELD_MAX_RETRIES   — Reintentos máximos en llamadas RPC
  HIGGSFIELD_POLL_INTERVAL — Intervalo entre polls de job status (segundos)
  HIGGSFIELD_MAX_POLL_TIME — Timeout máximo de polling (segundos)

Proyecto activo: Valeria Montesano Digital
"""

import os
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any

log = logging.getLogger("higgsfield_config")

# ─────────────────────────────────────────────────────────────
# Constantes de la plataforma Higgsfield
# ─────────────────────────────────────────────────────────────

HIGGSFIELD_MCP_URL_DEFAULT = "https://mcp.higgsfield.ai/mcp"

# Modelos conocidos (slugs de la API de Higgsfield)
KNOWN_IMAGE_MODELS = {
    "soul_2":          "Soul 2 — Personaje hiperrealista (influencer)",
    "soul":            "Soul — Personaje realista (generación anterior)",
    "nano_banana_2":   "NanoBanana 2 — Imágenes generales de alta calidad",
    "nano_banana":     "NanoBanana — Imágenes generales",
}

KNOWN_VIDEO_MODELS = {
    "seedance_2_0":           "Seedance 2.0 — Video cinematográfico premium",
    "cinematic_studio_3_0":   "Cinematic Studio 3.0 — Video cinematográfico",
    "cinematic_studio_2_0":   "Cinematic Studio 2.0",
    "motion_easy":            "Motion Easy — Animaciones simples",
}

# Estilos del proyecto Valeria (para enriquecer prompts automáticamente)
VALERIA_STYLE_TAGS: List[str] = [
    "luxury lifestyle",
    "photorealistic",
    "premium cinematic",
    "facebook-safe",
    "advertiser-friendly",
]

# ─────────────────────────────────────────────────────────────
# Perfil del proyecto — Valeria Montesano Digital
# ─────────────────────────────────────────────────────────────

VALERIA_PROJECT_PROFILE: Dict[str, Any] = {
    "project":              "Valeria Montesano Digital",
    "character":            "Mi Influencer",
    "style_tags":           VALERIA_STYLE_TAGS,
    "default_image_model":  "soul_2",
    "default_video_model":  "seedance_2_0",
    "default_aspect_ratio": "9:16",
    "content_platform":     "Facebook / Instagram",
    "content_type":         "Luxury lifestyle & premium brand content",
    "safe_for_ads":         True,
}


# ─────────────────────────────────────────────────────────────
# Dataclass de configuración — carga desde env vars
# ─────────────────────────────────────────────────────────────

@dataclass
class HiggsfieldConfig:
    """
    Configuración de Higgsfield AI para DM AI OS.
    Se instancia con valores desde el entorno — nunca credenciales fijas.
    """

    # Conexión
    mcp_url: str = field(default_factory=lambda: os.getenv(
        "HIGGSFIELD_MCP_URL", HIGGSFIELD_MCP_URL_DEFAULT
    ))

    # Autenticación (solo la variable, nunca el valor en código)
    api_key_env_var: str = "HIGGSFIELD_AUTH_TOKEN"

    # Workspace
    workspace_id: Optional[str] = field(default_factory=lambda: os.getenv(
        "HIGGSFIELD_WORKSPACE_ID"
    ))

    # Personaje activo
    character_id: Optional[str] = field(default_factory=lambda: os.getenv(
        "HIGGSFIELD_CHARACTER_ID"
    ))
    character_name: str = field(default_factory=lambda: os.getenv(
        "HIGGSFIELD_CHARACTER_NAME", "Mi Influencer"
    ))

    # Modelos default
    default_image_model: str = field(default_factory=lambda: os.getenv(
        "HIGGSFIELD_DEFAULT_IMAGE_MODEL", "soul_2"
    ))
    default_video_model: str = field(default_factory=lambda: os.getenv(
        "HIGGSFIELD_DEFAULT_VIDEO_MODEL", "seedance_2_0"
    ))

    # Formato
    default_aspect_ratio: str = field(default_factory=lambda: os.getenv(
        "HIGGSFIELD_DEFAULT_ASPECT_RATIO", "9:16"
    ))

    # Proyecto
    project_name: str = field(default_factory=lambda: os.getenv(
        "HIGGSFIELD_PROJECT_NAME", "Valeria Montesano Digital"
    ))

    # Estado del proveedor
    provider_state: str = field(default_factory=lambda: os.getenv(
        "HIGGSFIELD_PROVIDER", "enabled"
    ).lower())

    # Parámetros de retry y polling
    max_retries: int = field(default_factory=lambda: int(os.getenv(
        "HIGGSFIELD_MAX_RETRIES", "3"
    )))
    poll_interval: float = field(default_factory=lambda: float(os.getenv(
        "HIGGSFIELD_POLL_INTERVAL", "5.0"
    )))
    max_poll_time: float = field(default_factory=lambda: float(os.getenv(
        "HIGGSFIELD_MAX_POLL_TIME", "300.0"
    )))

    # Estilos del proyecto activo
    style_tags: List[str] = field(default_factory=lambda: VALERIA_STYLE_TAGS)

    @property
    def is_enabled(self) -> bool:
        """True si el proveedor está habilitado."""
        return self.provider_state not in ("disabled", "false", "0")

    @property
    def has_character(self) -> bool:
        """True si hay un character_id configurado."""
        return bool(self.character_id)

    @property
    def auth_token(self) -> Optional[str]:
        """
        Retorna el token de autenticación desde variables de entorno.
        Prioridad: HIGGSFIELD_AUTH_TOKEN > HIGGSFIELD_TOKEN > HIGGSFIELD_API_KEY
        Nunca almacena el token en el objeto — siempre lo lee del entorno.
        """
        for var in ["HIGGSFIELD_AUTH_TOKEN", "HIGGSFIELD_TOKEN", "HIGGSFIELD_API_KEY"]:
            val = os.getenv(var, "").strip()
            if val:
                return val
        return None

    def get_project_profile(self) -> Dict[str, Any]:
        """
        Retorna el perfil completo del proyecto activo
        con los valores actuales del entorno.
        """
        return {
            "project":              self.project_name,
            "character":            self.character_name,
            "character_id":         self.character_id,
            "style_tags":           self.style_tags,
            "default_image_model":  self.default_image_model,
            "default_video_model":  self.default_video_model,
            "default_aspect_ratio": self.default_aspect_ratio,
            "workspace_id":         self.workspace_id,
            "mcp_url":              self.mcp_url,
            "is_enabled":           self.is_enabled,
            "has_character":        self.has_character,
        }

    def enrich_prompt_with_style(self, prompt: str) -> str:
        """
        Enriquece un prompt con los estilos del proyecto.
        Útil para garantizar consistencia de marca en todas las generaciones.
        """
        if not self.style_tags:
            return prompt
        style_suffix = ", ".join(self.style_tags)
        return f"{prompt}. Style: {style_suffix}"

    def summary(self) -> str:
        """Resumen de configuración para logging (sin credenciales)."""
        token_status = "✅ Token configurado" if self.auth_token else "❌ Sin token"
        char_status = f"Character: {self.character_id}" if self.has_character else "Sin character configurado"
        return (
            f"HiggsfieldConfig | Proyecto: {self.project_name} | "
            f"{char_status} | {token_status} | "
            f"Imagen: {self.default_image_model} | Video: {self.default_video_model} | "
            f"Ratio: {self.default_aspect_ratio} | Estado: {self.provider_state}"
        )


# ─────────────────────────────────────────────────────────────
# Singleton de configuración — instanciado una vez al importar
# ─────────────────────────────────────────────────────────────

higgsfield_config = HiggsfieldConfig()

log.info(f"[HiggsfieldConfig] {higgsfield_config.summary()}")
