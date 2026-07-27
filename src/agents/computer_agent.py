"""
ComputerAgent - Local System & Environment Control (Phase 2 Priority #2).
Handles OS commands, environment diagnostics, and process management.
Enforces human approval safety gates before destructive shell/file operations.
"""

import os
import platform
import subprocess
import asyncio
import logging
from typing import Dict, Any, List
from pathlib import Path

from ..core.plugin_manager import BasePlugin, plugin_manager

log = logging.getLogger("computer_agent")

DESTRUCTIVE_PATTERNS = ["rmdir", "del", "remove-item", "format", "shutdown", "reg delete", "drop", "kill"]

class ComputerAgent(BasePlugin):
    @property
    def plugin_name(self) -> str:
        return "computer"

    @property
    def description(self) -> str:
        return "Local OS environment, terminal, process, and system diagnostics control agent."

    async def initialize(self) -> bool:
        log.info("[ComputerAgent] Initialized.")
        return True

    def get_system_info(self) -> Dict[str, Any]:
        return {
            "os": platform.system(),
            "release": platform.release(),
            "version": platform.version(),
            "arch": platform.machine(),
            "cpu_count": os.cpu_count(),
            "user": os.getenv("USERNAME", "unknown")
        }

    def requires_human_approval(self, command: str) -> bool:
        """Enforce safety gate for destructive terminal commands."""
        cmd_lower = command.lower()
        for pattern in DESTRUCTIVE_PATTERNS:
            if pattern in cmd_lower:
                return True
        return False

    async def execute_action(self, action_name: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        if action_name == "sys_info":
            return {"status": "success", "info": self.get_system_info()}

        if action_name == "run_command":
            cmd = payload.get("command", "")
            if not cmd:
                return {"status": "error", "message": "No command provided."}

            if self.requires_human_approval(cmd):
                log.warning(f"[ComputerAgent] Safety Gate Triggered! Command '{cmd}' requires human approval.")
                return {
                    "status": "approval_required",
                    "message": f"Command '{cmd}' is potentially destructive and requires explicit user confirmation.",
                    "command": cmd
                }

            # Safe execution via subprocess
            try:
                proc = await asyncio.create_subprocess_shell(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE
                )
                stdout, stderr = await proc.communicate()
                output = stdout.decode("utf-8", errors="replace").strip()
                err_out = stderr.decode("utf-8", errors="replace").strip()

                return {
                    "status": "success",
                    "exit_code": proc.returncode,
                    "output": output,
                    "stderr": err_out
                }
            except Exception as e:
                return {"status": "error", "message": str(e)}

        return {"status": "error", "message": f"Unknown action '{action_name}'."}

# Register instance
computer_agent_instance = ComputerAgent()
plugin_manager.register_plugin(computer_agent_instance)
