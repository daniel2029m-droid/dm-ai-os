"""
DM AI OS v1.5.2 — Antigravity Remote Bridge Integration Module
==============================================================
Provides secure, authenticated remote bridging between DM AI OS (Web/PWA)
and local Antigravity Agent Runtime.
"""

from .models import (
    PermissionMode,
    SessionStatus,
    AntigravitySession,
    AntigravityChatRequest,
    AntigravityApprovalRequest,
    AntigravityResponse,
    AntigravityAction,
)
from .bridge import antigravity_bridge
from .routes import antigravity_router

__all__ = [
    "PermissionMode",
    "SessionStatus",
    "AntigravitySession",
    "AntigravityChatRequest",
    "AntigravityApprovalRequest",
    "AntigravityResponse",
    "AntigravityAction",
    "antigravity_bridge",
    "antigravity_router",
]

