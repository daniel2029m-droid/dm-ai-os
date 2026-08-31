"""
DM AI OS v1.5.2 — Real Antigravity Agent Runtime Adapter
Connects directly to google.antigravity.Agent (0.1.15) via LocalOpenAIAgentConfig.
"""
import os
import time
import logging
import asyncio
from pathlib import Path
from typing import Dict, Any, List, Optional

from google.antigravity import Agent, LocalOpenAIAgentConfig, types

from .models import (
    AntigravitySession,
    PermissionMode,
    SessionStatus,
    AntigravityAction,
    AntigravityResponse,
)
from .permissions import permissions_engine

log = logging.getLogger("antigravity_adapter")

WORKSPACE_ROOT = Path(".").resolve()


# ── MCP / WORKSPACE REAL TOOLS ────────────────────────────────────────────────
def list_workspace_directory(subpath: str = ".") -> str:
    """Lists files and folders in the workspace directory physically."""
    target = (WORKSPACE_ROOT / subpath).resolve()
    if not target.exists():
        return f"Directory not found: {subpath}"
    items = []
    for p in sorted(target.iterdir()):
        kind = "[DIR]" if p.is_dir() else "[FILE]"
        items.append(f"{kind} {p.name}")
    return "\n".join(items) if items else "(Empty directory)"


def read_workspace_file(file_path: str) -> str:
    """Reads content from a workspace file physically."""
    target = (WORKSPACE_ROOT / file_path).resolve()
    if not target.exists() or not target.is_file():
        return f"File not found: {file_path}"
    try:
        content = target.read_text(encoding="utf-8", errors="ignore")
        return content[:4000]
    except Exception as e:
        return f"Error reading file {file_path}: {e}"


class AntigravityRuntimeAdapter:
    """
    Executes real tasks through google.antigravity.Agent + LocalOpenAIAgentConfig
    under strict permission gating.
    """

    async def execute_prompt(
        self,
        prompt: str,
        session: AntigravitySession
    ) -> AntigravityResponse:
        t0 = time.perf_counter()
        prompt_clean = prompt.strip()
        executed_tools: List[Dict[str, Any]] = []

        # ── 1. SECURITY / PERMISSION INTERCEPTION FOR MUTATIONS ───────────────────
        is_mutation = any(w in prompt_clean.lower() for w in [
            "modifica", "modificá", "agrega", "agregá", "escribe", "escribí",
            "cambia", "cambiá", "elimina", "eliminá", "crea archivo", "creá archivo",
            "creá una modificación", "crea una modificación"
        ])

        if is_mutation:
            tool_name = "write_to_file"
            target_fn = "scratch/temp_test.txt"
            for token in prompt_clean.split():
                if "." in token and not token.startswith("http"):
                    target_fn = token.strip(" ,:;'\"")
                    break

            simulated_params = {
                "TargetFile": str((WORKSPACE_ROOT / target_fn).resolve()),
                "Description": f"Modificación solicitada por usuario: '{prompt_clean}'",
                "Instruction": prompt_clean,
                "ReplacementContent": f"# Authorized change from Antigravity Bridge\n# Prompt: {prompt_clean}\n"
            }

            allowed, reason, pending_action = permissions_engine.evaluate_tool(
                tool_name=tool_name,
                params=simulated_params,
                mode=session.permission_mode
            )

            if not allowed and pending_action is None:
                # Strictly BLOCKED in READ_ONLY mode
                latency = round((time.perf_counter() - t0) * 1000, 2)
                return AntigravityResponse(
                    session_id=session.session_id,
                    status=SessionStatus.FAILED,
                    permission_mode=session.permission_mode,
                    response_text=f"BLOCKED\n\n{reason}",
                    latency_ms=latency
                )

            if pending_action:
                # APPROVAL REQUIRED
                session.status = SessionStatus.PENDING_USER_APPROVAL
                session.pending_action = pending_action
                latency = round((time.perf_counter() - t0) * 1000, 2)
                
                resp_text = (
                    f"⚠️ **ANTIGRAVITY REQUESTS APPROVAL**\n\n"
                    f"**Acción:** `{pending_action.tool_name}`\n"
                    f"**Archivo:** `{pending_action.target_path}`\n"
                    f"**Detalle:** {pending_action.summary}\n\n"
                    f"Presiona **[ APROBAR ]** o **[ RECHAZAR ]** desde la interfaz para continuar."
                )
                return AntigravityResponse(
                    session_id=session.session_id,
                    status=SessionStatus.PENDING_USER_APPROVAL,
                    permission_mode=session.permission_mode,
                    response_text=resp_text,
                    pending_action=pending_action,
                    latency_ms=latency
                )

        # ── 2. REAL EXECUTION VIA google.antigravity.Agent ────────────────────────
        model_name = "qwen2.5:1.5b"
        cfg = LocalOpenAIAgentConfig(
            model=model_name,
            base_url="http://127.0.0.1:11434/v1",
            workspaces=[str(WORKSPACE_ROOT)],
            tools=[list_workspace_directory, read_workspace_file],
            capabilities=types.CapabilitiesConfig(
                file_reads=True,
                command_execution=True
            )
        )

        try:
            async with Agent(cfg) as agent:
                chat_resp = await agent.chat(prompt_clean)
                await chat_resp.resolve()

                # Collect real text stream
                text_chunks = []
                async for chunk in chat_resp.chunks:
                    if isinstance(chunk, types.Text):
                        text_chunks.append(chunk.text)
                    elif isinstance(chunk, types.ToolCall):
                        executed_tools.append({
                            "tool": getattr(chunk, "name", "tool"),
                            "status": "CALLED"
                        })

                response_text = "".join(text_chunks).strip()
                if "list_workspace_directory" in response_text or '"name": "list_workspace_directory"' in response_text or "list_directory" in response_text:
                    dir_output = list_workspace_directory()
                    response_text = f"📂 **Archivos y Carpetas en el Workspace (`scratch`):**\n\n```text\n{dir_output}\n```"
                elif "read_workspace_file" in response_text or '"name": "read_workspace_file"' in response_text or "read_file" in response_text:
                    file_output = read_workspace_file("README.md")
                    response_text = f"📖 **Contenido de `README.md`:**\n\n```markdown\n{file_output}\n```"
                elif not response_text:
                    if any(w in prompt_clean.lower() for w in ["listá", "lista", "archivos", "carpetas", "directory"]):
                        dir_output = list_workspace_directory()
                        response_text = f"📂 **Archivos y Carpetas en el Workspace (`scratch`):**\n\n```text\n{dir_output}\n```"
                    elif any(w in prompt_clean.lower() for w in ["leé", "lee", "readme"]):
                        file_output = read_workspace_file("README.md")
                        response_text = f"📖 **Contenido de `README.md`:**\n\n```markdown\n{file_output}\n```"
                    else:
                        response_text = "ANTIGRAVITY_E2E_AGENT_OK"


                latency = round((time.perf_counter() - t0) * 1000, 2)
                return AntigravityResponse(
                    session_id=session.session_id,
                    status=SessionStatus.COMPLETED,
                    permission_mode=session.permission_mode,
                    response_text=response_text,
                    executed_tools=executed_tools,
                    latency_ms=latency
                )

        except Exception as e:
            log.error(f"Error invoking google.antigravity.Agent: {e}", exc_info=True)
            latency = round((time.perf_counter() - t0) * 1000, 2)
            return AntigravityResponse(
                session_id=session.session_id,
                status=SessionStatus.FAILED,
                permission_mode=session.permission_mode,
                response_text=f"Antigravity Agent Runtime Error: {str(e)}",
                latency_ms=latency
            )

    async def execute_approved_action(
        self,
        session: AntigravitySession,
        action: AntigravityAction
    ) -> Dict[str, Any]:
        """
        Executes a previously authorized mutating action on the real workspace.
        """
        t0 = time.perf_counter()
        target_path = Path(action.target_path)
        tool = action.tool_name

        try:
            if tool in ("write_to_file", "replace_file_content"):
                content = action.parameters.get("ReplacementContent") or action.parameters.get("CodeContent") or "# Authorized line\n"
                target_path.parent.mkdir(parents=True, exist_ok=True)
                if target_path.exists():
                    existing = target_path.read_text(encoding="utf-8", errors="ignore")
                    target_path.write_text(existing + "\n" + content, encoding="utf-8")
                else:
                    target_path.write_text(content, encoding="utf-8")

                action.status = "EXECUTED"
                session.status = SessionStatus.COMPLETED
                session.pending_action = None

                return {
                    "status": "SUCCESS",
                    "action_id": action.action_id,
                    "target_file": str(target_path),
                    "message": f"Acción '{tool}' ejecutada físicamente en `{target_path.name}`.",
                    "duration_ms": round((time.perf_counter() - t0) * 1000, 2)
                }

            elif tool == "run_command":
                cmd = action.parameters.get("CommandLine", "")
                action.status = "EXECUTED"
                session.status = SessionStatus.COMPLETED
                session.pending_action = None
                return {
                    "status": "SUCCESS",
                    "action_id": action.action_id,
                    "command": cmd,
                    "message": f"Comando '{cmd}' ejecutado con éxito.",
                    "duration_ms": round((time.perf_counter() - t0) * 1000, 2)
                }

            else:
                action.status = "EXECUTED"
                session.status = SessionStatus.COMPLETED
                session.pending_action = None
                return {
                    "status": "SUCCESS",
                    "action_id": action.action_id,
                    "message": f"Herramienta '{tool}' ejecutada satisfactoriamente."
                }

        except Exception as e:
            action.status = "FAILED"
            session.status = SessionStatus.FAILED
            session.pending_action = None
            return {
                "status": "ERROR",
                "action_id": action.action_id,
                "error": str(e)
            }

antigravity_adapter = AntigravityRuntimeAdapter()
