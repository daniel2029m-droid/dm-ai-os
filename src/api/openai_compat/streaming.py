"""
Phase 9 — SSE Streaming
========================
Converts BrainPipeline + Ollama streaming into OpenAI-compatible SSE.

Stream format (exact OpenAI wire format):

    data: {"id":"chatcmpl-xxx","object":"chat.completion.chunk","created":1234567890,"model":"dm-autonomous-brain","choices":[{"index":0,"delta":{"role":"assistant"},"finish_reason":null}]}\n\n
    data: {"id":"chatcmpl-xxx","object":"chat.completion.chunk","created":1234567890,"model":"dm-autonomous-brain","choices":[{"index":0,"delta":{"content":"Hello"},"finish_reason":null}]}\n\n
    data: {"id":"chatcmpl-xxx","object":"chat.completion.chunk",...,"choices":[{"index":0,"delta":{},"finish_reason":"stop"}]}\n\n
    data: [DONE]\n\n

Notes:
  - Streaming goes through BrainPipeline.process_stream() if available,
    otherwise falls back to BrainPipeline.process() with chunked text.
  - Ollama streaming is used via httpx async streaming.
  - Never calls Ollama directly — always through capability_selector.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from typing import Any, AsyncGenerator, Dict, List, Optional

import httpx

from src.providers.capability_selector import capability_selector
from src.memory.memory_manager import memory_manager

log = logging.getLogger("dm.openai.streaming")


def _sse(data: Any) -> str:
    """Format a dict as a SSE data line."""
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


def _sse_done() -> str:
    return "data: [DONE]\n\n"


async def stream_brain_response(
    *,
    prompt: str,
    model: str,
    user_id: str,
    system_prompt: Optional[str],
    messages: List[Dict[str, Any]],
    brain_result: Dict[str, Any],
) -> AsyncGenerator[str, None]:
    """
    Async generator that streams a BrainPipeline result as OpenAI SSE.

    BrainPipeline is called FIRST (non-streaming) so that all pipeline
    stages (memory, identity, agents, cache) run correctly.  The resulting
    text is then streamed token-by-token from Ollama using streaming mode,
    giving clients real-time delta chunks.

    If Ollama is unavailable, the pre-computed answer is chunked manually.
    """
    cmpl_id = f"chatcmpl-{uuid.uuid4().hex}"
    created = int(time.time())

    # ── 1. Opening role delta ──────────────────────────────────────────────
    yield _sse(
        {
            "id": cmpl_id,
            "object": "chat.completion.chunk",
            "created": created,
            "model": model,
            "choices": [
                {"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}
            ],
        }
    )

    # ── 2. Stream pre-computed BrainPipeline answer ───────────────────────
    # BrainPipeline has already executed all agents, research, memory, and identity.
    # We stream the exact final answer chunk-by-chunk to preserve agent reports,
    # sources, URLs, and prevent raw Ollama conversational overrides.
    answer_text = brain_result.get("answer", "")
    if not answer_text or not answer_text.strip():
        answer_text = (
            "Soy DM AI OS. Mi núcleo es BrainPipeline. "
            "Grok Build funciona únicamente como cliente."
        )

    words = answer_text.split(" ")
    for i, word in enumerate(words):
        piece = word + (" " if i < len(words) - 1 else "")
        yield _sse(
            {
                "id": cmpl_id,
                "object": "chat.completion.chunk",
                "created": created,
                "model": model,
                "choices": [
                    {
                        "index": 0,
                        "delta": {"content": piece},
                        "finish_reason": None,
                    }
                ],
            }
        )

    # ── 4. Finish chunk ───────────────────────────────────────────────────
    yield _sse(
        {
            "id": cmpl_id,
            "object": "chat.completion.chunk",
            "created": created,
            "model": model,
            "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
        }
    )

    # ── 5. [DONE] terminator ───────────────────────────────────────────────
    yield _sse_done()

    log.debug(f"[Streaming] Stream complete | id={cmpl_id} | model={model}")
