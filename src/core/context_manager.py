"""
ContextManager - Manages memory, Project_State synchronization, file context,
conversation history, and long-running task states across sessions.
"""

import os
import json
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional

log = logging.getLogger("context_manager")

class ContextManager:
    def __init__(self, project_state_dir: Optional[str] = None):
        if not project_state_dir:
            project_state_dir = os.getenv("DM_STORAGE_DIR") or os.getenv("DM_DATA_DIR")
        if not project_state_dir:
            if os.getenv("VERCEL"):
                project_state_dir = "/tmp/Project_State"
            else:
                project_state_dir = os.path.join(
                    os.path.expanduser("~"),
                    ".gemini", "antigravity-ide", "scratch", "Project_State"
                )
        self.state_dir = Path(project_state_dir)
        self.active_tasks: Dict[str, Dict[str, Any]] = {}
        self.conversation_history: List[Dict[str, str]] = []

    def _ensure_dir(self):
        try:
            self.state_dir.mkdir(parents=True, exist_ok=True)
        except Exception:
            self.state_dir = Path("/tmp/Project_State")
            self.state_dir.mkdir(parents=True, exist_ok=True)

    def read_state_file(self, filename: str) -> str:
        """Read any markdown or JSON file from Project_State/."""
        file_path = self.state_dir / filename
        if file_path.exists():
            return file_path.read_text(encoding="utf-8")
        return ""

    def write_state_file(self, filename: str, content: str) -> bool:
        """Write or update a file inside Project_State/."""
        self._ensure_dir()
        try:
            file_path = self.state_dir / filename
            file_path.write_text(content, encoding="utf-8")
            log.info(f"[ContextManager] Updated {filename}")
            return True
        except Exception as e:
            log.error(f"[ContextManager] Error writing {filename}: {e}")
            return False

    def add_conversation(self, role: str, message: str):
        """Append user/assistant message to session conversation window."""
        self.conversation_history.append({"role": role, "content": message})
        # Keep last 30 turns in memory window to minimize tokens
        if len(self.conversation_history) > 30:
            self.conversation_history.pop(0)

    def register_task(self, task_id: str, description: str, metadata: Dict[str, Any] = None):
        """Track active long-running task."""
        self.active_tasks[task_id] = {
            "description": description,
            "status": "RUNNING",
            "metadata": metadata or {}
        }

    def complete_task(self, task_id: str, result_summary: str):
        """Mark task as complete."""
        if task_id in self.active_tasks:
            self.active_tasks[task_id]["status"] = "COMPLETED"
            self.active_tasks[task_id]["result"] = result_summary

# Singleton
context_mgr = ContextManager()
