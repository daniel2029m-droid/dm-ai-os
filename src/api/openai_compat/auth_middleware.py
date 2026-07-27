"""
Phase 9 — OpenAI Layer Authentication Middleware
==================================================
Supports three modes (configured in config/openai_security.json):

  "none"    → All requests accepted (default — local dev)
  "bearer"  → Requires Authorization: Bearer <token>
  "api_key" → Requires X-API-Key: <key>
  "both"    → Accepts either Bearer or X-API-Key

Returns OpenAI-format error JSON on auth failure (not HTML 403).
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Optional

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse

log = logging.getLogger("dm.openai.auth")

_CONFIG_PATH = Path(__file__).resolve().parents[3] / "config" / "openai_security.json"


def _load_security_config() -> dict:
    """Load openai_security.json; fall back to no-auth if missing."""
    try:
        if _CONFIG_PATH.exists():
            return json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception as e:
        log.warning(f"[Auth] Failed to load openai_security.json: {e}")
    return {"auth_mode": "none", "require_auth": False}


def _openai_auth_error(message: str = "Unauthorized") -> JSONResponse:
    """Return a proper OpenAI-format 401 response."""
    return JSONResponse(
        status_code=401,
        content={
            "error": {
                "message": message,
                "type": "invalid_request_error",
                "param": None,
                "code": "invalid_api_key",
            }
        },
        headers={"WWW-Authenticate": "Bearer"},
    )


async def openai_auth_dependency(request: Request) -> Optional[str]:
    """
    FastAPI dependency.  Returns the authenticated identity string (token/key)
    or None when auth is disabled.  Raises HTTPException on failure.
    """
    cfg = _load_security_config()

    # Always accept if auth is disabled
    if not cfg.get("require_auth", False) or cfg.get("auth_mode", "none") == "none":
        return None

    mode = cfg.get("auth_mode", "none")
    allowed_tokens: list[str] = cfg.get("allowed_bearer_tokens", [])
    allowed_keys: list[str] = cfg.get("allowed_api_keys", [])

    # Also honour env-var override
    env_key = os.getenv("DM_API_KEY", "")
    if env_key:
        allowed_tokens = list({*allowed_tokens, env_key})
        allowed_keys = list({*allowed_keys, env_key})

    # ── Bearer ──────────────────────────────────────────────────────────────
    if mode in ("bearer", "both"):
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[len("Bearer "):].strip()
            if token in allowed_tokens:
                return token
            elif mode == "bearer":
                raise HTTPException(
                    status_code=401,
                    detail={
                        "error": {
                            "message": "Invalid Bearer token",
                            "type": "invalid_request_error",
                            "code": "invalid_api_key",
                        }
                    },
                )

    # ── X-API-Key ────────────────────────────────────────────────────────────
    if mode in ("api_key", "both"):
        api_key = (
            request.headers.get("X-API-Key", "")
            or request.headers.get("x-api-key", "")
        )
        if api_key in allowed_keys:
            return api_key

    # ── Failure ──────────────────────────────────────────────────────────────
    raise HTTPException(
        status_code=401,
        detail={
            "error": {
                "message": (
                    "No valid authentication provided. "
                    f"Expected mode: '{mode}'. "
                    "Set Authorization: Bearer <token> or X-API-Key: <key>."
                ),
                "type": "invalid_request_error",
                "code": "invalid_api_key",
            }
        },
    )
