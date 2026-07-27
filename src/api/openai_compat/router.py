"""
Phase 9 — OpenAI Compatibility Layer Main Router
=================================================
Assembles all sub-routers into a single APIRouter that is mounted
on the FastAPI app in server.py.

Sub-routers:
  - models_router    → GET  /v1/models
  - chat_completions → POST /v1/chat/completions
  - responses_router → POST /v1/responses

Authentication is applied at the dependency level within each sub-router.
The main app (server.py) mounts this router with no prefix.
"""

from fastapi import APIRouter

from .models_router import router as models_router
from .chat_completions_router import router as chat_router
from .responses_router import router as responses_router

openai_router = APIRouter()

openai_router.include_router(models_router, tags=["OpenAI Models"])
openai_router.include_router(chat_router,   tags=["OpenAI Chat Completions"])
openai_router.include_router(responses_router, tags=["OpenAI Responses"])
