"""
Phase 9 — Tool Translator
==========================
Translates OpenAI Tool Calls ↔ Internal MCP Tool Calls.

Key principles:
  - NEVER hardcodes tool definitions
  - Reads all tools dynamically from mcp_registry
  - Future MCP servers automatically appear
  - OpenAI tool_call → MCP call → OpenAI tool response

OpenAI name convention: "browser.search" → MCP name: "browser_search"
The translator normalises both directions automatically.
"""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any, Dict, List, Optional, Tuple

from src.mcp.registry import mcp_registry
from src.mcp.tools import register_all_tools  # ensure tools are registered

log = logging.getLogger("dm.openai.tools")

# Ensure MCP tools are registered before first use
register_all_tools()


# ─────────────────────────────────────────────────────────────────────────────
# Name normalisation helpers
# ─────────────────────────────────────────────────────────────────────────────

def _oai_to_mcp_name(oai_name: str) -> str:
    """
    Convert OpenAI tool name to MCP tool name.
    'browser.search' → 'browser_search'
    'memory.store'   → 'memory_store'  (or 'remember' via alias)
    """
    return oai_name.replace(".", "_").replace("-", "_")


def _mcp_to_oai_name(mcp_name: str) -> str:
    """
    Convert MCP tool name to OpenAI tool name (dot-notation).
    'browser_search' → 'browser.search'
    Only convert first underscore to dot for namespace separation.
    """
    # Known namespaces
    NAMESPACES = (
        "browser", "computer", "research", "workflow", "agent",
        "memory", "artifacts", "system", "facebook", "media",
    )
    for ns in NAMESPACES:
        prefix = f"{ns}_"
        if mcp_name.startswith(prefix):
            rest = mcp_name[len(prefix):]
            return f"{ns}.{rest}"
    return mcp_name


# Alias map: OpenAI tool name → MCP registry name
_ALIAS_MAP: Dict[str, str] = {
    "browser.search":      "browser_search",
    "browser.open":        "browser_open",
    "computer.execute":    "computer_execute",
    "research.search":     "research_search",
    "research.summarize":  "research_summarize",
    "workflow.run":        "run_workflow",
    "agent.run":           "run_agent",
    "memory.search":       "search_memory",
    "memory.store":        "remember",
    "memory.update":       "update_memory",
    "memory.forget":       "forget_memory",
    "artifacts.list":      "get_artifacts",
    "system.status":       "system_status",
    "facebook.generate":   "facebook_generate",
    "media.generate":      "media_generate",
}


def _resolve_mcp_name(oai_name: str) -> Optional[str]:
    """
    Try to find a matching MCP tool name for an OpenAI tool name.
    1. Check alias map
    2. Try direct normalisation
    3. Search registry fuzzy
    """
    # 1. Alias
    if oai_name in _ALIAS_MAP:
        candidate = _ALIAS_MAP[oai_name]
        if mcp_registry.get_tool(candidate):
            return candidate

    # 2. Normalised
    normalised = _oai_to_mcp_name(oai_name)
    if mcp_registry.get_tool(normalised):
        return normalised

    # 3. Direct (already mcp_name format)
    if mcp_registry.get_tool(oai_name):
        return oai_name

    return None


# ─────────────────────────────────────────────────────────────────────────────
# Build OpenAI tool list from MCP Registry (dynamic — never hardcoded)
# ─────────────────────────────────────────────────────────────────────────────

def build_openai_tools_from_registry() -> List[Dict[str, Any]]:
    """
    Dynamically generate an OpenAI-compatible `tools` list from the
    MCP Registry.  New MCP tools appear automatically without code changes.
    """
    tools = []
    for mcp_tool in mcp_registry.list_tools():
        oai_name = _mcp_to_oai_name(mcp_tool["name"])
        tools.append(
            {
                "type": "function",
                "function": {
                    "name": oai_name,
                    "description": mcp_tool.get("description", ""),
                    "parameters": {
                        "type": "object",
                        "properties": {},
                        "required": [],
                    },
                },
            }
        )
    return tools


# ─────────────────────────────────────────────────────────────────────────────
# Execute an OpenAI tool call via MCP
# ─────────────────────────────────────────────────────────────────────────────

async def execute_openai_tool_call(
    tool_call_id: str,
    oai_function_name: str,
    arguments_json: str,
) -> Dict[str, Any]:
    """
    Translate one OpenAI tool call into an MCP invocation and return the
    result in the format expected by OpenAI's tool response.
    """
    import asyncio

    try:
        arguments = json.loads(arguments_json) if arguments_json.strip() else {}
    except json.JSONDecodeError:
        arguments = {"raw_input": arguments_json}

    mcp_name = _resolve_mcp_name(oai_function_name)
    if not mcp_name:
        log.warning(f"[ToolTranslator] No MCP mapping for '{oai_function_name}'")
        return {
            "tool_call_id": tool_call_id,
            "role": "tool",
            "content": json.dumps(
                {"error": f"Tool '{oai_function_name}' not found in MCP registry"}
            ),
        }

    tool_item = mcp_registry.get_tool(mcp_name)
    if not tool_item:
        return {
            "tool_call_id": tool_call_id,
            "role": "tool",
            "content": json.dumps({"error": f"MCP tool '{mcp_name}' not registered"}),
        }

    handler = tool_item["handler"]
    try:
        log.info(f"[ToolTranslator] {oai_function_name} → MCP:{mcp_name} | args={arguments}")
        if asyncio.iscoroutinefunction(handler):
            result = await handler(**arguments)
        else:
            result = handler(**arguments)

        return {
            "tool_call_id": tool_call_id,
            "role": "tool",
            "content": json.dumps(result, default=str),
        }
    except Exception as exc:
        log.error(f"[ToolTranslator] MCP call failed for '{mcp_name}': {exc}")
        return {
            "tool_call_id": tool_call_id,
            "role": "tool",
            "content": json.dumps({"error": str(exc)}),
        }


# ─────────────────────────────────────────────────────────────────────────────
# Build OpenAI tool_calls from a BrainPipeline-detected agent action
# ─────────────────────────────────────────────────────────────────────────────

def make_tool_call_from_agent(agent_name: Optional[str]) -> Optional[List[Dict[str, Any]]]:
    """
    If BrainPipeline selected an agent, fabricate an OpenAI tool_call
    so clients that inspect tool usage can see what happened.
    """
    if not agent_name:
        return None
    oai_name = f"{agent_name}.run"
    call_id = f"call_{uuid.uuid4().hex[:16]}"
    return [
        {
            "id": call_id,
            "type": "function",
            "function": {
                "name": oai_name,
                "arguments": "{}",
            },
        }
    ]
