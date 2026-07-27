"""
Unified Storage Layer - Unified interface wrapping:
- SQLite (Structured records & system logs)
- Vector DB (Semantic embeddings)
- Filesystem (Artifacts & state files)
- Cache Layer (SHA-256 hash query/LLM cache)
"""

import os
import json
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional

from .knowledge_base import KnowledgeBase
from ..core.cache_layer import CacheLayer

log = logging.getLogger("storage_layer")

class StorageLayer:
    def __init__(self, base_dir: Optional[str] = None):
        if not base_dir:
            base_dir = os.path.join(
                os.path.expanduser("~"),
                ".gemini", "antigravity-ide", "scratch", "Project_State"
            )
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

        # Initialize sub-stores
        self.sqlite_db = KnowledgeBase(db_path=str(self.base_dir / "Storage" / "knowledge.db"))
        self.cache = CacheLayer(cache_dir=str(self.base_dir / "Cache"))
        self.artifacts_dir = self.base_dir / "Artifacts"
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)

    # --- Filesystem operations ---
    def save_artifact(self, filename: str, content: str) -> str:
        file_path = self.artifacts_dir / filename
        file_path.write_text(content, encoding="utf-8")
        log.info(f"[StorageLayer] Artifact saved: {filename}")
        return str(file_path)

    def read_artifact(self, filename: str) -> Optional[str]:
        file_path = self.artifacts_dir / filename
        if file_path.exists():
            return file_path.read_text(encoding="utf-8")
        return None

    # --- Cache operations ---
    def get_cache(self, prefix: str, key_data: Any) -> Optional[Any]:
        return self.cache.get(prefix, key_data)

    def set_cache(self, prefix: str, key_data: Any, payload: Any, ttl_sec: Optional[int] = None):
        self.cache.set(prefix, key_data, payload, ttl_sec)

    # --- SQLite / Knowledge operations ---
    def save_record(self, category: str, title: str, content: str, tags: List[str] = None) -> int:
        return self.sqlite_db.save_record(category, title, content, tags)

    def search_records(self, query: str, category: str = None) -> List[Dict[str, Any]]:
        return self.sqlite_db.search_records(query, category)

    # --- Cleanup operations ---
    def clear_cache(self):
        """Clear all cached entries. Used for test isolation."""
        import shutil
        cache_dir = self.cache.cache_dir
        if cache_dir.exists():
            shutil.rmtree(str(cache_dir))
            cache_dir.mkdir(parents=True, exist_ok=True)

    def close(self):
        """Cleanly close all storage backends."""
        try:
            if hasattr(self.sqlite_db, '_conn') and self.sqlite_db._conn:
                self.sqlite_db._conn.close()
        except Exception:
            pass

# Singleton
storage = StorageLayer()
