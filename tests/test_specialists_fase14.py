"""
Tests de Fase 14 - Sistema Autónomo de Negocios (Empleados Digitales Autónomos)
=============================================================================
Valida:
1. Aislamiento Multi-Tenant & Credential Vault (TenantManager, TenantContext).
2. Registro y Routing de Intenciones (SpecialistRegistry).
3. Ejecución de los 20 Agentes Especialistas Autónomos.
4. Casos Reales del Prometo Maestro:
   - Caso 1: Negocio Local ("Haz crecer mi negocio de electricidad")
   - Caso 2: Trabajos Académicos ("Termina mis trabajos de Argentina 2000")
   - Caso 3: Canal de YouTube ("Crea un canal de YouTube")
   - Caso 4: Contenido Creadora ("Crea contenido para Valeria Montesano")
   - Caso 5: Publicidad WhatsApp ("Haz publicidad para mi negocio mediante WhatsApp")
   - Caso 6: Crecimiento Facebook ("Haz crecer mi Facebook")

Ejecutar con: python -m pytest tests/test_specialists_fase14.py -v
"""

import asyncio
import os
import tempfile
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock


# ===========================================================================
# 1. Multi-Tenant Isolation Tests
# ===========================================================================

class TestTenantManagerIsolation:
    """Valida aislamiento comercial entre clientes (Multi-Tenant)."""

    def test_tenant_context_creation(self, tmp_path):
        from src.specialists.tenant_manager import TenantManager

        tm = TenantManager(storage_root=str(tmp_path))
        client_a = tm.get_or_create_tenant("client_a", "Empresa A")
        client_b = tm.get_or_create_tenant("client_b", "Empresa B")

        assert client_a.tenant_id == "client_a"
        assert client_b.tenant_id == "client_b"
        assert client_a.base_dir != client_b.base_dir

    def test_secrets_isolation_between_tenants(self, tmp_path):
        from src.specialists.tenant_manager import TenantManager

        tm = TenantManager(storage_root=str(tmp_path))
        tenant_1 = tm.get_or_create_tenant("tenant_1", "Tenant One")
        tenant_2 = tm.get_or_create_tenant("tenant_2", "Tenant Two")

        tenant_1.save_secret("facebook_page_id", "FB_PAGE_111")
        tenant_2.save_secret("facebook_page_id", "FB_PAGE_222")

        assert tenant_1.get_secret("facebook_page_id") == "FB_PAGE_111"
        assert tenant_2.get_secret("facebook_page_id") == "FB_PAGE_222"
        assert tenant_1.get_secret("facebook_page_id") != tenant_2.get_secret("facebook_page_id")

    def test_active_providers_open_source_fallback(self, tmp_path):
        from src.specialists.tenant_manager import TenantManager

        tm = TenantManager(storage_root=str(tmp_path))
        tenant = tm.get_or_create_tenant("tenant_no_keys")
        providers = tenant.get_active_providers()
        # When no external keys provided, falls back to open source/ollama
        assert "open_source" in providers or "ollama" in providers


# ===========================================================================
# 2. Specialist Registry & Routing Tests
# ===========================================================================

class TestSpecialistRegistry:
    """Valida el registro central y el ruteo de intenciones en lenguaje natural."""

    def test_registry_contains_20_specialists(self):
        from src.specialists import specialist_registry
        specialists = specialist_registry.list_specialists()
        assert len(specialists) == 20

    def test_route_mission_facebook(self):
        from src.specialists import specialist_registry
        worker = specialist_registry.route_mission("Haz crecer mi Facebook")
        assert worker is not None
        assert worker.specialist_id == "facebook_specialist"

    def test_route_mission_electrician(self):
        from src.specialists import specialist_registry
        worker = specialist_registry.route_mission("Haz crecer mi negocio de electricidad")
        assert worker is not None
        assert worker.specialist_id == "local_business_specialist"

    def test_route_mission_youtube(self):
        from src.specialists import specialist_registry
        worker = specialist_registry.route_mission("Crea un canal de YouTube")
        assert worker is not None
        assert worker.specialist_id == "youtube_specialist"

    def test_route_mission_valeria(self):
        from src.specialists import specialist_registry
        worker = specialist_registry.route_mission("Crea contenido para Valeria Montesano")
        assert worker is not None
        assert worker.specialist_id == "fanvue_specialist"

    def test_route_mission_whatsapp(self):
        from src.specialists import specialist_registry
        worker = specialist_registry.route_mission("Haz publicidad para mi negocio mediante WhatsApp")
        assert worker is not None
        assert worker.specialist_id == "whatsapp_specialist"

    def test_route_mission_coursework(self):
        from src.specialists import specialist_registry
        worker = specialist_registry.route_mission("Termina mis trabajos de Argentina 2000")
        assert worker is not None
        assert worker.specialist_id == "education_specialist"


# ===========================================================================
# 3. Execution Tests for All 20 Workers
# ===========================================================================

class TestAll20SpecialistWorkers:
    """Valida ejecucion limpia de los 20 trabajadores autonomos."""

    @pytest.mark.asyncio
    async def test_facebook_specialist(self):
        from src.specialists import FacebookSpecialist
        worker = FacebookSpecialist("tenant_test")
        res = await worker.execute_task("Haz crecer mi Facebook de ropa deportiva")
        assert res["status"] == "success"
        assert res["specialist"] == "facebook_specialist"

    @pytest.mark.asyncio
    async def test_instagram_specialist(self):
        from src.specialists import InstagramSpecialist
        worker = InstagramSpecialist("tenant_test")
        res = await worker.execute_task("Crear Reels virales de gastronomía")
        assert res["status"] == "success"
        assert res["specialist"] == "instagram_specialist"

    @pytest.mark.asyncio
    async def test_tiktok_specialist(self):
        from src.specialists import TikTokSpecialist
        worker = TikTokSpecialist("tenant_test")
        res = await worker.execute_task("Crear guiones virales de TikTok")
        assert res["status"] == "success"
        assert res["specialist"] == "tiktok_specialist"

    @pytest.mark.asyncio
    async def test_youtube_specialist(self):
        from src.specialists import YouTubeSpecialist
        worker = YouTubeSpecialist("tenant_test")
        res = await worker.execute_task("Crea un canal de YouTube sobre finanzas")
        assert res["status"] == "success"
        assert res["specialist"] == "youtube_specialist"

    @pytest.mark.asyncio
    async def test_fanvue_specialist(self):
        from src.specialists import FanvueSpecialist
        worker = FanvueSpecialist("tenant_test")
        res = await worker.execute_task("Crea contenido para Valeria Montesano")
        assert res["status"] == "success"
        assert res["specialist"] == "fanvue_specialist"

    @pytest.mark.asyncio
    async def test_whatsapp_specialist(self):
        from src.specialists import WhatsAppSpecialist
        worker = WhatsAppSpecialist("tenant_test")
        res = await worker.execute_task("Haz publicidad para mi negocio mediante WhatsApp")
        assert res["status"] == "success"
        assert res["specialist"] == "whatsapp_specialist"

    @pytest.mark.asyncio
    async def test_seo_specialist(self):
        from src.specialists import SEOSpecialist
        worker = SEOSpecialist("tenant_test")
        res = await worker.execute_task("Optimizar SEO de mi sitio e-commerce")
        assert res["status"] == "success"
        assert res["specialist"] == "seo_specialist"

    @pytest.mark.asyncio
    async def test_research_specialist(self):
        from src.specialists import ResearchSpecialist
        worker = ResearchSpecialist("tenant_test")
        res = await worker.execute_task("Investigar avances en inteligencia artificial")
        assert res["status"] == "success"
        assert res["specialist"] == "research_specialist"

    @pytest.mark.asyncio
    async def test_content_specialist(self):
        from src.specialists import ContentSpecialist
        worker = ContentSpecialist("tenant_test")
        res = await worker.execute_task("Crear artículos de blog y posts de redes")
        assert res["status"] == "success"
        assert res["specialist"] == "content_specialist"

    @pytest.mark.asyncio
    async def test_ads_specialist(self):
        from src.specialists import AdsSpecialist
        worker = AdsSpecialist("tenant_test")
        res = await worker.execute_task("Diseñar anuncios de Meta Ads y Google")
        assert res["status"] == "success"
        assert res["specialist"] == "ads_specialist"

    @pytest.mark.asyncio
    async def test_local_business_specialist(self):
        from src.specialists import LocalBusinessSpecialist
        worker = LocalBusinessSpecialist("tenant_test")
        res = await worker.execute_task("Haz crecer mi negocio de electricidad")
        assert res["status"] == "success"
        assert res["specialist"] == "local_business_specialist"

    @pytest.mark.asyncio
    async def test_sales_specialist(self):
        from src.specialists import SalesSpecialist
        worker = SalesSpecialist("tenant_test")
        res = await worker.execute_task("Crear guion de cierre de ventas")
        assert res["status"] == "success"
        assert res["specialist"] == "sales_specialist"

    @pytest.mark.asyncio
    async def test_crypto_specialist(self):
        from src.specialists import CryptoSpecialist
        worker = CryptoSpecialist("tenant_test")
        res = await worker.execute_task("Analizar mercado de Bitcoin y Ethereum")
        assert res["status"] == "success"
        assert res["specialist"] == "crypto_specialist"

    @pytest.mark.asyncio
    async def test_customer_support_specialist(self):
        from src.specialists import CustomerSupportSpecialist
        worker = CustomerSupportSpecialist("tenant_test")
        res = await worker.execute_task("Responder consulta de garantía de producto")
        assert res["status"] == "success"
        assert res["specialist"] == "customer_support_specialist"

    @pytest.mark.asyncio
    async def test_education_specialist(self):
        from src.specialists import EducationSpecialist
        worker = EducationSpecialist("tenant_test")
        res = await worker.execute_task("Termina mis trabajos de Argentina 2000")
        assert res["status"] == "success"
        assert res["specialist"] == "education_specialist"

    @pytest.mark.asyncio
    async def test_business_specialist(self):
        from src.specialists import BusinessSpecialist
        worker = BusinessSpecialist("tenant_test")
        res = await worker.execute_task("Crear plan estratégico de negocios")
        assert res["status"] == "success"
        assert res["specialist"] == "business_specialist"

    @pytest.mark.asyncio
    async def test_analytics_specialist(self):
        from src.specialists import AnalyticsSpecialist
        worker = AnalyticsSpecialist("tenant_test")
        res = await worker.execute_task("Analizar métricas de ventas y ROAS")
        assert res["status"] == "success"
        assert res["specialist"] == "analytics_specialist"

    @pytest.mark.asyncio
    async def test_automation_specialist(self):
        from src.specialists import AutomationSpecialist
        worker = AutomationSpecialist("tenant_test")
        res = await worker.execute_task("Automatizar flujo de emails y tareas")
        assert res["status"] == "success"
        assert res["specialist"] == "automation_specialist"

    @pytest.mark.asyncio
    async def test_course_builder_specialist(self):
        from src.specialists import CourseBuilderSpecialist
        worker = CourseBuilderSpecialist("tenant_test")
        res = await worker.execute_task("Crear curso de marketing digital")
        assert res["status"] == "success"
        assert res["specialist"] == "course_builder_specialist"

    @pytest.mark.asyncio
    async def test_workflow_specialist(self):
        from src.specialists import WorkflowSpecialist
        worker = WorkflowSpecialist("tenant_test")
        res = await worker.execute_task("Ejecutar pipeline de prospección")
        assert res["status"] == "success"
        assert res["specialist"] == "workflow_specialist"


# ===========================================================================
# 4. Real-World User Scenario Suite
# ===========================================================================

class TestRealWorldUserScenarios:
    """Valida los 6 casos de uso reales del Prompt Maestro."""

    @pytest.mark.asyncio
    async def test_real_scenario_1_electrician_business(self):
        """Usuario: 'Haz crecer mi negocio de electricidad'"""
        from src.specialists import specialist_registry
        worker = specialist_registry.route_mission("Haz crecer mi negocio de electricidad")
        res = await worker.execute_task("Haz crecer mi negocio de electricidad")

        assert res["status"] == "success"
        assert "branding_package" in res
        assert "logo_url" in res
        assert "banner_url" in res

    @pytest.mark.asyncio
    async def test_real_scenario_2_argentina_2000(self):
        """Usuario: 'Termina mis trabajos de Argentina 2000'"""
        from src.specialists import specialist_registry
        worker = specialist_registry.route_mission("Termina mis trabajos de Argentina 2000")
        res = await worker.execute_task("Termina mis trabajos de Argentina 2000")

        assert res["status"] == "success"
        assert "completed_assignment" in res

    @pytest.mark.asyncio
    async def test_real_scenario_3_youtube_channel(self):
        """Usuario: 'Crea un canal de YouTube'"""
        from src.specialists import specialist_registry
        worker = specialist_registry.route_mission("Crea un canal de YouTube")
        res = await worker.execute_task("Crea un canal de YouTube sobre viajes")

        assert res["status"] == "success"
        assert "seo_package" in res
        assert "thumbnail_url" in res

    @pytest.mark.asyncio
    async def test_real_scenario_4_valeria_montesano_content(self):
        """Usuario: 'Crea contenido para Valeria Montesano'"""
        from src.specialists import specialist_registry
        worker = specialist_registry.route_mission("Crea contenido para Valeria Montesano")
        res = await worker.execute_task("Crea contenido para Valeria Montesano")

        assert res["status"] == "success"
        assert "prompts" in res
        assert "content_url" in res

    @pytest.mark.asyncio
    async def test_real_scenario_5_whatsapp_marketing(self):
        """Usuario: 'Haz publicidad para mi negocio mediante WhatsApp'"""
        from src.specialists import specialist_registry
        worker = specialist_registry.route_mission("Haz publicidad para mi negocio mediante WhatsApp")
        res = await worker.execute_task("Haz publicidad para mi negocio mediante WhatsApp")

        assert res["status"] == "success"
        assert "auto_responses" in res
        assert "flyer_url" in res

    @pytest.mark.asyncio
    async def test_real_scenario_6_facebook_growth(self):
        """Usuario: 'Haz crecer mi Facebook'"""
        from src.specialists import specialist_registry
        worker = specialist_registry.route_mission("Haz crecer mi Facebook")
        res = await worker.execute_task("Haz crecer mi Facebook")

        assert res["status"] == "success"
        assert "copy" in res
        assert "image_url" in res
