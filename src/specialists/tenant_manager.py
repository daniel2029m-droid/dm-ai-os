"""
TenantManager — Multi-Tenant SaaS Isolation & Credential Vault (Fase 14.1)
==========================================================================
Provides complete commercial isolation for each client installation.

Each tenant has:
- Isolated secrets & API credentials (Grok, ChatGPT, Gemini, Claude, RunPod, Ollama, Social logins)
- Isolated workspace storage directory
- Isolated vector & document memory namespace
- Isolated workflow & specialist configurations

Rule: Never leak or share memory, keys, or data between tenants.
"""

import os
import json
import sqlite3
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List

log = logging.getLogger("tenant_manager")


class TenantContext:
    """Represents an isolated tenant execution context."""

    def __init__(self, tenant_id: str, name: str, base_dir: Path):
        self.tenant_id = tenant_id
        self.name = name
        self.base_dir = base_dir / tenant_id
        self.docs_dir = self.base_dir / "documents"
        self.vectors_dir = self.base_dir / "vectors"
        self.workflows_dir = self.base_dir / "workflows"
        self.secrets_file = self.base_dir / "credentials.json"
        self._dirs_created = False

    def _ensure_dirs(self):
        if self._dirs_created:
            return
        try:
            for d in [self.base_dir, self.docs_dir, self.vectors_dir, self.workflows_dir]:
                d.mkdir(parents=True, exist_ok=True)
        except Exception:
            self.base_dir = Path("/tmp/Project_State/Tenants") / self.tenant_id
            self.docs_dir = self.base_dir / "documents"
            self.vectors_dir = self.base_dir / "vectors"
            self.workflows_dir = self.base_dir / "workflows"
            self.secrets_file = self.base_dir / "credentials.json"
            for d in [self.base_dir, self.docs_dir, self.vectors_dir, self.workflows_dir]:
                d.mkdir(parents=True, exist_ok=True)
        self._dirs_created = True

    def _load_secrets(self) -> Dict[str, Any]:
        if self.secrets_file.exists():
            try:
                return json.loads(self.secrets_file.read_text(encoding="utf-8"))
            except Exception:
                return {}
        return {}

    def save_secret(self, key: str, value: Any) -> None:
        """Save a credential or API key for this tenant."""
        self._ensure_dirs()
        secrets = self._load_secrets()
        secrets[key] = value
        self.secrets_file.write_text(json.dumps(secrets, indent=2), encoding="utf-8")
        log.info(f"[TenantContext:{self.tenant_id}] Saved credential key: '{key}'")

    def get_secret(self, key: str, default: Any = None) -> Any:
        """Retrieve a credential or API key for this tenant."""
        secrets = self._load_secrets()
        return secrets.get(key, default)

    def get_active_providers(self) -> List[str]:
        """
        Return list of active providers configured for this tenant.
        e.g., ['grok', 'openai', 'gemini', 'claude', 'runpod', 'ollama', 'open_source']
        """
        providers = []
        if self.get_secret("grok_api_key") or self.get_secret("grok_cookies"):
            providers.append("grok")
        if self.get_secret("openai_api_key"):
            providers.append("openai")
        if self.get_secret("gemini_api_key"):
            providers.append("gemini")
        if self.get_secret("claude_api_key"):
            providers.append("claude")
        if self.get_secret("runpod_api_key"):
            providers.append("runpod")
        if self.get_secret("ollama_url") or os.getenv("OLLAMA_BASE_URL"):
            providers.append("ollama")
        if not providers:
            providers.append("open_source")  # Pure OS local execution
        return providers


class TenantManager:
    """Manager for multi-tenant isolation and tenant switching."""

    def __init__(self, storage_root: Optional[str] = None):
        if not storage_root:
            storage_root_env = os.getenv("DM_STORAGE_DIR") or os.getenv("DM_DATA_DIR")
            if storage_root_env:
                storage_root = str(Path(storage_root_env) / "Tenants")
            elif os.getenv("VERCEL"):
                storage_root = "/tmp/Project_State/Tenants"
            else:
                storage_root = str(
                    Path(os.path.expanduser("~"))
                    / ".gemini" / "antigravity-ide" / "scratch"
                    / "Project_State" / "Tenants"
                )
        self.storage_root = Path(storage_root)
        self.db_file = self.storage_root / "tenants.db"
        self._db_initialized = False

    def _ensure_db(self):
        if self._db_initialized:
            return
        try:
            self.storage_root.mkdir(parents=True, exist_ok=True)
        except Exception:
            self.storage_root = Path("/tmp/Project_State/Tenants")
            self.storage_root.mkdir(parents=True, exist_ok=True)
            self.db_file = self.storage_root / "tenants.db"
        self._init_db()
        self._db_initialized = True

    def _init_db(self):
        with sqlite3.connect(str(self.db_file)) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS tenants (
                    tenant_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()

        # Ensure default tenant 'daniel' exists
        with sqlite3.connect(str(self.db_file)) as conn:
            conn.execute(
                "INSERT OR IGNORE INTO tenants (tenant_id, name) VALUES (?, ?)",
                ("daniel", "Daniel Morales")
            )
            conn.commit()

    def get_or_create_tenant(self, tenant_id: str, name: str = "Client") -> TenantContext:
        """Get or create isolated TenantContext for tenant_id."""
        self._ensure_db()
        with sqlite3.connect(str(self.db_file)) as conn:
            conn.execute(
                "INSERT OR IGNORE INTO tenants (tenant_id, name) VALUES (?, ?)",
                (tenant_id, name)
            )
            conn.commit()

        return TenantContext(tenant_id=tenant_id, name=name, base_dir=self.storage_root)


# Module-level singleton
tenant_manager = TenantManager()
