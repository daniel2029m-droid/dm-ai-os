import json
import os
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional

log = logging.getLogger("knowledge_store")

class KnowledgeStore:
    def __init__(self, vectors_dir: Optional[str] = None):
        if not vectors_dir:
            vectors_dir_env = os.getenv("DM_STORAGE_DIR") or os.getenv("DM_DATA_DIR")
            if vectors_dir_env:
                vectors_dir = Path(vectors_dir_env) / "Memory" / "vectors"
            elif os.getenv("VERCEL"):
                vectors_dir = Path("/tmp/Project_State/Memory/vectors")
            else:
                vectors_dir = Path(os.path.expanduser("~")) / ".gemini" / "antigravity-ide" / "scratch" / "Project_State" / "Memory" / "vectors"
        self.vectors_dir = Path(vectors_dir)
        self.index_file = self.vectors_dir / "vector_index.json"
        self._initialized = False

    def _ensure_store(self):
        if self._initialized:
            return
        try:
            self.vectors_dir.mkdir(parents=True, exist_ok=True)
        except Exception:
            self.vectors_dir = Path("/tmp/Project_State/Memory/vectors")
            self.vectors_dir.mkdir(parents=True, exist_ok=True)
            self.index_file = self.vectors_dir / "vector_index.json"
        self._init_store()
        self._initialized = True

    def _init_store(self):
        if not self.index_file.exists():
            self.index_file.write_text(json.dumps({"items": []}), encoding="utf-8")

    def save_vector(self, item_id: str, text: str, vector: List[float], metadata: Optional[Dict[str, Any]] = None):
        self._ensure_store()
        data = self.get_all_vectors()
        data["items"].append({
            "id": item_id,
            "text": text,
            "vector": vector,
            "metadata": metadata or {}
        })
        self.index_file.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def get_all_vectors(self) -> Dict[str, Any]:
        self._ensure_store()
        try:
            return json.loads(self.index_file.read_text(encoding="utf-8"))
        except Exception:
            return {"items": []}

knowledge_store = KnowledgeStore()
