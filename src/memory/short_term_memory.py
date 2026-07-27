from typing import List, Dict, Any, Optional
from src.core.context_manager import context_mgr

class ShortTermMemory:
    def __init__(self):
        pass

    def add_message(self, role: str, content: str):
        context_mgr.add_conversation(role, content)

    def get_history(self, limit: int = 10) -> List[Dict[str, Any]]:
        return context_mgr.get_history(limit=limit)

    def register_active_task(self, task_id: str, description: str, metadata: Optional[Dict[str, Any]] = None):
        context_mgr.register_task(task_id, description, metadata)

    def complete_active_task(self, task_id: str, result: Any = None):
        context_mgr.complete_task(task_id, result)

    def get_active_tasks(self) -> Dict[str, Any]:
        return context_mgr.active_tasks

    def clear(self):
        context_mgr.clear_history()

short_term_memory = ShortTermMemory()
