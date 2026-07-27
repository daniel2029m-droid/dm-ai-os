import json
import os
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional

log = logging.getLogger("knowledge_store")

class KnowledgeStore:
    def __init__(self, vectors_dir: Optional[str] = None):
        if not vectors_dir:
            vectors_dir = Path(os.path.expanduser("~")) / ".gemini" / "antigravity-ide" / "scratch" / "Project_State" / "Memory" / "vectors"
        self.vectors_dir = Path(vectors_dir)
        self.vectors_dir.mkdir(parents=True, exist_ok=True)
        self.index_file = self.vectors_dir / "vector_index.json"
        self._init_store()

    def _init_store(self):
        if not self.index_file.exists():
            self.index_file.write_text(json.dumps({"items": []}), encoding="utf-8")

    def save_vector(self, item_id: str, text: str, vector: List[float], metadata: Optional[Dict[str, Any]] = None):
        data = self.get_all_vectors()
        data["items"].append({
            "id": item_id,
            "text": text,
            "vector": vector,
            "metadata": metadata or {}
        })
        self.index_file.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def get_all_vectors(self) -> Dict[str, Any]:
        try:
            return json.loads(self.index_file.read_text(encoding="utf-8"))
        except Exception:
            return {"items": []}

knowledge_store = KnowledgeStore()
