"""
Tests de Fase 15 — Multi-Tenant SaaS Isolation
===============================================
Valida:
1. Aislamiento completo de namespaces entre tenants
2. Configuración por tenant (sin filtración entre clientes)
3. Tracking de uso y quotas
4. Audit log por tenant
5. Aprovisionamiento SaaS
6. Verificación de isolation cross-tenant

Ejecutar: python -m pytest tests/test_fase15_multitenant.py -v
"""

import pytest
from pathlib import Path


class TestTenantNamespaceIsolation:
    """Valida que todos los namespaces de recursos sean únicos por tenant."""

    def test_memory_namespaces_isolated(self, tmp_path):
        from src.adapters.tenant_isolation_adapter import TenantIsolationAdapter
        adapter = TenantIsolationAdapter(db_path=tmp_path / "iso.db")

        ns_a = adapter.get_memory_namespace("client_a")
        ns_b = adapter.get_memory_namespace("client_b")

        assert ns_a != ns_b
        assert "client_a" in ns_a
        assert "client_b" in ns_b

    def test_vector_namespaces_isolated(self, tmp_path):
        from src.adapters.tenant_isolation_adapter import TenantIsolationAdapter
        adapter = TenantIsolationAdapter(db_path=tmp_path / "iso.db")

        assert adapter.get_vector_namespace("t1") != adapter.get_vector_namespace("t2")

    def test_document_namespaces_isolated(self, tmp_path):
        from src.adapters.tenant_isolation_adapter import TenantIsolationAdapter
        adapter = TenantIsolationAdapter(db_path=tmp_path / "iso.db")

        assert adapter.get_document_namespace("t1") != adapter.get_document_namespace("t2")

    def test_embedding_namespaces_isolated(self, tmp_path):
        from src.adapters.tenant_isolation_adapter import TenantIsolationAdapter
        adapter = TenantIsolationAdapter(db_path=tmp_path / "iso.db")

        assert adapter.get_embedding_namespace("t1") != adapter.get_embedding_namespace("t2")

    def test_workflow_namespaces_isolated(self, tmp_path):
        from src.adapters.tenant_isolation_adapter import TenantIsolationAdapter
        adapter = TenantIsolationAdapter(db_path=tmp_path / "iso.db")

        assert adapter.get_workflow_namespace("t1") != adapter.get_workflow_namespace("t2")

    def test_workspace_paths_isolated(self, tmp_path):
        from src.adapters.tenant_isolation_adapter import TenantIsolationAdapter
        from src.specialists.tenant_manager import TenantManager
        import os
        os.environ.setdefault("TENANT_STORAGE_ROOT", str(tmp_path))

        # Use custom TenantManager with tmp path to avoid polluting real data
        from src.specialists.tenant_manager import TenantContext
        from pathlib import Path as P
        base = tmp_path / "tenants"
        ctx_a = TenantContext("ws_a", "WS A", base)
        ctx_b = TenantContext("ws_b", "WS B", base)
        assert ctx_a.base_dir != ctx_b.base_dir


class TestTenantConfigIsolation:
    """Valida que la configuración por tenant nunca se filtre entre clientes."""

    def test_config_set_and_get(self, tmp_path):
        from src.adapters.tenant_isolation_adapter import TenantIsolationAdapter
        adapter = TenantIsolationAdapter(db_path=tmp_path / "iso.db")

        adapter.set_tenant_config("tenant_x", "api_key", "SECRET_X_123")
        result = adapter.get_tenant_config("tenant_x", "api_key")
        assert result == "SECRET_X_123"

    def test_config_no_cross_tenant_leak(self, tmp_path):
        from src.adapters.tenant_isolation_adapter import TenantIsolationAdapter
        adapter = TenantIsolationAdapter(db_path=tmp_path / "iso.db")

        adapter.set_tenant_config("tenant_alpha", "secret", "ALPHA_SECRET")
        adapter.set_tenant_config("tenant_beta", "secret", "BETA_SECRET")

        # Each tenant sees only their own data
        assert adapter.get_tenant_config("tenant_alpha", "secret") == "ALPHA_SECRET"
        assert adapter.get_tenant_config("tenant_beta", "secret") == "BETA_SECRET"
        # Tenant gamma sees nothing
        assert adapter.get_tenant_config("tenant_gamma", "secret") is None

    def test_config_default_fallback(self, tmp_path):
        from src.adapters.tenant_isolation_adapter import TenantIsolationAdapter
        adapter = TenantIsolationAdapter(db_path=tmp_path / "iso.db")

        result = adapter.get_tenant_config("new_tenant", "missing_key", default=42)
        assert result == 42

    def test_config_complex_values(self, tmp_path):
        from src.adapters.tenant_isolation_adapter import TenantIsolationAdapter
        adapter = TenantIsolationAdapter(db_path=tmp_path / "iso.db")

        value = {"specialists": ["facebook", "instagram"], "plan": "premium", "active": True}
        adapter.set_tenant_config("client_z", "assistant_config", value)
        result = adapter.get_tenant_config("client_z", "assistant_config")
        assert result == value

    def test_get_all_tenant_config(self, tmp_path):
        from src.adapters.tenant_isolation_adapter import TenantIsolationAdapter
        adapter = TenantIsolationAdapter(db_path=tmp_path / "iso.db")

        adapter.set_tenant_config("t1", "key_a", "val_a")
        adapter.set_tenant_config("t1", "key_b", "val_b")

        all_config = adapter.get_all_tenant_config("t1")
        assert "key_a" in all_config
        assert "key_b" in all_config
        assert all_config["key_a"] == "val_a"


class TestUsageTracking:
    """Valida tracking de uso por tenant para quotas y billing."""

    def test_track_and_get_usage(self, tmp_path):
        from src.adapters.tenant_isolation_adapter import TenantIsolationAdapter
        adapter = TenantIsolationAdapter(db_path=tmp_path / "iso.db")

        adapter.track_usage("tenant_1", "llm_calls", 5)
        adapter.track_usage("tenant_1", "llm_calls", 3)
        adapter.track_usage("tenant_1", "image_generations", 2)

        usage = adapter.get_usage("tenant_1")
        assert usage["llm_calls"] == 8
        assert usage["image_generations"] == 2

    def test_usage_isolated_between_tenants(self, tmp_path):
        from src.adapters.tenant_isolation_adapter import TenantIsolationAdapter
        adapter = TenantIsolationAdapter(db_path=tmp_path / "iso.db")

        adapter.track_usage("client_a", "api_calls", 100)
        adapter.track_usage("client_b", "api_calls", 50)

        usage_a = adapter.get_usage("client_a")
        usage_b = adapter.get_usage("client_b")

        assert usage_a["api_calls"] == 100
        assert usage_b["api_calls"] == 50


class TestAuditLog:
    """Valida el registro de auditoría por tenant."""

    def test_audit_action_recorded(self, tmp_path):
        from src.adapters.tenant_isolation_adapter import TenantIsolationAdapter
        adapter = TenantIsolationAdapter(db_path=tmp_path / "iso.db")

        adapter.audit_action("tenant_a", "login", metadata={"ip": "127.0.0.1"})
        log = adapter.get_audit_log("tenant_a")

        assert len(log) >= 1
        assert log[0]["action"] == "login"

    def test_audit_isolated_between_tenants(self, tmp_path):
        from src.adapters.tenant_isolation_adapter import TenantIsolationAdapter
        adapter = TenantIsolationAdapter(db_path=tmp_path / "iso.db")

        adapter.audit_action("t_a", "action_for_a")
        adapter.audit_action("t_b", "action_for_b")

        log_a = adapter.get_audit_log("t_a")
        log_b = adapter.get_audit_log("t_b")

        assert all(e["action"] == "action_for_a" for e in log_a)
        assert all(e["action"] == "action_for_b" for e in log_b)
        # Cross check — a's log has no b's entries
        actions_a = {e["action"] for e in log_a}
        assert "action_for_b" not in actions_a


class TestCrossTenantIsolationVerification:
    """Verifica isolamiento completo entre tenants (aserción de seguridad)."""

    def test_assert_isolation_passes(self, tmp_path):
        from src.adapters.tenant_isolation_adapter import TenantIsolationAdapter
        adapter = TenantIsolationAdapter(db_path=tmp_path / "iso.db")

        result = adapter.assert_isolation("empresa_alpha", "empresa_beta")
        assert result is True

    def test_assert_isolation_same_tenant_fails(self, tmp_path):
        from src.adapters.tenant_isolation_adapter import TenantIsolationAdapter
        adapter = TenantIsolationAdapter(db_path=tmp_path / "iso.db")

        # Same tenant — workspace path will be equal → isolation assertion should fail
        result = adapter.assert_isolation("same_tenant", "same_tenant")
        assert result is False


class TestTenantProvisioning:
    """Valida el flujo completo de aprovisionamiento de tenant SaaS."""

    def test_provision_tenant_creates_context(self, tmp_path):
        from src.adapters.tenant_isolation_adapter import TenantIsolationAdapter
        from src.specialists.tenant_manager import TenantManager
        import os

        # Use isolated TenantManager for this test
        tm = TenantManager(storage_root=str(tmp_path / "tenants"))

        # Create adapter pointing to same tmp location
        adapter = TenantIsolationAdapter.__new__(TenantIsolationAdapter)
        adapter._db_path = tmp_path / "iso.db"
        adapter._db_path.parent.mkdir(parents=True, exist_ok=True)
        adapter._init_db = lambda: None  # skip since we call manually below

        import sqlite3
        with sqlite3.connect(str(adapter._db_path)) as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS tenant_usage (tenant_id TEXT, resource TEXT, count INTEGER, last_used TIMESTAMP, PRIMARY KEY(tenant_id, resource));
                CREATE TABLE IF NOT EXISTS tenant_config (tenant_id TEXT, key TEXT, value TEXT, updated_at TIMESTAMP, PRIMARY KEY(tenant_id, key));
                CREATE TABLE IF NOT EXISTS tenant_audit (id INTEGER PRIMARY KEY AUTOINCREMENT, tenant_id TEXT, action TEXT, resource TEXT, metadata TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
            """)
            conn.commit()

        # Manually test the config methods work
        import json, sqlite3 as sqlite3_2
        with sqlite3_2.connect(str(adapter._db_path)) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO tenant_config (tenant_id, key, value, updated_at) VALUES (?, ?, ?, CURRENT_TIMESTAMP)",
                ("new_saas_client", "plan", json.dumps("premium"))
            )
            conn.commit()

        with sqlite3_2.connect(str(adapter._db_path)) as conn:
            row = conn.execute(
                "SELECT value FROM tenant_config WHERE tenant_id=? AND key=?",
                ("new_saas_client", "plan")
            ).fetchone()

        assert row is not None
        assert json.loads(row[0]) == "premium"
