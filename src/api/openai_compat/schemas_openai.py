"""
Phase 9 — OpenAI-compatible Pydantic schemas.

Mirrors the OpenAI API schema as closely as possible so that any OpenAI SDK
client (Grok Build, Open WebUI, LibreChat, Cursor, Cherry Studio, etc.) can
POST its native request body without modification.

All unrecognised fields are absorbed by `model_config = ConfigDict(extra="allow")`.
"""

from __future__ import annotations

import time
import uuid
from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field


# ─────────────────────────────────────────────────────────────────────────────
# Shared base — absorbs unknown OpenAI fields gracefully
# ─────────────────────────────────────────────────────────────────────────────

class OpenAIBase(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)


# ─────────────────────────────────────────────────────────────────────────────
# Tool definitions
# ─────────────────────────────────────────────────────────────────────────────

class FunctionParameters(OpenAIBase):
    type: str = "object"
    properties: Optional[Dict[str, Any]] = None
    required: Optional[List[str]] = None


class FunctionDefinition(OpenAIBase):
    name: str
    description: Optional[str] = None
    parameters: Optional[FunctionParameters] = None
    strict: Optional[bool] = None


class Tool(OpenAIBase):
    type: Literal["function"] = "function"
    function: FunctionDefinition


class ToolCallFunction(OpenAIBase):
    name: str
    arguments: str  # JSON string per OpenAI spec


class ToolCall(OpenAIBase):
    id: str = Field(default_factory=lambda: f"call_{uuid.uuid4().hex[:16]}")
    type: Literal["function"] = "function"
    function: ToolCallFunction


# ─────────────────────────────────────────────────────────────────────────────
# Messages
# ─────────────────────────────────────────────────────────────────────────────

class ChatMessage(OpenAIBase):
    role: Literal["system", "user", "assistant", "tool", "function"]
    content: Optional[Union[str, List[Any]]] = None
    name: Optional[str] = None
    tool_calls: Optional[List[ToolCall]] = None
    tool_call_id: Optional[str] = None


# ─────────────────────────────────────────────────────────────────────────────
# Request
# ─────────────────────────────────────────────────────────────────────────────

class ResponseFormat(OpenAIBase):
    type: Literal["text", "json_object", "json_schema"] = "text"
    json_schema: Optional[Dict[str, Any]] = None


class ChatCompletionRequest(OpenAIBase):
    """
    Full OpenAI /v1/chat/completions request body.
    Unknown fields are silently ignored (extra="allow").
    """
    model: str = "dm-autonomous-brain"
    messages: List[ChatMessage] = Field(..., min_length=1)

    # Generation parameters
    temperature: Optional[float] = Field(None, ge=0.0, le=2.0)
    top_p: Optional[float] = Field(None, ge=0.0, le=1.0)
    n: Optional[int] = Field(1, ge=1, le=128)
    stream: Optional[bool] = False
    stop: Optional[Union[str, List[str]]] = None
    max_tokens: Optional[int] = Field(None, ge=1)
    presence_penalty: Optional[float] = Field(None, ge=-2.0, le=2.0)
    frequency_penalty: Optional[float] = Field(None, ge=-2.0, le=2.0)
    seed: Optional[int] = None
    response_format: Optional[ResponseFormat] = None

    # Tool calling
    tools: Optional[List[Tool]] = None
    tool_choice: Optional[Union[str, Dict[str, Any]]] = None
    parallel_tool_calls: Optional[bool] = True

    # Identity / metadata
    user: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None

    # OpenAI extended / reasoning
    store: Optional[bool] = None
    reasoning: Optional[Dict[str, Any]] = None
    logprobs: Optional[bool] = None
    top_logprobs: Optional[int] = None


# ─────────────────────────────────────────────────────────────────────────────
# Non-streaming response
# ─────────────────────────────────────────────────────────────────────────────

class Choice(OpenAIBase):
    index: int
    message: ChatMessage
    finish_reason: Optional[str] = "stop"
    logprobs: Optional[Any] = None


class UsageTokens(OpenAIBase):
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class ChatCompletionResponse(OpenAIBase):
    id: str = Field(default_factory=lambda: f"chatcmpl-{uuid.uuid4().hex}")
    object: str = "chat.completion"
    created: int = Field(default_factory=lambda: int(time.time()))
    model: str
    choices: List[Choice]
    usage: Optional[UsageTokens] = None
    system_fingerprint: Optional[str] = None

    # DM platform metadata extensions (backward compatibility)
    x_dm_pipeline: Optional[Dict[str, Any]] = Field(None, alias="x_dm_pipeline")
    x_dm_metadata: Optional[Dict[str, Any]] = Field(None, alias="x_dm_metadata")



# ─────────────────────────────────────────────────────────────────────────────
# Streaming delta
# ─────────────────────────────────────────────────────────────────────────────

class DeltaMessage(OpenAIBase):
    role: Optional[str] = None
    content: Optional[str] = None
    tool_calls: Optional[List[ToolCall]] = None


class StreamChoice(OpenAIBase):
    index: int
    delta: DeltaMessage
    finish_reason: Optional[str] = None
    logprobs: Optional[Any] = None


class ChatCompletionChunk(OpenAIBase):
    id: str
    object: str = "chat.completion.chunk"
    created: int = Field(default_factory=lambda: int(time.time()))
    model: str
    choices: List[StreamChoice]
    system_fingerprint: Optional[str] = None


# ─────────────────────────────────────────────────────────────────────────────
# /v1/models response
# ─────────────────────────────────────────────────────────────────────────────

class ModelObject(OpenAIBase):
    id: str
    object: str = "model"
    created: int = Field(default_factory=lambda: int(time.time()))
    owned_by: str = "dm-platform"


class ModelListResponse(OpenAIBase):
    object: str = "list"
    data: List[ModelObject]


# ─────────────────────────────────────────────────────────────────────────────
# /v1/responses (Responses API — newer OpenAI SDK)
# ─────────────────────────────────────────────────────────────────────────────

class ResponseRequest(OpenAIBase):
    """
    OpenAI Responses API — compatible with newer openai SDK (v1.x+).
    Maps to the same BrainPipeline as chat/completions.
    """
    model: str = "dm-autonomous-brain"
    input: Optional[Union[str, List[Any]]] = None
    messages: Optional[List[ChatMessage]] = None  # fallback alias
    instructions: Optional[str] = None
    tools: Optional[List[Tool]] = None
    temperature: Optional[float] = None
    max_output_tokens: Optional[int] = None
    stream: Optional[bool] = False
    user: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    previous_response_id: Optional[str] = None


class ResponseOutput(OpenAIBase):
    id: str = Field(default_factory=lambda: f"resp_{uuid.uuid4().hex}")
    object: str = "response"
    created: int = Field(default_factory=lambda: int(time.time()))
    model: str
    output: List[Dict[str, Any]]
    usage: Optional[UsageTokens] = None
    status: str = "completed"


# ─────────────────────────────────────────────────────────────────────────────
# Error response (OpenAI format)
# ─────────────────────────────────────────────────────────────────────────────

class OpenAIError(OpenAIBase):
    message: str
    type: str
    param: Optional[str] = None
    code: Optional[str] = None


class OpenAIErrorResponse(OpenAIBase):
    error: OpenAIError
