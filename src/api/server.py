"""
DM AI Operating System — API Gateway v1.2.0-production
=======================================================
Mounts two router groups:

  1. Existing platform routes  (routes.py)
     /health, /system/status, /agent/run, /workflow/run,
     /memory/*, /agents, /mcp/*

  2. OpenAI Compatibility Layer  (openai_compat/)  [Phase 9]
     GET  /v1/models
     POST /v1/chat/completions
     POST /v1/responses

All OpenAI endpoints delegate to BrainPipeline internally.
"""

import logging
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routes import router
from .openai_compat import openai_router

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

app = FastAPI(
    title="DM AI Operating System — OpenAI-Compatible API Gateway",
    version="v1.2.0-production",
    description=(
        "Multi-Agent Autonomous Orchestration Platform — "
        "OpenAI-compatible API layer powering Grok Build, Open WebUI, "
        "LibreChat, Cursor, Cherry Studio, Continue.dev and any OpenAI client."
    ),
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Existing platform routes (all previous phases — DO NOT MODIFY) ─────────
app.include_router(router)

# ── Phase 9: OpenAI Compatibility Layer ─────────────────────────────────────
app.include_router(openai_router)

# ── Commercial SaaS Layer (Stripe, Mercado Pago, Billing, Admin) ───────────
from src.commercial.routes import commercial_router
app.include_router(commercial_router)

# ── AI Provider Manager Router (Settings > AI Providers, AI Router) ─────────
from src.api.providers_router import providers_router
app.include_router(providers_router)

# ── Creative Assets Router (Remote Streaming & Presigned URLs) ──────────────
from src.api.creative_assets_router import creative_assets_router
app.include_router(creative_assets_router)

# ── Remote Compute Workers Router (Colab, Tesla T4, Heartbeat, Handshake) ───
from src.api.workers_router import workers_router
app.include_router(workers_router)


def start_api(host: str = "0.0.0.0", port: int = 8000):
    uvicorn.run("src.api.server:app", host=host, port=port, reload=False, log_level="info")


if __name__ == "__main__":
    start_api()

