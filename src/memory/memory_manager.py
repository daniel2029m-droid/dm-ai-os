import json
import os
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional

from .short_term_memory import short_term_memory
from .long_term_memory import long_term_memory
from .knowledge_store import knowledge_store
from .embedding_engine import embedding_engine
from .memory_retriever import memory_retriever
from src.users.identity_manager import identity_manager, UserProfile

log = logging.getLogger("memory_manager")

class MemoryManager:
    def __init__(self):
        self.short_term = short_term_memory
        self.long_term = long_term_memory
        self.knowledge = knowledge_store
        self.retriever = memory_retriever
        self.identity = identity_manager

    def store_memory(self, content: str, category: str = "general", importance: float = 1.0, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        emb = embedding_engine.generate_embedding(content)
        mem_id = self.long_term.store(
            content=content,
            category=category,
            importance=importance,
            embedding=emb,
            metadata=metadata
        )
        self.knowledge.save_vector(str(mem_id), content, emb, metadata)
        log.info(f"[MemoryManager] Stored memory #{mem_id} under category '{category}'")
        return {"status": "SUCCESS", "memory_id": mem_id, "category": category}

    def retrieve_memory(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        return self.retriever.retrieve_relevant_memories(query, top_k=top_k)

    def search_memory(self, query: str, category: Optional[str] = None) -> List[Dict[str, Any]]:
        all_mem = self.long_term.get_all(category=category)
        if not query:
            return all_mem
        return [m for m in all_mem if query.lower() in m["content"].lower()]

    def forget_memory(self, memory_id: int) -> Dict[str, Any]:
        success = self.long_term.forget(memory_id)
        return {"status": "SUCCESS" if success else "FAILED", "memory_id": memory_id}

    def update_user_profile(self, key: str, value: Any, user_id: str = "daniel") -> Dict[str, Any]:
        success = self.identity.update_preference(key, value, user_id=user_id)
        return {"status": "SUCCESS" if success else "FAILED", "user_id": user_id, "key": key, "value": value}

    def get_user_profile(self, user_id: str = "daniel") -> Dict[str, Any]:
        profile = self.identity.get_profile(user_id)
        return profile.to_dict() if profile else UserProfile(user_id=user_id).to_dict()

    def summarize_context(self, user_id: str = "daniel", query: str = "") -> str:
        return self.retriever.build_context_prompt(user_id=user_id, current_query=query)

    def export_memory(self, export_path: Optional[str] = None) -> str:
        if not export_path:
            exp_dir = Path(os.path.expanduser("~")) / ".gemini" / "antigravity-ide" / "scratch" / "Project_State" / "Memory"
            exp_dir.mkdir(parents=True, exist_ok=True)
            export_path = str(exp_dir / "memory_export.json")

        data = {
            "profile": self.get_user_profile("daniel"),
            "long_term_memories": self.long_term.get_all(),
            "short_term_history": self.short_term.get_history(limit=50)
        }
        Path(export_path).write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        return export_path

    def import_memory(self, import_path: str) -> bool:
        path = Path(import_path)
        if not path.exists():
            return False
        data = json.loads(path.read_text(encoding="utf-8"))
        if "profile" in data:
            self.identity.save_profile(UserProfile.from_dict(data["profile"]))
        for m in data.get("long_term_memories", []):
            self.store_memory(m["content"], category=m.get("category", "general"), importance=m.get("importance", 1.0))
        return True

    def reset_memory(self) -> bool:
        self.long_term.clear_all()
        self.short_term.clear()
        return True

memory_manager = MemoryManager()
