from typing import Tuple, Dict, Any, Optional
import logging
from .models import PermissionMode, AntigravityAction


log = logging.getLogger("antigravity_permissions")

READ_ONLY_ALLOWED_TOOLS = {
    "view_file",
    "list_dir",
    "grep_search",
    "read_url_content",
    "search_web",
    "inspect_system",
    "get_logs",
    "health_check",
    "status",
    "read_file",
}

MUTATING_TOOLS = {
    "write_to_file",
    "replace_file_content",
    "multi_replace_file_content",
    "run_command",
    "manage_task",
    "execute_script",
    "install_package",
    "delete_file",
}

class PermissionViolationError(PermissionError):
    pass

class PermissionsEngine:
    @staticmethod
    def evaluate_tool(
        tool_name: str,
        params: Dict[str, Any],
        mode: PermissionMode,
    ) -> Tuple[bool, str, Optional[AntigravityAction]]:
        """
        Evaluates whether a tool execution is allowed under the given permission mode.
        Returns:
            (is_allowed, reason, pending_action)
        """
        tool_clean = tool_name.lower().strip()
        
        # Read-only evaluation
        if tool_clean in READ_ONLY_ALLOWED_TOOLS:
            return True, "Tool is read-only and explicitly permitted", None

        # Mutating tool under READ_ONLY mode -> Strictly BLOCKED
        if mode == PermissionMode.READ_ONLY:
            msg = (
                f"🛡️ BLOQUEADO POR POLÍTICA DE SEGURIDAD [READ_ONLY]: "
                f"La acción '{tool_name}' no está permitida en modo de solo lectura. "
                f"Cambia a APPROVAL_REQUIRED o AUTONOMOUS para preparar modificaciones."
            )
            log.warning(f"[PermissionsEngine] Blocked mutating tool '{tool_name}' in READ_ONLY mode.")
            return False, msg, None

        # Mutating tool under APPROVAL_REQUIRED mode -> Requires User Approval
        if mode == PermissionMode.APPROVAL_REQUIRED:
            target_path = params.get("TargetFile") or params.get("path") or params.get("file") or params.get("CommandLine") or "System"
            summary = params.get("Description") or params.get("Instruction") or f"Ejecutar herramienta {tool_name}"
            diff = params.get("ReplacementContent") or params.get("CodeContent") or params.get("CommandLine")
            
            action = AntigravityAction(
                tool_name=tool_name,
                target_path=str(target_path),
                parameters=params,
                summary=str(summary),
                diff_preview=str(diff) if diff else None,
                status="PENDING"
            )
            msg = f"⚠️ ANTIGRAVITY REQUESTS APPROVAL para '{tool_name}' en '{target_path}'"
            log.info(f"[PermissionsEngine] Intercepted mutating tool '{tool_name}'. Created Pending Action {action.action_id}.")
            return False, msg, action

        # Mutating tool under AUTONOMOUS mode -> Allowed
        if mode == PermissionMode.AUTONOMOUS:
            return True, "Autonomous mode enabled. Action permitted.", None

        return False, "Unknown permission mode or tool", None

permissions_engine = PermissionsEngine()
