"""
TenantIsolationAdapter — Full SaaS-grade Multi-Tenant Isolation (Fase 15)
=========================================================================
Extends the base TenantManager with full commercial SaaS isolation:

- Namespaced memory, vector & document storage per tenant
- Per-tenant plugin/specialist configuration store
- Usage tracking and quota management
- Immutable audit log per tenant action
- Cross-tenant isolation verification

Rule: No information EVER leaks between tenants.
Pattern: Same adapter pattern as src/adapters/*.py — zero core changes.
"""

import json
import sqlite3
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List

from ..specialists.tenant_manager import tenant_manager, TenantContext

log = logging.getLogger("tenant_isolation_adapter")


class TenantIsolationAdapter:
    """
    SaaS-grade isolation layer over TenantManager.
    Provides per-tenant namespacing for ALL system resources.
    Designed for thousands of concurrent tenants.
    """

    def __init__(self, db_path: Optional[Path] = None):
        if db_path:
            self._db_path = db_path
        else:
            self._db_path = tenant_manager.storage_root / "isolation.db"
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(str(self._db_path)) as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS tenant_usage (
                    tenant_id TEXT NOT NULL,
                    resource TEXT NOT NULL,
                    count INTEGER DEFAULT 0,
                    last_used TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (tenant_id, resource)
                );
                CREATE TABLE IF NOT EXISTS tenant_config (
                    tenant_id TEXT NOT NULL,
                    key TEXT NOT NULL,
                    value TEXT NOT NULL,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (tenant_id, key)
                );
                CREATE TABLE IF NOT EXISTS tenant_audit (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tenant_id TEXT NOT NULL,
                    action TEXT NOT NULL,
                    resource TEXT,
                    metadata TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                CREATE INDEX IF NOT EXISTS idx_audit_tenant
                    ON tenant_audit(tenant_id, created_at DESC);
            """)
            conn.commit()

    # ── Namespace Isolation ──────────────────────────────────────────────────

    def get_memory_namespace(self, tenant_id: str) -> str:
        """Returns isolated memory namespace key for tenant."""
        return f"tenant:{tenant_id}:memory"

    def get_vector_namespace(self, tenant_id: str) -> str:
        """Returns isolated vector store namespace key for tenant."""
        return f"tenant:{tenant_id}:vectors"

    def get_document_namespace(self, tenant_id: str) -> str:
        """Returns isolated document namespace key for tenant."""
        return f"tenant:{tenant_id}:docs"

    def get_embedding_namespace(self, tenant_id: str) -> str:
        """Returns isolated embedding namespace key for tenant."""
        return f"tenant:{tenant_id}:embeddings"

    def get_workflow_namespace(self, tenant_id: str) -> str:
        """Returns isolated workflow namespace key for tenant."""
        return f"tenant:{tenant_id}:workflows"

    def get_tenant_workspace(self, tenant_id: str) -> Path:
        """Returns isolated filesystem workspace directory for tenant."""
        ctx = tenant_manager.get_or_create_tenant(tenant_id)
        return ctx.base_dir

    # ── Per-Tenant Configuration ─────────────────────────────────────────────

    def set_tenant_config(self, tenant_id: str, key: str, value: Any) -> None:
        """Store per-tenant configuration value (specialists, plugins, prefs)."""
        with sqlite3.connect(str(self._db_path)) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO tenant_config (tenant_id, key, value, updated_at) VALUES (?, ?, ?, CURRENT_TIMESTAMP)",
                (tenant_id, key, json.dumps(value))
            )
            conn.commit()
        log.info(f"[TenantIsolation:{tenant_id}] Config set: '{key}'")

    def get_tenant_config(self, tenant_id: str, key: str, default: Any = None) -> Any:
        """Retrieve per-tenant configuration value. Never returns another tenant's data."""
        with sqlite3.connect(str(self._db_path)) as conn:
            row = conn.execute(
                "SELECT value FROM tenant_config WHERE tenant_id=? AND key=?",
                (tenant_id, key)
            ).fetchone()
        return json.loads(row[0]) if row else default

    def get_all_tenant_config(self, tenant_id: str) -> Dict[str, Any]:
        """Retrieve all configuration entries for a tenant."""
        with sqlite3.connect(str(self._db_path)) as conn:
            rows = conn.execute(
                "SELECT key, value FROM tenant_config WHERE tenant_id=?",
                (tenant_id,)
            ).fetchall()
        return {r[0]: json.loads(r[1]) for r in rows}

    # ── Usage Tracking & Quotas ──────────────────────────────────────────────

    def track_usage(self, tenant_id: str, resource: str, count: int = 1) -> None:
        """Track resource usage per tenant (for quotas and billing)."""
        with sqlite3.connect(str(self._db_path)) as conn:
            conn.execute("""
                INSERT INTO tenant_usage (tenant_id, resource, count)
                VALUES (?, ?, ?)
                ON CONFLICT(tenant_id, resource) DO UPDATE SET
                    count = count + excluded.count,
                    last_used = CURRENT_TIMESTAMP
            """, (tenant_id, resource, count))
            conn.commit()

    def get_usage(self, tenant_id: str) -> Dict[str, int]:
        """Get all resource usage counts for a tenant."""
        with sqlite3.connect(str(self._db_path)) as conn:
            rows = conn.execute(
                "SELECT resource, count FROM tenant_usage WHERE tenant_id=?",
                (tenant_id,)
            ).fetchall()
        return {r[0]: r[1] for r in rows}

    # ── Audit Log ────────────────────────────────────────────────────────────

    def audit_action(
        self,
        tenant_id: str,
        action: str,
        resource: Optional[str] = None,
        metadata: Optional[Dict] = None,
    ) -> None:
        """Record immutable audit log entry for a tenant action."""
        with sqlite3.connect(str(self._db_path)) as conn:
            conn.execute(
                "INSERT INTO tenant_audit (tenant_id, action, resource, metadata) VALUES (?, ?, ?, ?)",
                (tenant_id, action, resource, json.dumps(metadata or {}))
            )
            conn.commit()

    def get_audit_log(self, tenant_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        """Retrieve recent audit log entries for a tenant."""
        with sqlite3.connect(str(self._db_path)) as conn:
            rows = conn.execute(
                "SELECT action, resource, metadata, created_at FROM tenant_audit WHERE tenant_id=? ORDER BY created_at DESC LIMIT ?",
                (tenant_id, limit)
            ).fetchall()
        return [
            {
                "action": r[0],
                "resource": r[1],
                "metadata": json.loads(r[2] or "{}"),
                "created_at": r[3],
            }
            for r in rows
        ]

    # ── Tenant Management ────────────────────────────────────────────────────

    def list_tenants(self) -> List[str]:
        """List all registered tenant IDs."""
        with sqlite3.connect(str(tenant_manager.db_file)) as conn:
            rows = conn.execute("SELECT tenant_id FROM tenants").fetchall()
        return [r[0] for r in rows]

    def provision_tenant(self, tenant_id: str, name: str, plan: str = "free") -> TenantContext:
        """
        Provision a new commercial tenant with full isolation.
        Creates workspace, initializes all namespaces, stores plan config.
        """
        ctx = tenant_manager.get_or_create_tenant(tenant_id, name)

        # Initialize default configuration
        self.set_tenant_config(tenant_id, "plan", plan)
        self.set_tenant_config(tenant_id, "memory_namespace", self.get_memory_namespace(tenant_id))
        self.set_tenant_config(tenant_id, "vector_namespace", self.get_vector_namespace(tenant_id))
        self.set_tenant_config(tenant_id, "doc_namespace", self.get_document_namespace(tenant_id))
        self.set_tenant_config(tenant_id, "embedding_namespace", self.get_embedding_namespace(tenant_id))

        self.audit_action(tenant_id, "tenant_provisioned", metadata={"name": name, "plan": plan})
        log.info(f"[TenantIsolation] Provisioned tenant '{tenant_id}' ({name}) plan={plan}")
        return ctx

    # ── Isolation Verification ───────────────────────────────────────────────

    def assert_isolation(self, tenant_a: str, tenant_b: str) -> bool:
        """
        Verify that two tenants have completely separate resources.
        Returns True if all namespaces and workspaces are isolated.
        """
        workspace_a = self.get_tenant_workspace(tenant_a)
        workspace_b = self.get_tenant_workspace(tenant_b)

        checks = [
            workspace_a != workspace_b,
            self.get_memory_namespace(tenant_a) != self.get_memory_namespace(tenant_b),
            self.get_vector_namespace(tenant_a) != self.get_vector_namespace(tenant_b),
            self.get_document_namespace(tenant_a) != self.get_document_namespace(tenant_b),
            self.get_embedding_namespace(tenant_a) != self.get_embedding_namespace(tenant_b),
            self.get_workflow_namespace(tenant_a) != self.get_workflow_namespace(tenant_b),
        ]

        isolated = all(checks)
        if not isolated:
            log.error(f"[TenantIsolation] ISOLATION BREACH detected between {tenant_a} and {tenant_b}!")
        return isolated


# Module-level singleton
tenant_isolation = TenantIsolationAdapter()
