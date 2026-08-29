"""
AgentTools — Filesystem & Shell tools exposed to the local LLM (Fase 14.3)
==========================================================================
Enables the local LLM (qwen2.5-coder:7b via Ollama) to act as a coding agent
by providing it with tool definitions and an execution loop.

The loop:
  1. Send user request + tool schemas to Ollama (tools field in /api/chat)
  2. If the model returns tool_calls → execute them locally → feed results back
  3. Repeat until the model returns a plain text response (no tool calls)

Available tools:
  - write_file(path, content)       — Create or overwrite a file
  - read_file(path)                 — Read file contents
  - list_dir(path)                  — List directory contents
  - run_command(command, cwd)       — Execute a shell command (PowerShell)
  - search_file(path, query)        — Search for text in a file

Security:
  - All file operations are sandboxed to DM_WORKSPACE_ROOT (Project root)
  - run_command is restricted to safe prefixes (pytest, python, pip)
"""

import asyncio
import json
import logging
import os
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx

log = logging.getLogger("agent_tools")

# ---------------------------------------------------------------------------
# Security sandbox
# ---------------------------------------------------------------------------
_WORKSPACE_ROOT = Path(
    os.getenv("DM_WORKSPACE_ROOT")
    or os.path.join(os.path.expanduser("~"), ".gemini", "antigravity-ide", "scratch")
).resolve()

_ALLOWED_COMMAND_PREFIXES = (
    "pytest", "python", "pip", ".venv\\Scripts\\python",
    ".venv/bin/python", "dir", "ls", "cat", "type",
)


def _safe_path(raw: str) -> Path:
    """Resolve path relative to workspace root, rejecting directory traversal."""
    p = (_WORKSPACE_ROOT / raw).resolve()
    if not str(p).startswith(str(_WORKSPACE_ROOT)):
        raise PermissionError(f"Path '{raw}' is outside workspace root.")
    return p


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------

def tool_write_file(path: str, content: str) -> Dict[str, Any]:
    """Write content to a file inside the workspace."""
    try:
        target = _safe_path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        log.info(f"[AgentTools] write_file: {target} ({len(content)} chars)")
        return {"ok": True, "path": str(target), "bytes_written": len(content.encode())}
    except Exception as exc:
        log.error(f"[AgentTools] write_file error: {exc}")
        return {"ok": False, "error": str(exc)}


def tool_read_file(path: str, max_chars: int = 8000) -> Dict[str, Any]:
    """Read file contents (truncated to max_chars for context safety)."""
    try:
        target = _safe_path(path)
        if not target.exists():
            return {"ok": False, "error": f"File not found: {path}"}
        content = target.read_text(encoding="utf-8", errors="replace")
        truncated = len(content) > max_chars
        return {
            "ok": True,
            "path": str(target),
            "content": content[:max_chars],
            "truncated": truncated,
            "total_chars": len(content),
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def tool_list_dir(path: str = ".") -> Dict[str, Any]:
    """List files and directories at a given path."""
    try:
        target = _safe_path(path)
        if not target.exists():
            return {"ok": False, "error": f"Path not found: {path}"}
        entries = []
        for item in sorted(target.iterdir()):
            entries.append({
                "name": item.name,
                "type": "dir" if item.is_dir() else "file",
                "size": item.stat().st_size if item.is_file() else None,
            })
        return {"ok": True, "path": str(target), "entries": entries}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def tool_run_command(command: str, cwd: str = ".") -> Dict[str, Any]:
    """
    Execute a shell command inside the workspace.
    Only allowed prefixes: pytest, python, pip, dir, ls, cat, type.
    """
    cmd_lower = command.strip().lower()
    if not any(cmd_lower.startswith(p) for p in _ALLOWED_COMMAND_PREFIXES):
        return {
            "ok": False,
            "error": (
                f"Command '{command}' is not in the allowed list. "
                f"Allowed: {_ALLOWED_COMMAND_PREFIXES}"
            ),
        }
    try:
        work_dir = _safe_path(cwd)
        result = subprocess.run(
            command,
            shell=True,
            cwd=str(work_dir),
            capture_output=True,
            text=True,
            timeout=120,
        )
        return {
            "ok": result.returncode == 0,
            "returncode": result.returncode,
            "stdout": result.stdout[:4000],
            "stderr": result.stderr[:2000],
        }
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "Command timed out after 120s"}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def tool_search_file(path: str, query: str) -> Dict[str, Any]:
    """Search for a string pattern inside a file, return matching lines."""
    try:
        target = _safe_path(path)
        if not target.exists():
            return {"ok": False, "error": f"File not found: {path}"}
        lines = target.read_text(encoding="utf-8", errors="replace").splitlines()
        matches = [
            {"line": i + 1, "content": line}
            for i, line in enumerate(lines)
            if query.lower() in line.lower()
        ]
        return {"ok": True, "path": str(target), "query": query, "matches": matches[:50]}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


# ---------------------------------------------------------------------------
# Tool registry & dispatcher
# ---------------------------------------------------------------------------

TOOL_DEFINITIONS: List[Dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Create or overwrite a file with given content inside the project workspace.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Relative path from workspace root, e.g. 'src/specialists/my_module.py'",
                    },
                    "content": {
                        "type": "string",
                        "description": "Full file content to write.",
                    },
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read the contents of an existing file in the workspace.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Relative file path."},
                    "max_chars": {
                        "type": "integer",
                        "description": "Maximum characters to return (default 8000).",
                        "default": 8000,
                    },
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_dir",
            "description": "List files and directories at a given path in the workspace.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Relative directory path (default '.').", "default": "."},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_command",
            "description": "Execute a safe shell command (pytest, python, pip, ls, dir). Returns stdout/stderr.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "Command to run."},
                    "cwd": {"type": "string", "description": "Working directory relative to workspace root.", "default": "."},
                },
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_file",
            "description": "Search for a text pattern inside a file and return matching lines with line numbers.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Relative file path."},
                    "query": {"type": "string", "description": "Text to search for (case-insensitive)."},
                },
                "required": ["path", "query"],
            },
        },
    },
]

_TOOL_MAP = {
    "write_file": tool_write_file,
    "read_file": tool_read_file,
    "list_dir": tool_list_dir,
    "run_command": tool_run_command,
    "search_file": tool_search_file,
}


def dispatch_tool(name: str, arguments: Dict[str, Any]) -> str:
    """Execute a tool by name and return JSON string result."""
    fn = _TOOL_MAP.get(name)
    if fn is None:
        return json.dumps({"ok": False, "error": f"Unknown tool: '{name}'"})
    try:
        result = fn(**arguments)
        return json.dumps(result, ensure_ascii=False)
    except Exception as exc:
        return json.dumps({"ok": False, "error": str(exc)})


# ---------------------------------------------------------------------------
# Agentic Loop — drives the LLM through multi-step tool use
# ---------------------------------------------------------------------------

_OLLAMA_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
_CODING_MODEL = os.getenv("OLLAMA_CODING_MODEL", "qwen2.5-coder:7b")
_MAX_ITERATIONS = 20  # prevent infinite loops


async def run_agentic_loop(
    user_request: str,
    model: Optional[str] = None,
    max_iterations: int = _MAX_ITERATIONS,
    on_tool_call: Optional[Any] = None,   # optional callback(name, args, result)
) -> str:
    """
    Execute the local LLM in an agentic loop with tool calling.

    The model can call write_file, read_file, list_dir, run_command, search_file
    until it produces a final text response.

    Args:
        user_request:   The coding task description.
        model:          Ollama model name (default OLLAMA_CODING_MODEL env var).
        max_iterations: Safety limit for tool call rounds.
        on_tool_call:   Optional async callback called after each tool execution.

    Returns:
        Final model response text.
    """
    model = model or _CODING_MODEL
    system_prompt = (
        "You are an expert software engineer with access to tools that allow you to "
        "read and write files, list directories, and run commands inside the project workspace.\n\n"
        "Rules:\n"
        "- Always use write_file to create or modify source files — never just describe what to write.\n"
        "- After writing files, use run_command to run pytest and verify your changes.\n"
        "- Read existing files before modifying them to preserve the existing architecture.\n"
        "- Follow production-quality standards: type hints, docstrings, error handling.\n"
        "- When done, summarize what files you created/modified and the test results."
    )

    messages: List[Dict[str, Any]] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_request},
    ]

    async with httpx.AsyncClient(timeout=600.0) as client:
        for iteration in range(max_iterations):
            log.info(f"[AgenticLoop] Iteration {iteration + 1}/{max_iterations} | messages={len(messages)}")

            payload = {
                "model": model,
                "messages": messages,
                "stream": False,
                "tools": TOOL_DEFINITIONS,
            }

            try:
                resp = await client.post(f"{_OLLAMA_URL}/api/chat", json=payload)
                resp.raise_for_status()
                data = resp.json()
            except httpx.TimeoutException:
                log.error("[AgenticLoop] Ollama request timed out.")
                return "Error: The model took too long to respond. Try a simpler task or increase OLLAMA_TIMEOUT_CODING."
            except Exception as exc:
                log.error(f"[AgenticLoop] Ollama error: {exc}")
                return f"Error communicating with Ollama: {exc}"

            assistant_msg = data.get("message", {})
            messages.append({"role": "assistant", **assistant_msg})

            tool_calls = assistant_msg.get("tool_calls") or []
            if not tool_calls:
                # Model is done — return final text
                final = assistant_msg.get("content", "").strip()
                log.info(f"[AgenticLoop] Completed in {iteration + 1} iterations. Final len={len(final)}")
                return final

            # Execute all tool calls and collect results
            for tc in tool_calls:
                fn_info = tc.get("function", {})
                tool_name = fn_info.get("name", "")
                raw_args = fn_info.get("arguments", {})
                if isinstance(raw_args, str):
                    try:
                        raw_args = json.loads(raw_args)
                    except json.JSONDecodeError:
                        raw_args = {}

                log.info(f"[AgenticLoop] Tool call: {tool_name}({list(raw_args.keys())})")
                result_json = dispatch_tool(tool_name, raw_args)

                if on_tool_call:
                    try:
                        await on_tool_call(tool_name, raw_args, json.loads(result_json))
                    except Exception:
                        pass

                messages.append({
                    "role": "tool",
                    "content": result_json,
                })

    log.warning(f"[AgenticLoop] Reached max_iterations={max_iterations} without final response.")
    return f"The agent reached the maximum number of iterations ({max_iterations}) without finishing. Try a more focused task."
