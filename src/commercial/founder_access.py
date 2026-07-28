"""
DM AI OS — Founder Access Module
==================================
Defines the FOUNDER plan: owner-level access with zero billing,
full specialist suite, all 22 commercial templates, and admin dashboard.

This module is imported by BillingEngine and AssistantFactory to
resolve permissions for tenant_id == 'founder_daniel'.

DO NOT MODIFY — Part of commercial access control layer.
"""

from typing import Dict, Any, List

# ── Founder Identity ──────────────────────────────────────────────────────────

FOUNDER_TENANT_ID   = "founder_daniel"
FOUNDER_EMAIL       = "daniel@dmorales.site"
FOUNDER_NAME        = "Daniel Morales"
FOUNDER_ROLE        = "owner"
FOUNDER_PLAN        = "founder"

# ── Founder Plan Definition ───────────────────────────────────────────────────

FOUNDER_PLAN_CONFIG: Dict[str, Any] = {
    "plan_id":          "founder",
    "plan_name":        "Founder — Acceso Total",
    "role":             "owner",
    "subscription":     "free",
    "billing_exempt":   True,
    "amount_usd":       0.0,
    "amount_ars":       0.0,
    "payment_required": False,
    "description":      (
        "Cuenta fundador del sistema DM AI OS. "
        "Acceso completo a todos los módulos, especialistas, "
        "templates comerciales, dashboard y funciones SaaS. "
        "Sin costo — permanente."
    ),
}

# ── All Specialists Unlocked ──────────────────────────────────────────────────

FOUNDER_SPECIALISTS: List[str] = [
    # Core Agents
    "browser_agent",
    "computer_agent",
    "research_agent",
    "facebook_agent",
    "university_agent",
    "media_agent",
    # Digital Employees (Fase 14)
    "local_business_specialist",
    "whatsapp_specialist",
    "facebook_specialist",
    "instagram_specialist",
    "tiktok_specialist",
    "youtube_specialist",
    "content_specialist",
    "ads_specialist",
    "seo_specialist",
    "email_specialist",
    "ecommerce_specialist",
    "analytics_specialist",
    "crypto_specialist",
    "fanvue_specialist",
    "education_specialist",
    "business_specialist",
    # Autonomy & Learning
    "cognitive_scheduler",
    "learning_engine",
    # MCP Tools (15 tools)
    "mcp_tools_full",
]

# ── All 22 Commercial Templates Unlocked ─────────────────────────────────────

FOUNDER_TEMPLATES: List[str] = [
    "electricista", "plomero", "refrigeracion", "mecanico",
    "peluqueria", "manicura",
    "restaurante", "kiosco", "merceria",
    "abogado", "contador", "medico", "profesor",
    "youtube", "tiktok", "facebook", "instagram",
    "fanvue", "whatsapp_business",
    "crypto", "cursos", "negocio_local",
]

# ── Full Feature Access ───────────────────────────────────────────────────────

FOUNDER_FEATURES: Dict[str, bool] = {
    "dashboard":               True,
    "admin_panel":             True,
    "super_admin":             True,
    "all_specialists":         True,
    "commercial_templates":    True,
    "billing_management":      True,
    "tenant_management":       True,
    "learning_engine":         True,
    "cognitive_scheduler":     True,
    "brain_pipeline":          True,
    "memory_manager":          True,
    "dag_engine":              True,
    "api_gateway":             True,
    "mcp_server":              True,
    "multi_tenant":            True,
    "stripe_management":       True,
    "mercado_pago_management": True,
    "saas_analytics":          True,
    "unlimited_assistants":    True,
    "unlimited_tenants":       True,
    "raw_api_access":          True,
    "openai_compat_layer":     True,
}

# ── Access Control Helper ─────────────────────────────────────────────────────

def is_founder(tenant_id: str) -> bool:
    """Returns True if tenant_id is the Founder account."""
    return tenant_id == FOUNDER_TENANT_ID


def get_founder_profile() -> Dict[str, Any]:
    """Returns the complete Founder account profile dict."""
    return {
        "tenant_id":        FOUNDER_TENANT_ID,
        "user_email":       FOUNDER_EMAIL,
        "name":             FOUNDER_NAME,
        "role":             FOUNDER_ROLE,
        "plan":             FOUNDER_PLAN,
        "subscription":     "free",
        "billing_exempt":   True,
        "status":           "ACTIVE",
        "specialists":      FOUNDER_SPECIALISTS,
        "templates":        FOUNDER_TEMPLATES,
        "features":         FOUNDER_FEATURES,
        "plan_config":      FOUNDER_PLAN_CONFIG,
    }


def founder_has_access(feature: str) -> bool:
    """Check if the Founder plan includes a specific feature."""
    return FOUNDER_FEATURES.get(feature, False)
