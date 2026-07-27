"""
Phase 9 — POST /v1/responses
==============================
OpenAI Responses API endpoint — compatible with openai SDK v1.x+ when
clients use `client.responses.create(...)` instead of `chat.completions.create(...)`.

Maps to the same BrainPipeline as /v1/chat/completions.
All intelligence is in BrainPipeline.

Reference: https://platform.openai.com/docs/api-reference/responses
"""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any, Dict, List, Optional, Union

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

from .auth_middleware import openai_auth_dependency
from .debug_trace import RequestTrace
from .schemas_openai import ResponseRequest, ResponseOutput, UsageTokens
from .streaming import stream_brain_response
from src.api.brain_pipeline import brain_pipeline

log = logging.getLogger("dm.openai.responses")

router = APIRouter()


def _input_to_prompt(input_field: Optional[Union[str, List[Any]]]) -> str:
    """Convert the Responses API `input` field to a plain text prompt."""
    if not input_field:
        return ""
    if isinstance(input_field, str):
        return input_field
    if isinstance(input_field, list):
        parts: List[str] = []
        for item in input_field:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                if item.get("type") == "text":
                    parts.append(item.get("text", ""))
                elif item.get("role") == "user":
                    content = item.get("content", "")
                    if isinstance(content, str):
                        parts.append(content)
                    elif isinstance(content, list):
                        parts.extend(
                            c.get("text", "") for c in content
                            if isinstance(c, dict) and c.get("type") == "text"
                        )
        return " ".join(p for p in parts if p)
    return str(input_field)


@router.post("/v1/responses")
async def post_responses(
    raw_request: Request,
    _auth: Optional[str] = Depends(openai_auth_dependency),
) -> Any:
    """
    POST /v1/responses

    OpenAI Responses API — translates to BrainPipeline.
    Same intelligence pipeline as /v1/chat/completions.

    Compatible with: openai SDK v1.x `client.responses.create(...)`,
                     Grok Build, and any Responses-API-aware client.
    """
    try:
        body = await raw_request.json()
    except Exception:
        raise HTTPException(status_code=400, detail={"error": {"message": "Invalid JSON", "type": "invalid_request_error"}})

    try:
        req = ResponseRequest.model_validate(body)
    except Exception as e:
        raise HTTPException(status_code=422, detail={"error": {"message": str(e), "type": "invalid_request_error"}})

    user_id = req.user or body.get("user", "daniel")
    resp_id = f"resp_{uuid.uuid4().hex}"

    trace = RequestTrace(request_id=resp_id, model=req.model, user_id=user_id)
    trace.add("authentication", "OK", f"user={user_id}")

    # Build prompt from `input` or `messages` field
    prompt = _input_to_prompt(req.input)
    if not prompt and req.messages:
        for m in reversed(req.messages):
            if m.role == "user":
                prompt = m.content if isinstance(m.content, str) else ""
                break

    system_prompt = req.instructions  # Responses API uses `instructions` for system

    if not prompt:
        prompt = "Hello"

    trace.add("prompt_extraction", "OK", f"len={len(prompt)}")

    # Run BrainPipeline
    trace.add("brain_pipeline_start", "OK")
    try:
        brain_result = await brain_pipeline.process(user_prompt=prompt, user_id=user_id)
    except Exception as exc:
        log.error(f"[Responses] BrainPipeline error: {exc}")
        raise HTTPException(status_code=500, detail={"error": {"message": str(exc), "type": "server_error"}})

    trace.add("brain_pipeline_complete", "OK", f"source={brain_result.get('source')}")

    answer = brain_result.get("answer", "")

    # Streaming
    if req.stream:
        trace.add("streaming", "OK")

        async def _stream():
            async for chunk in stream_brain_response(
                prompt=prompt,
                model=req.model,
                user_id=user_id,
                system_prompt=system_prompt,
                messages=[],
                brain_result=brain_result,
            ):
                yield chunk

        return StreamingResponse(
            _stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    # Non-streaming — Responses API format
    prompt_tokens = max(1, len(prompt) // 4)
    completion_tokens = max(1, len(answer) // 4)

    response = ResponseOutput(
        id=resp_id,
        object="response",
        created=int(time.time()),
        model=req.model,
        output=[
            {
                "type": "message",
                "id": f"msg_{uuid.uuid4().hex[:16]}",
                "role": "assistant",
                "content": [{"type": "output_text", "text": answer}],
                "status": "completed",
            }
        ],
        usage=UsageTokens(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
        ),
        status="completed",
    )

    trace.add("response_format", "OK", "responses-api")
    trace.log_summary()

    return response.model_dump(exclude_none=True)
