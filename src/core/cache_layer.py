"""
CacheLayer - SHA-256 hash-indexed cache to eliminate duplicate web searches
and LLM invocations when responses remain valid.
"""

import hashlib
import json
import os
import time
import logging
from pathlib import Path
from typing import Optional, Any

log = logging.getLogger("cache_layer")

class CacheLayer:
    def __init__(self, cache_dir: Optional[str] = None, default_ttl_sec: int = 86400):
        if not cache_dir:
            cache_dir = os.getenv("DM_CACHE_DIR")
        if not cache_dir:
            base_storage = os.getenv("DM_STORAGE_DIR") or os.getenv("DM_DATA_DIR")
            if base_storage:
                cache_dir = os.path.join(base_storage, "Cache")
            elif os.getenv("VERCEL"):
                cache_dir = "/tmp/cache"
            else:
                cache_dir = os.path.join(
                    os.path.expanduser("~"),
                    ".gemini", "antigravity-ide", "scratch", "Project_State", "Cache"
                )
        self.cache_dir = Path(cache_dir)
        self.default_ttl = default_ttl_sec

    def _ensure_dir(self):
        """Lazy creation of cache directory with fallback to /tmp/cache for Vercel/read-only environments."""
        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
        except Exception:
            self.cache_dir = Path("/tmp/cache")
            self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _hash_key(self, prefix: str, key_data: Any) -> str:
        serialized = json.dumps(key_data, sort_keys=True)
        h = hashlib.sha256(serialized.encode("utf-8")).hexdigest()[:16]
        return f"{prefix}_{h}"

    def get(self, prefix: str, key_data: Any) -> Optional[Any]:
        """Retrieve cached payload if it exists and has not expired."""
        cache_id = self._hash_key(prefix, key_data)
        if not self.cache_dir.exists():
            return None

        file_path = self.cache_dir / f"{cache_id}.json"
        if not file_path.exists():
            return None

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            created_at = data.get("created_at", 0)
            ttl = data.get("ttl", self.default_ttl)

            if time.time() - created_at > ttl:
                log.info(f"[CacheLayer] Expired entry: {cache_id}")
                file_path.unlink(missing_ok=True)
                return None

            log.info(f"[CacheLayer] HIT: {cache_id}")
            return data.get("payload")
        except Exception as e:
            log.error(f"[CacheLayer] Read error for {cache_id}: {e}")
            return None

    def set(self, prefix: str, key_data: Any, payload: Any, ttl_sec: Optional[int] = None):
        """Store payload in SHA-256 hash cache."""
        self._ensure_dir()
        cache_id = self._hash_key(prefix, key_data)
        file_path = self.cache_dir / f"{cache_id}.json"

        entry = {
            "created_at": time.time(),
            "ttl": ttl_sec if ttl_sec is not None else self.default_ttl,
            "payload": payload
        }

        try:
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(entry, f, indent=2, ensure_ascii=False)
            log.info(f"[CacheLayer] STORED: {cache_id}")
        except Exception as e:
            log.error(f"[CacheLayer] Store error for {cache_id}: {e}")

    def clear(self):
        """Delete all cached files in the cache directory."""
        if not self.cache_dir.exists():
            return
        for f in self.cache_dir.glob("*.json"):
            f.unlink(missing_ok=True)
        log.info("[CacheLayer] Cleared all cache entries.")

# Lazy Singleton Instance (no filesystem side-effects at import time)
cache = CacheLayer()
