"""
Tests de Fase 19 — Producto Comercial (AssistantFactory)
=========================================================
Valida:
1. Creación de asistentes para todos los tipos de negocio
2. Listado de templates disponibles (22 templates)
3. Aislamiento por tenant de asistentes
4. Resolución difusa de tipo de negocio
5. Listado de asistentes por tenant
6. Desactivación de asistentes
7. Ejecución de tareas vía asistente (con mocks)
8. Templates para casos reales (electricista, peluquería, restaurante, YouTube)

Ejecutar: python -m pytest tests/test_fase19_commercial.py -v
"""

import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch


class TestTemplateDiscovery:
    """Valida el catálogo de templates disponibles."""

    def test_templates_count_at_least_20(self, tmp_path):
        from src.commercial.assistant_factory import AssistantFactory, BUSINESS_TEMPLATES
        factory = AssistantFactory(db_path=tmp_path / "factory.db")

        templates = factory.list_available_templates()
        assert len(templates) >= 20

    def test_all_local_trade_templates_present(self, tmp_path):
        from src.commercial.assistant_factory import BUSINESS_TEMPLATES
        required_trades = ["electricista", "plomero", "refrigeracion", "mecanico"]
        for trade in required_trades:
            assert trade in BUSINESS_TEMPLATES, f"Missing template: {trade}"

    def test_all_beauty_templates_present(self, tmp_path):
        from src.commercial.assistant_factory import BUSINESS_TEMPLATES
        assert "peluqueria" in BUSINESS_TEMPLATES
        assert "manicura" in BUSINESS_TEMPLATES

    def test_all_digital_media_templates_present(self, tmp_path):
        from src.commercial.assistant_factory import BUSINESS_TEMPLATES
        required_digital = ["youtube", "tiktok", "facebook", "instagram", "fanvue", "whatsapp_business"]
        for media in required_digital:
            assert media in BUSINESS_TEMPLATES, f"Missing template: {media}"

    def test_all_professional_templates_present(self, tmp_path):
        from src.commercial.assistant_factory import BUSINESS_TEMPLATES
        required_prof = ["abogado", "contador", "medico", "profesor"]
        for prof in required_prof:
            assert prof in BUSINESS_TEMPLATES, f"Missing template: {prof}"

    def test_template_has_required_fields(self, tmp_path):
        from src.commercial.assistant_factory import AssistantFactory
        factory = AssistantFactory(db_path=tmp_path / "factory.db")
        templates = factory.list_available_templates()

        for tpl in templates:
            assert "type" in tpl
            assert "name" in tpl
            assert "description" in tpl
            assert "specialists" in tpl
            assert len(tpl["specialists"]) >= 1


class TestAssistantCreation:
    """Valida la creación de asistentes para tipos de negocio reales."""

    def test_create_electricista_assistant(self, tmp_path):
        from src.commercial.assistant_factory import AssistantFactory
        factory = AssistantFactory(db_path=tmp_path / "factory.db")

        result = factory.create_assistant("client_elec", "electricista")

        assert result["assistant_id"].startswith("asst_")
        assert result["tenant_id"] == "client_elec"
        assert result["business_type"] == "electricista"
        assert "local_business_specialist" in result["specialists"]
        assert result["primary_specialist"] == "local_business_specialist"

    def test_create_youtube_assistant(self, tmp_path):
        from src.commercial.assistant_factory import AssistantFactory
        factory = AssistantFactory(db_path=tmp_path / "factory.db")

        result = factory.create_assistant("creator_1", "youtube")

        assert result["business_type"] == "youtube"
        assert "youtube_specialist" in result["specialists"]
        assert result["primary_specialist"] == "youtube_specialist"

    def test_create_peluqueria_assistant(self, tmp_path):
        from src.commercial.assistant_factory import AssistantFactory
        factory = AssistantFactory(db_path=tmp_path / "factory.db")

        result = factory.create_assistant("salon_rosa", "peluqueria")

        assert "instagram_specialist" in result["specialists"]
        assert result["primary_specialist"] == "instagram_specialist"

    def test_create_restaurante_assistant(self, tmp_path):
        from src.commercial.assistant_factory import AssistantFactory
        factory = AssistantFactory(db_path=tmp_path / "factory.db")

        result = factory.create_assistant("bistro_42", "restaurante")

        assert result["business_type"] == "restaurante"
        assert len(result["specialists"]) >= 3

    def test_create_crypto_assistant(self, tmp_path):
        from src.commercial.assistant_factory import AssistantFactory
        factory = AssistantFactory(db_path=tmp_path / "factory.db")

        result = factory.create_assistant("trader_x", "crypto")

        assert "crypto_specialist" in result["specialists"]
        assert result["primary_specialist"] == "crypto_specialist"

    def test_create_with_custom_name(self, tmp_path):
        from src.commercial.assistant_factory import AssistantFactory
        factory = AssistantFactory(db_path=tmp_path / "factory.db")

        result = factory.create_assistant(
            "my_tenant", "tiktok", custom_name="Mi Asistente TikTok Premium"
        )
        assert result["display_name"] == "Mi Asistente TikTok Premium"

    def test_create_with_extra_config(self, tmp_path):
        from src.commercial.assistant_factory import AssistantFactory
        factory = AssistantFactory(db_path=tmp_path / "factory.db")

        result = factory.create_assistant(
            "shop_1", "facebook",
            extra_config={"facebook_page_id": "PAGE_123", "budget": 50}
        )
        assert result["config"]["facebook_page_id"] == "PAGE_123"


class TestFuzzyTemplateResolution:
    """Valida resolución difusa de tipos de negocio."""

    def test_fuzzy_match_plumber_variant(self, tmp_path):
        from src.commercial.assistant_factory import AssistantFactory
        factory = AssistantFactory(db_path=tmp_path / "factory.db")

        # "plomero" should fuzzy-match to "plomero" template
        result = factory.create_assistant("t1", "servicio de plomeria")
        assert result["business_type"] in ["plomero", "negocio_local"]

    def test_unknown_type_falls_back_to_generic(self, tmp_path):
        from src.commercial.assistant_factory import AssistantFactory
        factory = AssistantFactory(db_path=tmp_path / "factory.db")

        result = factory.create_assistant("t1", "taxidermista_exotico_XYZ")
        # Should not crash, falls back to generic negocio_local
        assert result["assistant_id"] is not None
        assert result["primary_specialist"] is not None


class TestAssistantIsolation:
    """Valida aislamiento entre asistentes de distintos tenants."""

    def test_two_tenants_get_separate_assistants(self, tmp_path):
        from src.commercial.assistant_factory import AssistantFactory
        factory = AssistantFactory(db_path=tmp_path / "factory.db")

        a1 = factory.create_assistant("client_1", "facebook")
        a2 = factory.create_assistant("client_2", "facebook")

        assert a1["assistant_id"] != a2["assistant_id"]
        assert a1["tenant_id"] != a2["tenant_id"]

    def test_list_assistants_shows_only_own_tenant(self, tmp_path):
        from src.commercial.assistant_factory import AssistantFactory
        factory = AssistantFactory(db_path=tmp_path / "factory.db")

        factory.create_assistant("tenant_a", "youtube")
        factory.create_assistant("tenant_a", "instagram")
        factory.create_assistant("tenant_b", "tiktok")

        assistants_a = factory.list_assistants("tenant_a")
        assistants_b = factory.list_assistants("tenant_b")

        assert len(assistants_a) == 2
        assert len(assistants_b) == 1
        tenant_ids_a = {a["assistant_id"] for a in assistants_a}
        tenant_ids_b = {a["assistant_id"] for a in assistants_b}
        assert tenant_ids_a.isdisjoint(tenant_ids_b)


class TestAssistantLifecycle:
    """Valida el ciclo de vida completo de un asistente."""

    def test_get_assistant_by_id(self, tmp_path):
        from src.commercial.assistant_factory import AssistantFactory
        factory = AssistantFactory(db_path=tmp_path / "factory.db")

        created = factory.create_assistant("t1", "abogado")
        retrieved = factory.get_assistant(created["assistant_id"])

        assert retrieved is not None
        assert retrieved["business_type"] == "abogado"
        assert retrieved["tenant_id"] == "t1"

    def test_get_nonexistent_assistant_returns_none(self, tmp_path):
        from src.commercial.assistant_factory import AssistantFactory
        factory = AssistantFactory(db_path=tmp_path / "factory.db")

        result = factory.get_assistant("asst_nonexistent_xyz")
        assert result is None

    def test_deactivate_assistant(self, tmp_path):
        from src.commercial.assistant_factory import AssistantFactory
        factory = AssistantFactory(db_path=tmp_path / "factory.db")

        created = factory.create_assistant("t1", "kiosco")
        success = factory.deactivate_assistant(created["assistant_id"])
        assert success is True

        retrieved = factory.get_assistant(created["assistant_id"])
        assert retrieved["active"] is False

    def test_deactivate_nonexistent_returns_false(self, tmp_path):
        from src.commercial.assistant_factory import AssistantFactory
        factory = AssistantFactory(db_path=tmp_path / "factory.db")

        result = factory.deactivate_assistant("asst_nonexistent")
        assert result is False


class TestAssistantTaskExecution:
    """Valida ejecución de tareas a través del asistente (con mocks)."""

    @pytest.mark.asyncio
    async def test_run_assistant_success(self, tmp_path):
        from src.commercial.assistant_factory import AssistantFactory
        factory = AssistantFactory(db_path=tmp_path / "factory.db")

        created = factory.create_assistant("t1", "electricista")
        assistant_id = created["assistant_id"]

        mock_worker = MagicMock()
        mock_worker.specialist_id = "local_business_specialist"
        mock_worker.execute_task = AsyncMock(return_value={
            "status": "success",
            "branding_package": "Marca completa",
            "logo_url": "https://example.com/logo.png",
        })

        with patch("src.specialists.specialist_registry.specialist_registry.route_mission", return_value=mock_worker), \
             patch("src.specialists.specialist_registry.specialist_registry.get_specialist", return_value=mock_worker):
            result = await factory.run_assistant(
                assistant_id,
                "Haz crecer mi negocio de electricidad",
            )

        assert result["status"] == "success"
        assert result["assistant_id"] == assistant_id
        assert result["business_type"] == "electricista"

    @pytest.mark.asyncio
    async def test_run_deactivated_assistant_returns_error(self, tmp_path):
        from src.commercial.assistant_factory import AssistantFactory
        factory = AssistantFactory(db_path=tmp_path / "factory.db")

        created = factory.create_assistant("t1", "youtube")
        factory.deactivate_assistant(created["assistant_id"])

        result = await factory.run_assistant(
            created["assistant_id"], "Crear video"
        )
        assert result["status"] == "error"
        assert "deactivated" in result["message"]

    @pytest.mark.asyncio
    async def test_run_nonexistent_assistant_returns_error(self, tmp_path):
        from src.commercial.assistant_factory import AssistantFactory
        factory = AssistantFactory(db_path=tmp_path / "factory.db")

        result = await factory.run_assistant("asst_not_found", "some task")
        assert result["status"] == "error"


class TestRealWorldScenarios:
    """Valida los casos de uso comerciales reales."""

    def test_electricista_bundle_covers_all_channels(self, tmp_path):
        from src.commercial.assistant_factory import AssistantFactory
        factory = AssistantFactory(db_path=tmp_path / "factory.db")
        result = factory.create_assistant("elec_01", "electricista")
        # Electrician needs: local business + social + ads
        assert "local_business_specialist" in result["specialists"]
        assert "whatsapp_specialist" in result["specialists"]

    def test_fanvue_creator_bundle(self, tmp_path):
        from src.commercial.assistant_factory import AssistantFactory
        factory = AssistantFactory(db_path=tmp_path / "factory.db")
        result = factory.create_assistant("valeria_m", "fanvue")
        assert "fanvue_specialist" in result["specialists"]
        assert result["primary_specialist"] == "fanvue_specialist"

    def test_cursos_bundle_has_course_builder(self, tmp_path):
        from src.commercial.assistant_factory import AssistantFactory
        factory = AssistantFactory(db_path=tmp_path / "factory.db")
        result = factory.create_assistant("educator_1", "cursos")
        assert "course_builder_specialist" in result["specialists"]

    def test_whatsapp_business_bundle(self, tmp_path):
        from src.commercial.assistant_factory import AssistantFactory
        factory = AssistantFactory(db_path=tmp_path / "factory.db")
        result = factory.create_assistant("negocio_wa", "whatsapp_business")
        assert "whatsapp_specialist" in result["specialists"]
        assert "sales_specialist" in result["specialists"]
