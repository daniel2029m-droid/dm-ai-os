"""
DM AI OS v1.5.2 — Safe Textual Tool Call Parser & Dispatcher
Safely extracts and validates JSON tool calls from raw LLM text streams, enforces ACLs,
prevents path traversal, and executes whitelisted physical workspace tools.
"""
import re
import json
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

from .models import PermissionMode, SessionStatus, AntigravityAction
from .permissions import permissions_engine

log = logging.getLogger("antigravity_tool_parser")
WORKSPACE_ROOT = Path(".").resolve()

# Strict Whitelist of Authorized Tools
WHITELISTED_READ_TOOLS = {
    "list_workspace_directory",
    "list_directory",
    "read_workspace_file",
    "read_file",
    "view_file",
    "search_code"
}

WHITELISTED_MUTATING_TOOLS = {
    "write_to_file",
    "replace_file_content",
    "run_command",
    "delete_file"
}


def is_safe_path(target_path: Path) -> bool:
    """Ensures target path stays strictly inside WORKSPACE_ROOT."""
    try:
        resolved = target_path.resolve()
        return resolved == WORKSPACE_ROOT or resolved.is_relative_to(WORKSPACE_ROOT)
    except Exception:
        return False


# ── PHYSICAL TOOL IMPLEMENTATIONS ─────────────────────────────────────────────
def execute_list_directory(arguments: Dict[str, Any]) -> str:
    subpath = arguments.get("subpath") or arguments.get("path") or arguments.get("DirectoryPath") or "."
    clean_subpath = str(subpath).strip().strip("/\\")
    if clean_subpath in ("", ".", "scratch", "workspace"):
        target = WORKSPACE_ROOT
    else:
        target = (WORKSPACE_ROOT / clean_subpath).resolve()

    if not is_safe_path(target):
        return "[ERROR: ACCESS_DENIED - Path traversal outside workspace is blocked]"

    if not target.exists():
        return f"[ERROR: DIRECTORY_NOT_FOUND - '{subpath}' does not exist on disk]"

    if not target.is_dir():
        return f"[ERROR: NOT_A_DIRECTORY - '{subpath}' is a file]"

    items = []
    for p in sorted(target.iterdir()):
        kind = "[DIR]" if p.is_dir() else "[FILE]"
        items.append(f"{kind} {p.name}")
    return "\n".join(items) if items else "(Empty directory)"


def list_workspace_directory(subpath: str = ".") -> str:
    """Lists files and directories in the workspace directory.

    Use this tool exclusively to inspect files and folders in a directory.
    This tool does NOT read file contents and does NOT require a file_path argument.

    Args:
        subpath: Optional relative directory path to list. Defaults to "." for workspace root.

    Returns:
        A list of files and folders found on disk.
    """
    return execute_list_directory({"subpath": subpath})


def read_workspace_file(file_path: str = "README.md") -> str:
    """Reads the text content of a specific file in the workspace.

    Use this tool exclusively to read files on disk.
    This tool does NOT list directories and requires a file_path argument.

    Args:
        file_path: The relative path of the file to read (for example 'README.md').

    Returns:
        The text content of the file.
    """
    return execute_read_file({"file_path": file_path})




def execute_read_file(arguments: Dict[str, Any]) -> str:
    file_path = arguments.get("file_path") or arguments.get("path") or arguments.get("AbsolutePath") or arguments.get("TargetFile") or ""
    if not file_path:
        return "[ERROR: INVALID_ARGUMENTS - No file path provided]"

    clean_path = str(file_path).strip().strip("/\\")
    for prefix in ["workspace/scratch/", "scratch/", "Code/", "workspace/", "root/", "app/"]:
        if clean_path.startswith(prefix):
            clean_path = clean_path[len(prefix):]

    target = (WORKSPACE_ROOT / clean_path).resolve()
    # If hallucinated subdirectory, check if filename exists directly in root
    if (not target.exists() or not target.is_file()) and (WORKSPACE_ROOT / Path(clean_path).name).is_file():
        target = (WORKSPACE_ROOT / Path(clean_path).name).resolve()

    if not is_safe_path(target):
        return "[ERROR: ACCESS_DENIED - Path traversal outside workspace is blocked]"

    if not target.exists() or not target.is_file():
        return f"[ERROR: FILE_NOT_FOUND - The requested file '{file_path}' does not exist on disk]"

    try:
        content = target.read_text(encoding="utf-8", errors="ignore")
        return content[:4000]
    except Exception as e:
        return f"[ERROR: READ_FAILURE - {e}]"



def execute_search_code(arguments: Dict[str, Any]) -> str:
    query = arguments.get("query") or arguments.get("Query") or ""
    if not query:
        return "[ERROR: INVALID_ARGUMENTS - No search query provided]"

    matches = []
    for p in WORKSPACE_ROOT.rglob("*.*"):
        if any(skip in p.parts for skip in [".git", ".venv", "__pycache__", "node_modules", "data"]):
            continue
        if p.is_file():
            try:
                content = p.read_text(encoding="utf-8", errors="ignore")
                for idx, line in enumerate(content.splitlines(), 1):
                    if query.lower() in line.lower():
                        rel = p.relative_to(WORKSPACE_ROOT)
                        matches.append(f"{rel}:{idx} {line.strip()[:100]}")
                        if len(matches) >= 20:
                            break
            except Exception:
                pass
        if len(matches) >= 20:
            break

    return "\n".join(matches) if matches else f"(No matches found for '{query}')"


class SafeTextualToolParser:
    """
    Parses, validates and safely dispatches tool calls emitted as text JSON by LLMs.
    """

    @staticmethod
    def extract_tool_calls(text: str) -> List[Dict[str, Any]]:
        """
        Extracts all valid JSON objects containing 'name' and 'arguments' using brace depth scanning
        with fallback regex for slightly malformed model outputs.
        """
        found_calls = []
        if not text:
            return found_calls

        # 1. Brace depth scanning for valid JSON
        start_indices = [i for i, ch in enumerate(text) if ch == "{"]
        for start in start_indices:
            depth = 0
            for end in range(start, len(text)):
                if text[end] == "{":
                    depth += 1
                elif text[end] == "}":
                    depth -= 1
                    if depth == 0:
                        candidate = text[start:end+1]
                        try:
                            data = json.loads(candidate)
                            if isinstance(data, dict) and "name" in data:
                                tname = str(data["name"]).strip()
                                args = data.get("arguments", {})
                                if not isinstance(args, dict):
                                    args = {}
                                if tname not in [fc["name"] for fc in found_calls]:
                                    found_calls.append({
                                        "name": tname,
                                        "arguments": args
                                    })
                        except Exception:
                            # Fallback extraction for malformed JSON arguments
                            name_m = re.search(r'"name"\s*:\s*"([a-zA-Z0-9_]+)"', candidate)
                            if name_m:
                                tname = name_m.group(1).strip()
                                if tname not in [fc["name"] for fc in found_calls]:
                                    found_calls.append({
                                        "name": tname,
                                        "arguments": {}
                                    })
                        break

        # 2. Top-level regex fallback if no objects parsed
        if not found_calls:
            for m in re.finditer(r'"name"\s*:\s*"([a-zA-Z0-9_]+)"', text):
                tname = m.group(1).strip()
                if tname not in [fc["name"] for fc in found_calls]:
                    found_calls.append({
                        "name": tname,
                        "arguments": {}
                    })

        return found_calls



    @classmethod
    def dispatch_tool(
        cls,
        tool_name: str,
        arguments: Dict[str, Any],
        permission_mode: PermissionMode
    ) -> Tuple[bool, str, Optional[AntigravityAction]]:
        """
        Validates ACL, executes if authorized, or generates pending action if approval required.
        Returns: (success, result_or_reason, pending_action)
        """
        normalized_name = tool_name.lower().strip()

        # Map aliases
        if normalized_name in ("list_directory", "list_workspace_directory"):
            actual_tool = "list_workspace_directory"
        elif normalized_name in ("read_file", "view_file", "read_workspace_file"):
            actual_tool = "read_workspace_file"
        elif normalized_name == "search_code":
            actual_tool = "search_code"
        elif normalized_name in ("write_to_file", "write_file"):
            actual_tool = "write_to_file"
        elif normalized_name in ("replace_file_content", "edit_file"):
            actual_tool = "replace_file_content"
        elif normalized_name in ("run_command", "execute_command"):
            actual_tool = "run_command"
        else:
            return False, f"[ERROR: TOOL_NOT_PERMITTED - '{tool_name}' is not in the authorized whitelist]", None

        # 1. READ TOOLS
        if actual_tool in ("list_workspace_directory", "read_workspace_file", "search_code"):
            if actual_tool == "list_workspace_directory":
                output = execute_list_directory(arguments)
            elif actual_tool == "read_workspace_file":
                output = execute_read_file(arguments)
            elif actual_tool == "search_code":
                output = execute_search_code(arguments)
            return True, output, None

        # 2. MUTATING TOOLS -> Evaluate ACL
        allowed, reason, pending_action = permissions_engine.evaluate_tool(
            tool_name=actual_tool,
            params=arguments,
            mode=permission_mode
        )

        if not allowed and pending_action is None:
            # Strictly BLOCKED in READ_ONLY
            return False, f"BLOCKED\n\n{reason}", None

        if pending_action:
            # APPROVAL REQUIRED
            return False, "PENDING_USER_APPROVAL", pending_action

        # AUTONOMOUS (if explicitly allowed)
        return True, f"Action '{actual_tool}' authorized in AUTONOMOUS mode.", None


safe_tool_parser = SafeTextualToolParser()
