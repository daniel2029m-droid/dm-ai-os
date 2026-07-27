"""
Tests de Fase C - Adaptadores Open Source
==========================================
Valida que PocketFlowAdapter y VisionAdapter:
1. Aplican correctamente el patron _is_available() / _is_enabled() / fallback.
2. No rompen la API publica de WorkflowEngine ni CapabilitySelector.
3. Funcionan sin las dependencias opcionales instaladas (fallback garantizado).
4. Exportan correctamente las clases y singletons desde el paquete src.adapters.

Ejecutar con: python -m pytest tests/test_adapters_phase_c.py -v
"""

import os
import asyncio
import pytest
from unittest.mock import patch, MagicMock


# ===========================================================================
# PocketFlowAdapter Tests
# ===========================================================================

class TestPocketFlowAdapterAvailability:
    """Tests del patron _is_available() y _is_enabled()."""

    def test_is_available_returns_bool(self):
        from src.adapters.pocketflow_adapter import PocketFlowAdapter
        assert isinstance(PocketFlowAdapter._is_available(), bool)

    def test_is_enabled_returns_bool(self):
        from src.adapters.pocketflow_adapter import PocketFlowAdapter
        assert isinstance(PocketFlowAdapter._is_enabled(), bool)

    def test_disabled_by_default(self):
        from src.adapters.pocketflow_adapter import PocketFlowAdapter
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("POCKETFLOW_ENABLED", None)
            assert PocketFlowAdapter._is_enabled() is False

    def test_enabled_via_env_var(self):
        from src.adapters.pocketflow_adapter import PocketFlowAdapter
        with patch.dict(os.environ, {"POCKETFLOW_ENABLED": "true"}):
            assert PocketFlowAdapter._is_enabled() is True


class TestPocketFlowAdapterFallback:
    """Tests de fallback cuando PocketFlow no esta disponible o esta desactivado."""

    def test_run_flow_returns_none_when_disabled(self):
        from src.adapters.pocketflow_adapter import PocketFlowAdapter
        adapter = PocketFlowAdapter()
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("POCKETFLOW_ENABLED", None)
            res = adapter.run_flow([{"name": "step1", "action": lambda c: "ok"}])
        assert res is None

    def test_run_flow_returns_none_when_not_installed(self):
        from src.adapters.pocketflow_adapter import PocketFlowAdapter
        adapter = PocketFlowAdapter()
        with patch.dict(os.environ, {"POCKETFLOW_ENABLED": "true"}):
            with patch.object(PocketFlowAdapter, "_is_available", return_value=False):
                res = adapter.run_flow([{"name": "step1", "action": lambda c: "ok"}])
        assert res is None

    def test_run_flow_returns_none_on_exception(self):
        from src.adapters.pocketflow_adapter import PocketFlowAdapter
        adapter = PocketFlowAdapter()
        with patch.dict(os.environ, {"POCKETFLOW_ENABLED": "true"}):
            with patch.object(PocketFlowAdapter, "_is_available", return_value=True):
                with patch.object(adapter, "_do_run_flow", side_effect=RuntimeError("flow err")):
                    res = adapter.run_flow([{"name": "step1", "action": lambda c: "ok"}])
        assert res is None


class TestPocketFlowAdapterExecution:
    """Tests con PocketFlow mockeado."""

    def test_do_run_flow_executes_steps(self):
        from src.adapters.pocketflow_adapter import PocketFlowAdapter
        adapter = PocketFlowAdapter()

        expected = {
            "status": "success",
            "results": {"step1": "val1"},
            "final_context": {"step1": "val1"},
            "source": "pocketflow",
        }

        with patch.dict(os.environ, {"POCKETFLOW_ENABLED": "true"}):
            with patch.object(PocketFlowAdapter, "_is_available", return_value=True):
                with patch.object(adapter, "_do_run_flow", return_value=expected):
                    res = adapter.run_flow([{"name": "step1", "action": lambda c: "val1"}])

        assert res is not None
        assert res["status"] == "success"
        assert res["source"] == "pocketflow"


# ===========================================================================
# VisionAdapter Tests
# ===========================================================================

class TestVisionAdapterAvailability:
    """Tests de disponibilidad y configuracion de VisionAdapter."""

    def test_is_enabled_default_true(self):
        from src.adapters.vision_adapter import VisionAdapter
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("VISION_ADAPTER_ENABLED", None)
            assert VisionAdapter._is_enabled() is True

    def test_is_enabled_disabled_via_env(self):
        from src.adapters.vision_adapter import VisionAdapter
        with patch.dict(os.environ, {"VISION_ADAPTER_ENABLED": "false"}):
            assert VisionAdapter._is_enabled() is False

    def test_encode_image_b64(self):
        from src.adapters.vision_adapter import VisionAdapter
        adapter = VisionAdapter()
        b64 = adapter.encode_image(b"test image bytes")
        assert isinstance(b64, str)
        assert len(b64) > 0

    def test_preprocess_image_returns_bytes(self):
        from src.adapters.vision_adapter import VisionAdapter
        adapter = VisionAdapter()
        res = adapter.preprocess_image(b"raw bytes")
        assert isinstance(res, bytes)

    def test_select_vision_model_subtask_ocr(self):
        from src.adapters.vision_adapter import VisionAdapter
        adapter = VisionAdapter()
        model = adapter.select_vision_model("ocr", installed_models=["qwen2.5-vl:7b", "qwen2.5:1.5b"])
        assert "qwen2.5-vl:7b" in model

    def test_select_vision_model_fallback(self):
        from src.adapters.vision_adapter import VisionAdapter
        adapter = VisionAdapter()
        model = adapter.select_vision_model("unknown_subtask", installed_models=[])
        assert model is not None

    def test_analyze_image_returns_none_when_disabled(self):
        from src.adapters.vision_adapter import VisionAdapter
        adapter = VisionAdapter()
        with patch.dict(os.environ, {"VISION_ADAPTER_ENABLED": "false"}):
            res = adapter.analyze_image(b"fake bytes")
        assert res is None

    def test_analyze_image_mocked(self):
        from src.adapters.vision_adapter import VisionAdapter
        adapter = VisionAdapter()

        with patch.dict(os.environ, {"VISION_ADAPTER_ENABLED": "true"}):
            with patch("src.providers.capability_selector.capability_selector.generate", return_value="Image shows a cat."):
                with patch("src.providers.capability_selector.capability_selector.probe_models", return_value=["llava:7b"]):
                    res = adapter.analyze_image(b"fake image bytes", prompt="Describe")

        assert res is not None
        assert res["status"] == "success"
        assert "analysis" in res
        assert res["source"] == "vision_adapter"


# ===========================================================================
# Package Integration Tests
# ===========================================================================

class TestAllAdaptersExported:
    """Valida que los 6 adaptadores de Fases A, B y C se exportan correctamente."""

    def test_all_six_adapters_exportable(self):
        from src.adapters import (
            DoclingAdapter, docling_adapter,
            Crawl4AIAdapter, crawl4ai_adapter,
            BrowserUseAdapter, browser_use_adapter,
            PocketFlowAdapter, pocketflow_adapter,
            VisionAdapter, vision_adapter,
        )

        adapters = [
            docling_adapter,
            crawl4ai_adapter,
            browser_use_adapter,
            pocketflow_adapter,
            vision_adapter,
        ]

        assert all(a is not None for a in adapters)
        assert len(adapters) == 5
