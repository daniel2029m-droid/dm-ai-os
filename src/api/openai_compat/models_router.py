"""
Phase 9 — GET /v1/models
=========================
Returns virtual DM models + live Ollama models in OpenAI list format.

Virtual models are loaded from config/models.json.
Ollama models are probed live (if Ollama is running).
All virtual models route internally to BrainPipeline.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends

from .auth_middleware import openai_auth_dependency
from .schemas_openai import ModelListResponse, ModelObject
from src.providers.capability_selector import capability_selector

log = logging.getLogger("dm.openai.models")

router = APIRouter()

_MODELS_CFG_PATH = Path(__file__).resolve().parents[3] / "config" / "models.json"


def _load_virtual_models() -> List[Dict[str, Any]]:
    """Load virtual model definitions from config/models.json."""
    try:
        if _MODELS_CFG_PATH.exists():
            cfg = json.loads(_MODELS_CFG_PATH.read_text(encoding="utf-8"))
            return cfg.get("virtual_models", [])
    except Exception as e:
        log.warning(f"[Models] Failed to load models.json: {e}")
    # Inline fallback — always return the 8 DM models
    ts = int(time.time())
    return [
        {"id": "dm-autonomous-brain", "object": "model", "created": ts, "owned_by": "dm-platform"},
        {"id": "dm-reasoner",         "object": "model", "created": ts, "owned_by": "dm-platform"},
        {"id": "dm-fast",             "object": "model", "created": ts, "owned_by": "dm-platform"},
        {"id": "dm-memory",           "object": "model", "created": ts, "owned_by": "dm-platform"},
        {"id": "dm-browser",          "object": "model", "created": ts, "owned_by": "dm-platform"},
        {"id": "dm-research",         "object": "model", "created": ts, "owned_by": "dm-platform"},
        {"id": "dm-media",            "object": "model", "created": ts, "owned_by": "dm-platform"},
        {"id": "dm-facebook",         "object": "model", "created": ts, "owned_by": "dm-platform"},
    ]


def _load_ollama_models() -> List[Dict[str, Any]]:
    """Probe Ollama live and return model entries."""
    try:
        cfg_path = Path(__file__).resolve().parents[3] / "config" / "models.json"
        include = True
        ollama_owner = "ollama"
        if cfg_path.exists():
            cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
            include = cfg.get("include_ollama_models", True)
            ollama_owner = cfg.get("ollama_owned_by", "ollama")

        if not include:
            return []

        live = capability_selector.probe_models()
        ts = int(time.time())
        return [
            {"id": name, "object": "model", "created": ts, "owned_by": ollama_owner}
            for name in live
        ]
    except Exception as e:
        log.debug(f"[Models] Ollama probe failed (expected if offline): {e}")
        return []


@router.get("/v1/models", response_model=ModelListResponse)
async def get_models(
    _auth: Optional[str] = Depends(openai_auth_dependency),
) -> ModelListResponse:
    """
    GET /v1/models

    Returns the full model catalog:
      - DM virtual models (from config/models.json)
      - Live Ollama models (probed at request time)

    All DM virtual models internally route to BrainPipeline.
    Compatible with: OpenAI SDK, Grok Build, Open WebUI, LibreChat,
                     Cursor, Cherry Studio, Continue.dev, Roo Code, Cline.
    """
    virtual = _load_virtual_models()
    ollama = _load_ollama_models()

    # Deduplicate by id (ollama models might overlap with virtual names)
    seen: set[str] = set()
    all_models: List[ModelObject] = []
    for m in [*virtual, *ollama]:
        mid = m.get("id", "")
        if mid and mid not in seen:
            seen.add(mid)
            all_models.append(
                ModelObject(
                    id=mid,
                    object=m.get("object", "model"),
                    created=m.get("created", int(time.time())),
                    owned_by=m.get("owned_by", "dm-platform"),
                )
            )

    log.debug(f"[Models] Serving {len(all_models)} models ({len(virtual)} virtual, {len(ollama)} ollama)")
    return ModelListResponse(object="list", data=all_models)
