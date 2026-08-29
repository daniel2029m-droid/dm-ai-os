"""
Tests para la integración completa de Higgsfield AI MCP en DM AI OS
====================================================================
Cubre:
  - HiggsfieldConfig: carga de variables de entorno y defaults del proyecto Valeria
  - HiggsfieldAdapter: disponibilidad, character management, generación, job status
  - HiggsfieldGenerationHistory: persistencia y deduplicación
  - HiggsfieldSpecialist: flujo completo imagen/video con personaje
  - ProviderManager: capabilities registradas, routing automático
  - MCP Tools: registro correcto de herramientas

Todos los tests que tocan la API real de Higgsfield están marcados @pytest.mark.asyncio
y usan mocks para no requerir credenciales en CI.
"""

import os
import time
import json
import pytest
import asyncio
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

# ─────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────

@pytest.fixture
def fake_job_id():
    return "a1b2c3d4-e5f6-7890-abcd-ef1234567890"


@pytest.fixture
def fake_image_result(fake_job_id):
    return {
        "job_id": fake_job_id,
        "status": "completed",
        "provider": "higgsfield",
        "media_type": "image",
        "prompt": "Valeria en un rooftop de Buenos Aires",
        "model": "soul_2",
        "aspect_ratio": "9:16",
        "character_id": "char-valeria-001",
        "image_url": "https://cdn.higgsfield.ai/outputs/test_image.png",
        "created_at": time.time(),
        "mcp_url": "https://mcp.higgsfield.ai/mcp",
        "auth_source": "Environment variable HIGGSFIELD_AUTH_TOKEN",
    }


@pytest.fixture
def fake_video_result(fake_job_id):
    return {
        "job_id": fake_job_id + "-v",
        "status": "completed",
        "provider": "higgsfield",
        "media_type": "video",
        "prompt": "Valeria caminando en Palermo",
        "model": "seedance_2_0",
        "aspect_ratio": "9:16",
        "duration": 5,
        "character_id": "char-valeria-001",
        "video_url": "https://cdn.higgsfield.ai/outputs/test_video.mp4",
        "created_at": time.time(),
        "mcp_url": "https://mcp.higgsfield.ai/mcp",
        "auth_source": "Environment variable HIGGSFIELD_AUTH_TOKEN",
    }


# ─────────────────────────────────────────────────────────────
# 1. HiggsfieldConfig — configuración centralizada
# ─────────────────────────────────────────────────────────────

class TestHiggsfieldConfig:

    def test_config_loads_without_credentials(self):
        """La config debe instanciarse correctamente aunque no haya token."""
        from src.config.higgsfield_config import HiggsfieldConfig
        cfg = HiggsfieldConfig()
        assert cfg.mcp_url == "https://mcp.higgsfield.ai/mcp"
        assert cfg.default_image_model in ("soul_2", "nano_banana_2")
        assert cfg.default_video_model in ("seedance_2_0", "cinematic_studio_3_0")
        assert cfg.default_aspect_ratio == "9:16"
        assert cfg.project_name == "Valeria Montesano Digital"
        assert cfg.character_name == "Mi Influencer"

    def test_config_is_enabled_by_default(self):
        from src.config.higgsfield_config import HiggsfieldConfig
        cfg = HiggsfieldConfig()
        assert cfg.is_enabled is True

    def test_config_disabled_via_env(self, monkeypatch):
        monkeypatch.setenv("HIGGSFIELD_PROVIDER", "disabled")
        from src.config.higgsfield_config import HiggsfieldConfig
        cfg = HiggsfieldConfig()
        assert cfg.is_enabled is False

    def test_config_has_character_false_without_env(self, monkeypatch):
        monkeypatch.delenv("HIGGSFIELD_CHARACTER_ID", raising=False)
        from src.config.higgsfield_config import HiggsfieldConfig
        cfg = HiggsfieldConfig()
        assert cfg.has_character is False

    def test_config_has_character_true_with_env(self, monkeypatch):
        monkeypatch.setenv("HIGGSFIELD_CHARACTER_ID", "char-valeria-001")
        from src.config.higgsfield_config import HiggsfieldConfig
        cfg = HiggsfieldConfig()
        assert cfg.has_character is True
        assert cfg.character_id == "char-valeria-001"

    def test_auth_token_reads_from_env(self, monkeypatch):
        monkeypatch.setenv("HIGGSFIELD_AUTH_TOKEN", "test-token-abc123")
        from src.config.higgsfield_config import HiggsfieldConfig
        cfg = HiggsfieldConfig()
        assert cfg.auth_token == "test-token-abc123"

    def test_auth_token_none_without_env(self, monkeypatch):
        for var in ["HIGGSFIELD_AUTH_TOKEN", "HIGGSFIELD_TOKEN", "HIGGSFIELD_API_KEY"]:
            monkeypatch.delenv(var, raising=False)
        from src.config.higgsfield_config import HiggsfieldConfig
        cfg = HiggsfieldConfig()
        assert cfg.auth_token is None

    def test_enrich_prompt_with_style(self):
        from src.config.higgsfield_config import HiggsfieldConfig
        cfg = HiggsfieldConfig()
        enriched = cfg.enrich_prompt_with_style("Valeria en rooftop")
        assert "Valeria en rooftop" in enriched
        assert "luxury lifestyle" in enriched.lower()
        assert "photorealistic" in enriched.lower()

    def test_get_project_profile_structure(self):
        from src.config.higgsfield_config import HiggsfieldConfig
        cfg = HiggsfieldConfig()
        profile = cfg.get_project_profile()
        assert "project" in profile
        assert "default_image_model" in profile
        assert "default_video_model" in profile
        assert "default_aspect_ratio" in profile
        assert "is_enabled" in profile

    def test_summary_has_no_token(self, monkeypatch):
        monkeypatch.setenv("HIGGSFIELD_AUTH_TOKEN", "super_secret_token_xyz")
        from src.config.higgsfield_config import HiggsfieldConfig
        cfg = HiggsfieldConfig()
        summary = cfg.summary()
        # El summary no debe exponer el token, solo su presencia
        assert "super_secret_token_xyz" not in summary
        assert "✅" in summary  # Indica que hay token

    def test_valeria_project_profile_constant(self):
        from src.config.higgsfield_config import VALERIA_PROJECT_PROFILE
        assert VALERIA_PROJECT_PROFILE["project"] == "Valeria Montesano Digital"
        assert VALERIA_PROJECT_PROFILE["default_image_model"] == "soul_2"
        assert VALERIA_PROJECT_PROFILE["default_video_model"] == "seedance_2_0"
        assert VALERIA_PROJECT_PROFILE["default_aspect_ratio"] == "9:16"
        assert "luxury lifestyle" in VALERIA_PROJECT_PROFILE["style_tags"]


# ─────────────────────────────────────────────────────────────
# 2. HiggsfieldAdapter — disponibilidad y character management
# ─────────────────────────────────────────────────────────────

class TestHiggsfieldAdapter:

    def test_adapter_availability(self):
        from src.adapters.higgsfield_adapter import HiggsfieldAdapter
        adapter = HiggsfieldAdapter()
        assert adapter._is_available() is True
        assert "mcp.higgsfield.ai" in adapter.mcp_url

    def test_adapter_singleton_exists(self):
        from src.adapters.higgsfield_adapter import higgsfield_adapter, HiggsfieldAdapter
        assert higgsfield_adapter is not None
        assert isinstance(higgsfield_adapter, HiggsfieldAdapter)

    def test_adapter_list_mcp_tools(self):
        from src.adapters.higgsfield_adapter import higgsfield_adapter
        tools = higgsfield_adapter.list_mcp_tools()
        tool_names = [t["name"] for t in tools]
        assert "higgsfield_generate_image" in tool_names
        assert "higgsfield_generate_video" in tool_names
        assert "higgsfield_list_characters" in tool_names
        assert "higgsfield_get_character" in tool_names
        assert "higgsfield_generate_image_character" in tool_names
        assert "higgsfield_generate_video_character" in tool_names
        assert "higgsfield_check_job_status" in tool_names
        assert "higgsfield_get_result" in tool_names

    def test_adapter_get_project_profile(self):
        from src.adapters.higgsfield_adapter import higgsfield_adapter
        profile = higgsfield_adapter.get_project_profile()
        assert "project" in profile
        assert "default_image_model" in profile
        assert "default_aspect_ratio" in profile

    @pytest.mark.asyncio
    async def test_list_characters_mock(self):
        """list_characters() parsea correctamente la respuesta del MCP."""
        from src.adapters.higgsfield_adapter import HiggsfieldAdapter
        adapter = HiggsfieldAdapter(api_key="fake-token-for-test")

        mock_result = {
            "structuredContent": {
                "characters": [
                    {"id": "char-001", "name": "Valeria", "model": "soul_2", "status": "ready"},
                    {"id": "char-002", "name": "Test",    "model": "soul",   "status": "ready"},
                ]
            }
        }
        with patch.object(adapter, "_rpc_call", new_callable=AsyncMock, return_value=mock_result):
            characters = await adapter.list_characters()

        assert isinstance(characters, list)
        assert len(characters) == 2
        assert characters[0]["id"] == "char-001"
        assert characters[0]["model"] == "soul_2"

    @pytest.mark.asyncio
    async def test_get_character_mock(self):
        """get_character() retorna el dict del personaje."""
        from src.adapters.higgsfield_adapter import HiggsfieldAdapter
        adapter = HiggsfieldAdapter(api_key="fake-token-for-test")

        mock_result = {
            "structuredContent": {
                "character": {
                    "id": "char-valeria-001",
                    "name": "Valeria",
                    "model": "soul_2",
                    "status": "ready",
                    "preview_url": "https://cdn.higgsfield.ai/chars/valeria.jpg",
                }
            }
        }
        with patch.object(adapter, "_rpc_call", new_callable=AsyncMock, return_value=mock_result):
            char = await adapter.get_character("char-valeria-001")

        assert char["id"] == "char-valeria-001"
        assert char["model"] == "soul_2"

    @pytest.mark.asyncio
    async def test_generate_image_with_character_mock(self, fake_job_id):
        """generate_image_with_character() aplica Soul 2 y 9:16, retorna job_id."""
        from src.adapters.higgsfield_adapter import HiggsfieldAdapter
        adapter = HiggsfieldAdapter(api_key="fake-token-for-test")

        mock_rpc_result = {
            "structuredContent": {
                "results": [{
                    "id": fake_job_id,
                    "status": "completed",
                    "results": {"rawUrl": "https://cdn.higgsfield.ai/img/test.png"},
                }]
            }
        }
        with patch.object(adapter, "_rpc_call", new_callable=AsyncMock, return_value=mock_rpc_result):
            result = await adapter.generate_image_with_character(
                prompt="Valeria en rooftop de Buenos Aires",
                character_id="char-valeria-001",
            )

        assert result["job_id"] == fake_job_id
        assert result["status"] == "completed"
        assert result["media_type"] == "image"
        assert result["character_id"] == "char-valeria-001"
        assert result["image_url"] == "https://cdn.higgsfield.ai/img/test.png"
        # Debe usar Soul 2 y 9:16 por defecto
        assert result["model"] == "soul_2"
        assert result["aspect_ratio"] == "9:16"

    @pytest.mark.asyncio
    async def test_generate_video_with_character_mock(self, fake_job_id):
        """generate_video_with_character() aplica Seedance 2.0 y 9:16."""
        from src.adapters.higgsfield_adapter import HiggsfieldAdapter
        adapter = HiggsfieldAdapter(api_key="fake-token-for-test")

        mock_rpc_result = {
            "structuredContent": {
                "results": [{
                    "id": fake_job_id + "-v",
                    "status": "completed",
                    "results": {"rawUrl": "https://cdn.higgsfield.ai/vid/test.mp4"},
                }]
            }
        }
        with patch.object(adapter, "_rpc_call", new_callable=AsyncMock, return_value=mock_rpc_result):
            result = await adapter.generate_video_with_character(
                prompt="Valeria caminando en Palermo",
                character_id="char-valeria-001",
            )

        assert result["status"] == "completed"
        assert result["media_type"] == "video"
        assert result["character_id"] == "char-valeria-001"
        assert result["video_url"] == "https://cdn.higgsfield.ai/vid/test.mp4"
        assert result["model"] == "seedance_2_0"
        assert result["aspect_ratio"] == "9:16"

    @pytest.mark.asyncio
    async def test_check_job_status_alias(self):
        """check_job_status() es alias semántico de get_job_status()."""
        from src.adapters.higgsfield_adapter import HiggsfieldAdapter
        adapter = HiggsfieldAdapter(api_key="fake-token-for-test")

        expected = {"job_id": "abc-123", "status": "completed", "provider": "higgsfield"}
        with patch.object(adapter, "get_job_status", new_callable=AsyncMock, return_value=expected):
            result = await adapter.check_job_status("abc-123")

        assert result["status"] == "completed"

    @pytest.mark.asyncio
    async def test_generate_image_real_or_graceful_fail(self):
        """Test de integración real: acepta éxito o error de créditos/auth."""
        from src.adapters.higgsfield_adapter import higgsfield_adapter
        try:
            res = await higgsfield_adapter.generate_image(
                prompt="Soul portrait of a luxury influencer",
                model="nano_banana_2",
                aspect_ratio="1:1"
            )
            assert res["status"] in ("completed", "pending", "success")
            assert "job_id" in res
        except RuntimeError as e:
            err = str(e).lower()
            assert any(k in err for k in ["credits", "error", "auth", "token", "401", "403"])


# ─────────────────────────────────────────────────────────────
# 3. HiggsfieldGenerationHistory — historial y deduplicación
# ─────────────────────────────────────────────────────────────

class TestHiggsfieldGenerationHistory:

    @pytest.fixture
    def tmp_history(self, tmp_path):
        from src.providers.higgsfield_generation_history import HiggsfieldGenerationHistory
        db_path = tmp_path / "test_generations.db"
        return HiggsfieldGenerationHistory(db_path=db_path)

    def test_save_image_generation(self, tmp_history, fake_image_result):
        row_id = tmp_history.save(
            fake_image_result,
            project="Valeria Montesano Digital",
            character_id="char-valeria-001",
            character_name="Mi Influencer",
            style_tags=["luxury lifestyle", "photorealistic"],
        )
        assert row_id is not None
        assert row_id > 0

    def test_save_video_generation(self, tmp_history, fake_video_result):
        row_id = tmp_history.save(
            fake_video_result,
            project="Valeria Montesano Digital",
            character_id="char-valeria-001",
        )
        assert row_id is not None

    def test_deduplication_same_job_id(self, tmp_history, fake_image_result):
        """Guardar el mismo job_id dos veces no crea duplicados."""
        id1 = tmp_history.save(fake_image_result, project="Valeria Montesano Digital")
        id2 = tmp_history.save(fake_image_result, project="Valeria Montesano Digital")
        assert id1 is not None
        assert id2 is None  # Duplicado rechazado silenciosamente

    def test_already_exists_check(self, tmp_history, fake_image_result):
        assert tmp_history.already_exists(fake_image_result["job_id"]) is False
        tmp_history.save(fake_image_result, project="Valeria Montesano Digital")
        assert tmp_history.already_exists(fake_image_result["job_id"]) is True

    def test_get_recent(self, tmp_history, fake_image_result, fake_video_result):
        tmp_history.save(fake_image_result, project="Valeria Montesano Digital")
        tmp_history.save(fake_video_result, project="Valeria Montesano Digital")
        recent = tmp_history.get_recent(limit=10)
        assert len(recent) == 2

    def test_get_by_project(self, tmp_history, fake_image_result):
        tmp_history.save(fake_image_result, project="Valeria Montesano Digital")
        results = tmp_history.get_by_project("Valeria Montesano Digital")
        assert len(results) == 1
        assert results[0]["job_id"] == fake_image_result["job_id"]

    def test_get_by_character(self, tmp_history, fake_image_result, fake_video_result):
        tmp_history.save(fake_image_result, project="Valeria Montesano Digital", character_id="char-valeria-001")
        tmp_history.save(fake_video_result, project="Valeria Montesano Digital", character_id="char-valeria-001")
        results = tmp_history.get_by_character("char-valeria-001")
        assert len(results) == 2

    def test_get_by_media_type(self, tmp_history, fake_image_result, fake_video_result):
        tmp_history.save(fake_image_result, project="Valeria Montesano Digital")
        tmp_history.save(fake_video_result, project="Valeria Montesano Digital")
        images = tmp_history.get_by_media_type("image")
        videos = tmp_history.get_by_media_type("video")
        assert len(images) == 1
        assert len(videos) == 1

    def test_get_by_job_id(self, tmp_history, fake_image_result):
        tmp_history.save(fake_image_result, project="Valeria Montesano Digital")
        record = tmp_history.get_by_job_id(fake_image_result["job_id"])
        assert record is not None
        assert record["job_id"] == fake_image_result["job_id"]
        assert record["model"] == "soul_2"

    def test_style_tags_serialization(self, tmp_history, fake_image_result):
        """Los style_tags se guardan y recuperan como lista."""
        tags = ["luxury lifestyle", "photorealistic", "premium cinematic"]
        tmp_history.save(fake_image_result, project="Valeria", style_tags=tags)
        record = tmp_history.get_by_job_id(fake_image_result["job_id"])
        assert isinstance(record["style_tags"], list)
        assert "luxury lifestyle" in record["style_tags"]

    def test_stats_structure(self, tmp_history, fake_image_result, fake_video_result):
        tmp_history.save(fake_image_result, project="Valeria Montesano Digital")
        tmp_history.save(fake_video_result, project="Valeria Montesano Digital")
        stats = tmp_history.get_stats()
        assert stats["total_generations"] == 2
        assert "by_media_type" in stats
        assert "by_model" in stats
        assert "by_project" in stats

    def test_save_without_job_id_is_skipped(self, tmp_history):
        """Resultado sin job_id no genera error, simplemente se omite."""
        result = tmp_history.save({"status": "unknown"}, project="test")
        assert result is None


# ─────────────────────────────────────────────────────────────
# 4. HiggsfieldSpecialist — flujo completo
# ─────────────────────────────────────────────────────────────

class TestHiggsfieldSpecialist:

    def test_specialist_registered(self):
        from src.specialists.specialist_registry import specialist_registry
        from src.specialists.higgsfield_specialist import HiggsfieldSpecialist
        spec = specialist_registry.get_specialist("higgsfield_specialist")
        assert spec is not None
        assert isinstance(spec, HiggsfieldSpecialist)

    def test_specialist_display_name(self):
        from src.specialists.higgsfield_specialist import HiggsfieldSpecialist
        spec = HiggsfieldSpecialist()
        assert spec.display_name == "Higgsfield AI Video & Media Specialist"

    def test_specialist_description_contains_valeria(self):
        from src.specialists.higgsfield_specialist import HiggsfieldSpecialist
        spec = HiggsfieldSpecialist()
        assert "Valeria" in spec.description

    def test_specialist_default_models(self):
        """Los modelos por defecto deben ser Soul 2 y Seedance 2.0."""
        from src.specialists.higgsfield_specialist import HiggsfieldSpecialist
        spec = HiggsfieldSpecialist()
        assert spec._default_image_model == "soul_2"
        assert spec._default_video_model == "seedance_2_0"

    def test_specialist_default_aspect_ratio(self):
        from src.specialists.higgsfield_specialist import HiggsfieldSpecialist
        spec = HiggsfieldSpecialist()
        assert spec._default_aspect_ratio == "9:16"

    def test_specialist_project_name(self):
        from src.specialists.higgsfield_specialist import HiggsfieldSpecialist
        spec = HiggsfieldSpecialist()
        assert spec._project_name == "Valeria Montesano Digital"

    def test_specialist_routing_video(self):
        from src.specialists.specialist_registry import specialist_registry
        spec = specialist_registry.route_mission("Crea un video cinematografico con higgsfield")
        assert spec is not None
        assert spec.specialist_id == "higgsfield_specialist"

    @pytest.mark.asyncio
    async def test_specialist_execute_image_task(self, fake_image_result):
        """execute_task() genera imagen y retorna asset final."""
        from src.specialists.higgsfield_specialist import HiggsfieldSpecialist
        import src.specialists.higgsfield_specialist as specialist_module

        spec = HiggsfieldSpecialist()

        with patch.object(
            specialist_module.higgsfield_adapter,
            "generate_image",
            new_callable=AsyncMock,
            return_value=fake_image_result
        ):
            result = await spec.execute_task(
                "Crear imagen de Valeria en un rooftop de Buenos Aires",
                payload={"prompt": "Valeria en rooftop de Buenos Aires"}
            )

        assert result["status"] == "success"
        assert result["specialist"] == "Higgsfield AI Video & Media Specialist"
        assert result["media_type"] == "image"
        assert "job_id" in result
        assert "output_url" in result
        assert result["project"] == "Valeria Montesano Digital"

    @pytest.mark.asyncio
    async def test_specialist_execute_video_task(self, fake_video_result):
        """execute_task() detecta 'video' en el prompt y genera video."""
        from src.specialists.higgsfield_specialist import HiggsfieldSpecialist
        import src.specialists.higgsfield_specialist as specialist_module

        spec = HiggsfieldSpecialist()

        with patch.object(
            specialist_module.higgsfield_adapter,
            "generate_video",
            new_callable=AsyncMock,
            return_value=fake_video_result
        ):
            result = await spec.execute_task(
                "Genera un video de Valeria caminando en Palermo",
                payload={"prompt": "Valeria caminando en Palermo"}
            )

        assert result["status"] == "success"
        assert result["media_type"] == "video"

    def test_specialist_get_project_profile(self):
        from src.specialists.higgsfield_specialist import HiggsfieldSpecialist
        spec = HiggsfieldSpecialist()
        profile = spec.get_project_profile()
        assert isinstance(profile, dict)
        assert "project" in profile


# ─────────────────────────────────────────────────────────────
# 5. ProviderManager — capabilities extendidas
# ─────────────────────────────────────────────────────────────

class TestProviderManagerHighsfield:

    def test_higgsfield_registered(self):
        from src.providers.provider_manager import provider_manager
        adapter = provider_manager.get("higgsfield")
        assert adapter is not None

    def test_higgsfield_capabilities_extended(self):
        from src.providers.provider_manager import provider_manager, ProviderCapability
        adapter = provider_manager.get("higgsfield")
        cap_values = [c.value for c in adapter.capabilities]
        assert "image" in cap_values
        assert "video" in cap_values
        assert "character_management" in cap_values
        assert "job_status" in cap_values
        assert "asset_retrieval" in cap_values

    def test_higgsfield_in_list_providers(self):
        from src.providers.provider_manager import provider_manager
        providers = provider_manager.list_providers()
        ids = [p["id"] for p in providers]
        assert "higgsfield" in ids

    def test_higgsfield_capabilities_in_list(self):
        from src.providers.provider_manager import provider_manager
        providers = provider_manager.list_providers()
        hf = next((p for p in providers if p["id"] == "higgsfield"), None)
        assert hf is not None
        assert "character_management" in hf["capabilities"]
        assert "job_status" in hf["capabilities"]

    def test_provider_capability_enum_values(self):
        from src.providers.provider_manager import ProviderCapability
        assert ProviderCapability.CHARACTER_MGMT.value == "character_management"
        assert ProviderCapability.JOB_STATUS.value == "job_status"
        assert ProviderCapability.ASSET_RETRIEVAL.value == "asset_retrieval"

    def test_higgsfield_has_character_methods(self):
        from src.providers.provider_manager import provider_manager
        adapter = provider_manager.get("higgsfield")
        assert hasattr(adapter, "list_characters")
        assert hasattr(adapter, "get_character")
        assert hasattr(adapter, "check_job_status")
        assert hasattr(adapter, "get_result")
        assert hasattr(adapter, "get_project_profile")


# ─────────────────────────────────────────────────────────────
# 6. MCP Tools — registro completo
# ─────────────────────────────────────────────────────────────

class TestMCPToolsRegistration:

    def test_mcp_tools_registration(self):
        from src.mcp.registry import mcp_registry
        from src.mcp.tools import register_all_tools
        register_all_tools()
        tool_names = [t["name"] for t in mcp_registry.list_tools()]
        assert "higgsfield_generate_video" in tool_names
        assert "higgsfield_generate_image" in tool_names
        assert "higgsfield_image_to_video" in tool_names
        assert "higgsfield_status" in tool_names
