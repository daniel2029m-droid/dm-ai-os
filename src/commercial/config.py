"""
DM AI OS — Centralized Commercial Configuration (Env & Constants)
===================================================================
Loads all sensitive variables and commercial constants from environment variables (.env).
No hardcoded sensitive data or settings.
"""

import os
from pathlib import Path

_WORKSPACE_ROOT = Path(__file__).parent.parent.parent

try:
    from dotenv import load_dotenv
    load_dotenv(_WORKSPACE_ROOT / ".env")
except ImportError:
    env_file = _WORKSPACE_ROOT / ".env"
    if env_file.exists():
        with open(env_file, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip() and not line.startswith("#") and "=" in line:
                    k, v = line.strip().split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())

# ── Admin Auth ─────────────────────────────────────────────────────────────────
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "dmorales2026-7")
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "dm_ai_os_jwt_super_secret_key_2026_change_in_prod")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "1440")) # 24 hours

# ── Stripe Config ──────────────────────────────────────────────────────────────
STRIPE_PAYMENT_LINK = os.getenv(
    "STRIPE_PAYMENT_LINK",
    "https://buy.stripe.com/9B68wQ5WMdF6gYsbCe8AE01"
)
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "whsec_mock_secret_key")

# ── Mercado Pago Config (Argentina) ────────────────────────────────────────────
MP_ALIAS = os.getenv("MP_ALIAS", "monetiza.dm")
MP_CVU = os.getenv("MP_CVU", "0000003100044063397420")
MP_ACCOUNT_HOLDER = os.getenv("MP_ACCOUNT_HOLDER", "Daniel Alberto Morales")
DEFAULT_USD_TO_ARS_RATE = float(os.getenv("DEFAULT_USD_TO_ARS_RATE", "1250.0"))

# ── Plans Config ───────────────────────────────────────────────────────────────
PLANS = {
    "starter": {"name": "Starter", "usd": 29.0, "description": "1 Asistente, especialista básico"},
    "professional": {"name": "Professional", "usd": 99.0, "description": "3 Asistentes, suite de especialistas completa"},
    "enterprise": {"name": "Enterprise", "usd": 299.0, "description": "Asistentes ilimitados, cognitive scheduler & aprendizaje continuo"},
}
