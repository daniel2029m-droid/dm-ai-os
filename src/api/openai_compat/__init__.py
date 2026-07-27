"""
OpenAI Compatibility Layer — Phase 9
=====================================
Pure translation layer between OpenAI-compatible clients and BrainPipeline.

This package:
  - Validates and translates OpenAI API requests
  - Authenticates requests (Bearer / X-API-Key / no-auth)
  - Calls BrainPipeline (never Ollama directly, never agents directly)
  - Converts BrainPipeline responses to OpenAI format
  - Streams SSE responses compatible with all OpenAI clients

It does NOT contain business logic.
It does NOT call Ollama directly.
It does NOT bypass BrainPipeline.
"""

from .router import openai_router  # noqa: F401

__all__ = ["openai_router"]
