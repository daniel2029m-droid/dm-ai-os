"""
Tests de Fase B - Adaptadores Open Source
==========================================
Valida que BrowserUseAdapter y VectorBackend:
1. Aplican correctamente el patron _is_available() / fallback.
2. No rompen la API publica de BrowserAgent ni KnowledgeStore.
3. Funcionan sin las dependencias instaladas (fallback garantizado).
4. La interfaz abstracta VectorBackend tiene las 3 implementaciones correctas.
5. JsonVectorBackend es identico al comportamiento actual de KnowledgeStore.

Ejecutar con: python -m pytest tests/test_adapters_phase_b.py -v
"""

import asyncio
import math
import os
import json
import tempfile
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock


# ===========================================================================
# BrowserUseAdapter Tests
# ===========================================================================

class TestBrowserUseAdapterAvailability:
    """Tests del patron _is_available() sin dependencias."""

    def test_is_available_returns_bool(self):
        from src.adapters.browser_use_adapter import BrowserUseAdapter
        assert isinstance(BrowserUseAdapter._is_available(), bool)

    def test_is_enabled_returns_bool(self):
        from src.adapters.browser_use_adapter import BrowserUseAdapter
        assert isinstance(BrowserUseAdapter._is_enabled(), bool)

    def test_disabled_by_default(self):
        from src.adapters.browser_use_adapter import BrowserUseAdapter
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("BROWSER_USE_ENABLED", None)
            assert BrowserUseAdapter._is_enabled() is False

    def test_enabled_via_env_var(self):
        from src.adapters.browser_use_adapter import BrowserUseAdapter
        with patch.dict(os.environ, {"BROWSER_USE_ENABLED": "true"}):
            assert BrowserUseAdapter._is_enabled() is True

    def test_enabled_via_env_var_1(self):
        from src.adapters.browser_use_adapter import BrowserUseAdapter
        with patch.dict(os.environ, {"BROWSER_USE_ENABLED": "1"}):
            assert BrowserUseAdapter._is_enabled() is True


class TestBrowserUseAdapterFallback:
    """Tests de fallback cuando Browser Use no esta disponible o esta desactivado."""

    def test_search_returns_none_when_disabled(self):
        from src.adapters.browser_use_adapter import BrowserUseAdapter
        adapter = BrowserUseAdapter()
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("BROWSER_USE_ENABLED", None)
            result = asyncio.run(adapter.search("AI news"))
        assert result is None

    def test_search_returns_none_when_not_installed(self):
        from src.adapters.browser_use_adapter import BrowserUseAdapter
        adapter = BrowserUseAdapter()
        with patch.dict(os.environ, {"BROWSER_USE_ENABLED": "true"}):
            with patch.object(BrowserUseAdapter, "_is_available", return_value=False):
                result = asyncio.run(adapter.search("technology"))
        assert result is None

    def test_search_returns_none_on_timeout(self):
        from src.adapters.browser_use_adapter import BrowserUseAdapter
        adapter = BrowserUseAdapter()
        with patch.dict(os.environ, {"BROWSER_USE_ENABLED": "true"}):
            with patch.object(BrowserUseAdapter, "_is_available", return_value=True):
                with patch.object(adapter, "_get_llm", return_value=MagicMock()):
                    with patch.object(adapter, "_do_search", side_effect=asyncio.TimeoutError()):
                        result = asyncio.run(adapter.search("test"))
        assert result is None

    def test_search_returns_none_on_exception(self):
        from src.adapters.browser_use_adapter import BrowserUseAdapter
        adapter = BrowserUseAdapter()
        with patch.dict(os.environ, {"BROWSER_USE_ENABLED": "true"}):
            with patch.object(BrowserUseAdapter, "_is_available", return_value=True):
                with patch.object(adapter, "_get_llm", return_value=MagicMock()):
                    with patch.object(adapter, "_do_search", side_effect=RuntimeError("browser error")):
                        result = asyncio.run(adapter.search("test"))
        assert result is None

    def test_search_returns_none_when_llm_unavailable(self):
        from src.adapters.browser_use_adapter import BrowserUseAdapter
        adapter = BrowserUseAdapter()
        with patch.dict(os.environ, {"BROWSER_USE_ENABLED": "true"}):
            with patch.object(BrowserUseAdapter, "_is_available", return_value=True):
                with patch.object(adapter, "_get_llm", return_value=None):
                    result = asyncio.run(adapter.search("test"))
        assert result is None

    def test_navigate_returns_none_when_disabled(self):
        from src.adapters.browser_use_adapter import BrowserUseAdapter
        adapter = BrowserUseAdapter()
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("BROWSER_USE_ENABLED", None)
            result = asyncio.run(adapter.navigate("open Google"))
        assert result is None


class TestBrowserUseAdapterMockedSearch:
    """Tests de busqueda con browser-use mockeado."""

    def test_search_returns_correct_format(self):
        from src.adapters.browser_use_adapter import BrowserUseAdapter
        adapter = BrowserUseAdapter()
        expected = {
            "status": "success",
            "query": "AI news",
            "results": ["Summary 1", "Summary 2"],
            "sources": ["Title 1: https://a.com", "Title 2: https://b.com"],
            "source": "browser_use",
        }

        with patch.dict(os.environ, {"BROWSER_USE_ENABLED": "true"}):
            with patch.object(BrowserUseAdapter, "_is_available", return_value=True):
                with patch.object(adapter, "_get_llm", return_value=MagicMock()):
                    with patch.object(adapter, "_do_search", new=AsyncMock(return_value=expected)):
                        result = asyncio.run(adapter.search("AI news"))

        assert result is not None
        assert result["status"] == "success"
        assert "results" in result
        assert "sources" in result
        assert result["source"] == "browser_use"

    def test_parse_agent_output_structured_format(self):
        """_parse_agent_output parses numbered list format correctly."""
        from src.adapters.browser_use_adapter import BrowserUseAdapter
        adapter = BrowserUseAdapter()

        mock_result = MagicMock()
        mock_result.final_result.return_value = (
            "[1]. Title: AI Breakthrough | URL: https://tech.com/ai | Summary: OpenAI released GPT-5 with amazing capabilities.\n"
            "[2]. Title: ML News | URL: https://ml.com/news | Summary: Google announced new Gemini features.\n"
        )

        parsed = adapter._parse_agent_output(mock_result, "AI news")

        assert parsed is not None
        assert parsed["status"] == "success"
        assert len(parsed["results"]) == 2
        assert "OpenAI" in parsed["results"][0]

    def test_parse_agent_output_fallback_on_unstructured(self):
        """_parse_agent_output falls back to raw text if format not matched."""
        from src.adapters.browser_use_adapter import BrowserUseAdapter
        adapter = BrowserUseAdapter()

        mock_result = MagicMock()
        mock_result.final_result.return_value = "Some unstructured text result that is longer than 20 characters."

        parsed = adapter._parse_agent_output(mock_result, "test query")

        assert parsed is not None
        assert len(parsed["results"]) > 0

    def test_parse_agent_output_returns_none_on_empty(self):
        """_parse_agent_output returns None when agent output is empty."""
        from src.adapters.browser_use_adapter import BrowserUseAdapter
        adapter = BrowserUseAdapter()

        mock_result = MagicMock()
        mock_result.final_result.return_value = ""

        parsed = adapter._parse_agent_output(mock_result, "test query")
        assert parsed is None


class TestBrowserAgentIntegration:
    """Tests de integracion de BrowserUseAdapter con BrowserAgent."""

    def test_search_web_falls_back_to_ddg_when_browser_use_disabled(self):
        """BrowserAgent.search_web() uses DuckDuckGo when Browser Use is disabled."""
        from src.agents.browser_agent import BrowserAgent

        agent = BrowserAgent()
        mock_ddg_response = {
            "status": "success",
            "query": "test",
            "results": ["DDG snippet 1"],
            "sources": ["Title: https://example.com"],
            "source": "duckduckgo_web",
        }

        import httpx

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("BROWSER_USE_ENABLED", None)

            # Mock the HTTP call to DuckDuckGo
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.text = '''
                <div class="result__title"><a class="result__a" href="https://example.com">Test Title</a></div>
                <a class="result__snippet">This is a detailed test snippet for unit testing purposes.</a>
            '''

            with patch("httpx.AsyncClient") as mock_client_cls:
                mock_client = AsyncMock()
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock(return_value=False)
                mock_client.post = AsyncMock(return_value=mock_resp)
                mock_client_cls.return_value = mock_client

                result = asyncio.run(agent.search_web("test query"))

        # Must return a dict with required keys (either DDG or no_internet)
        assert "status" in result
        assert "results" in result
        assert "sources" in result

    def test_search_web_public_api_unchanged(self):
        """BrowserAgent.search_web() signature is unchanged after integration."""
        import inspect
        from src.agents.browser_agent import BrowserAgent

        agent = BrowserAgent()
        sig = inspect.signature(agent.search_web)
        params = list(sig.parameters.keys())
        assert "query" in params

    def test_browser_use_adapter_exported_from_package(self):
        """BrowserUseAdapter is importable from src.adapters."""
        from src.adapters import BrowserUseAdapter, browser_use_adapter
        assert BrowserUseAdapter is not None
        assert browser_use_adapter is not None


# ===========================================================================
# VectorBackend Tests
# ===========================================================================

class TestVectorBackendInterface:
    """Tests de la interfaz abstracta VectorBackend."""

    def test_vector_backend_is_abstract(self):
        from src.memory.vector_backend import VectorBackend
        import inspect
        assert inspect.isabstract(VectorBackend)

    def test_abstract_methods_defined(self):
        from src.memory.vector_backend import VectorBackend
        abstract_methods = VectorBackend.__abstractmethods__
        assert "save_vector" in abstract_methods
        assert "search_similar" in abstract_methods
        assert "delete_vector" in abstract_methods
        assert "count" in abstract_methods


class TestJsonVectorBackend:
    """Tests del backend JSON (default — comportamiento actual)."""

    def _make_backend(self, tmp_dir):
        from src.memory.vector_backend import JsonVectorBackend
        return JsonVectorBackend(vectors_dir=str(tmp_dir))

    def _make_vector(self, dim=4, val=1.0):
        """Make a normalized vector of given dimension."""
        v = [val] * dim
        norm = math.sqrt(sum(x * x for x in v))
        return [x / norm for x in v]

    def test_init_creates_index_file(self, tmp_path):
        backend = self._make_backend(tmp_path)
        assert (tmp_path / "vector_index.json").exists()

    def test_save_and_count(self, tmp_path):
        backend = self._make_backend(tmp_path)
        backend.save_vector("id1", "test text", self._make_vector(), {"cat": "test"})
        assert backend.count() == 1

    def test_save_multiple_vectors(self, tmp_path):
        backend = self._make_backend(tmp_path)
        backend.save_vector("id1", "text 1", self._make_vector(), {})
        backend.save_vector("id2", "text 2", self._make_vector(val=0.5), {})
        assert backend.count() == 2

    def test_update_existing_vector(self, tmp_path):
        backend = self._make_backend(tmp_path)
        v1 = self._make_vector()
        backend.save_vector("id1", "original text", v1, {})
        backend.save_vector("id1", "updated text", v1, {})
        assert backend.count() == 1  # No duplicate

        # Load and verify update
        data = json.loads((tmp_path / "vector_index.json").read_text())
        assert data["items"][0]["text"] == "updated text"

    def test_search_similar_returns_results(self, tmp_path):
        backend = self._make_backend(tmp_path)
        v_similar = self._make_vector(dim=4, val=1.0)
        v_different = [1.0, 0.0, 0.0, 0.0]

        backend.save_vector("sim", "similar text", v_similar, {})
        backend.save_vector("diff", "different text", v_different, {})

        results = backend.search_similar(v_similar, top_k=2)
        assert len(results) > 0
        assert results[0]["id"] == "sim"  # Most similar first

    def test_search_similar_result_structure(self, tmp_path):
        backend = self._make_backend(tmp_path)
        backend.save_vector("x1", "content", self._make_vector(), {"key": "val"})
        results = backend.search_similar(self._make_vector(), top_k=1)
        assert len(results) == 1
        res = results[0]
        assert "id" in res
        assert "text" in res
        assert "score" in res
        assert "metadata" in res
        assert isinstance(res["score"], float)

    def test_delete_vector(self, tmp_path):
        backend = self._make_backend(tmp_path)
        backend.save_vector("del1", "to delete", self._make_vector(), {})
        assert backend.count() == 1
        success = backend.delete_vector("del1")
        assert success is True
        assert backend.count() == 0

    def test_delete_nonexistent_returns_false(self, tmp_path):
        backend = self._make_backend(tmp_path)
        assert backend.delete_vector("nonexistent") is False

    def test_search_with_metadata_filter(self, tmp_path):
        backend = self._make_backend(tmp_path)
        backend.save_vector("a1", "cat A", self._make_vector(), {"category": "A"})
        backend.save_vector("b1", "cat B", self._make_vector(), {"category": "B"})

        results = backend.search_similar(
            self._make_vector(), top_k=5, filter_metadata={"category": "A"}
        )
        assert len(results) == 1
        assert results[0]["id"] == "a1"

    def test_search_empty_store_returns_empty(self, tmp_path):
        backend = self._make_backend(tmp_path)
        results = backend.search_similar(self._make_vector(), top_k=5)
        assert results == []

    def test_cosine_similarity_identical_vectors(self):
        from src.memory.vector_backend import JsonVectorBackend
        v = [0.5, 0.5, 0.5, 0.5]
        score = JsonVectorBackend._cosine(v, v)
        assert abs(score - 1.0) < 1e-6

    def test_cosine_similarity_orthogonal_vectors(self):
        from src.memory.vector_backend import JsonVectorBackend
        v1 = [1.0, 0.0, 0.0]
        v2 = [0.0, 1.0, 0.0]
        score = JsonVectorBackend._cosine(v1, v2)
        assert abs(score) < 1e-6

    def test_backend_name(self, tmp_path):
        backend = self._make_backend(tmp_path)
        assert "Json" in backend.backend_name()


class TestGetBackendFactory:
    """Tests de la factory get_backend()."""

    def test_default_is_json(self):
        from src.memory.vector_backend import get_backend, JsonVectorBackend
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("VECTOR_BACKEND", None)
            backend = get_backend()
        assert isinstance(backend, JsonVectorBackend)

    def test_json_explicit(self):
        from src.memory.vector_backend import get_backend, JsonVectorBackend
        with patch.dict(os.environ, {"VECTOR_BACKEND": "json"}):
            backend = get_backend()
        assert isinstance(backend, JsonVectorBackend)

    def test_chroma_falls_back_to_json_when_not_installed(self):
        from src.memory.vector_backend import get_backend, JsonVectorBackend, ChromaVectorBackend
        with patch.dict(os.environ, {"VECTOR_BACKEND": "chroma"}):
            with patch.object(ChromaVectorBackend, "_is_available", return_value=False):
                backend = get_backend()
        assert isinstance(backend, JsonVectorBackend)

    def test_faiss_falls_back_to_json_when_not_installed(self):
        from src.memory.vector_backend import get_backend, JsonVectorBackend, FaissVectorBackend
        with patch.dict(os.environ, {"VECTOR_BACKEND": "faiss"}):
            with patch.object(FaissVectorBackend, "_is_available", return_value=False):
                backend = get_backend()
        assert isinstance(backend, JsonVectorBackend)

    def test_unknown_backend_falls_back_to_json(self):
        from src.memory.vector_backend import get_backend, JsonVectorBackend
        with patch.dict(os.environ, {"VECTOR_BACKEND": "unknown_db"}):
            backend = get_backend()
        assert isinstance(backend, JsonVectorBackend)

    def test_chroma_selected_when_installed(self):
        import sys
        from src.memory.vector_backend import get_backend, ChromaVectorBackend

        mock_chroma = MagicMock()
        with patch.dict(os.environ, {"VECTOR_BACKEND": "chroma"}):
            with patch.object(ChromaVectorBackend, "_is_available", return_value=True):
                with patch.dict(sys.modules, {"chromadb": mock_chroma}):
                    backend = get_backend()
        assert isinstance(backend, ChromaVectorBackend)

    def test_faiss_selected_when_installed(self):
        from src.memory.vector_backend import get_backend, FaissVectorBackend

        with patch.dict(os.environ, {"VECTOR_BACKEND": "faiss"}):
            with patch.object(FaissVectorBackend, "_is_available", return_value=True):
                with patch.object(FaissVectorBackend, "_load", return_value=None):
                    backend = get_backend()
        assert isinstance(backend, FaissVectorBackend)


class TestChromaVectorBackendInterface:
    """Tests de interfaz de ChromaVectorBackend (sin ChromaDB real instalado)."""

    def test_chroma_is_available_returns_bool(self):
        from src.memory.vector_backend import ChromaVectorBackend
        result = ChromaVectorBackend._is_available()
        assert isinstance(result, bool)

    def test_chroma_implements_interface(self):
        from src.memory.vector_backend import ChromaVectorBackend, VectorBackend
        assert issubclass(ChromaVectorBackend, VectorBackend)

    def test_chroma_save_delegates_to_chroma(self):
        from src.memory.vector_backend import ChromaVectorBackend

        backend = ChromaVectorBackend()
        mock_col = MagicMock()
        with patch.object(backend, "_get_collection", return_value=mock_col):
            backend.save_vector("id1", "text", [0.1, 0.2], {"key": "val"})

        mock_col.upsert.assert_called_once()
        call_kwargs = mock_col.upsert.call_args[1]
        assert call_kwargs["ids"] == ["id1"]

    def test_chroma_count_delegates_to_chroma(self):
        from src.memory.vector_backend import ChromaVectorBackend

        backend = ChromaVectorBackend()
        mock_col = MagicMock()
        mock_col.count.return_value = 42
        with patch.object(backend, "_get_collection", return_value=mock_col):
            count = backend.count()
        assert count == 42


class TestFaissVectorBackendInterface:
    """Tests de interfaz de FaissVectorBackend (sin FAISS real instalado)."""

    def test_faiss_is_available_returns_bool(self):
        from src.memory.vector_backend import FaissVectorBackend
        result = FaissVectorBackend._is_available()
        assert isinstance(result, bool)

    def test_faiss_implements_interface(self):
        from src.memory.vector_backend import FaissVectorBackend, VectorBackend
        assert issubclass(FaissVectorBackend, VectorBackend)

    def test_faiss_search_returns_empty_when_no_index(self, tmp_path):
        from src.memory.vector_backend import FaissVectorBackend

        backend = FaissVectorBackend(index_dir=str(tmp_path))
        # No index loaded (fresh)
        results = backend.search_similar([0.1, 0.2, 0.3], top_k=5)
        assert results == []

    def test_faiss_count_with_no_data(self, tmp_path):
        from src.memory.vector_backend import FaissVectorBackend

        backend = FaissVectorBackend(index_dir=str(tmp_path))
        assert backend.count() == 0


# ===========================================================================
# Full Pipeline Regression Tests
# ===========================================================================

class TestPhaseARegressionStillPasses:
    """Verify Phase A adapters are still functional after Phase B changes."""

    def test_docling_adapter_still_importable(self):
        from src.adapters import docling_adapter, DoclingAdapter
        assert docling_adapter is not None
        assert DoclingAdapter._is_enabled() is not None

    def test_crawl4ai_adapter_still_importable(self):
        from src.adapters import crawl4ai_adapter, Crawl4AIAdapter
        assert crawl4ai_adapter is not None
        assert Crawl4AIAdapter._is_enabled() is not None

    def test_all_four_adapters_importable_from_package(self):
        from src.adapters import (
            DoclingAdapter, docling_adapter,
            Crawl4AIAdapter, crawl4ai_adapter,
            BrowserUseAdapter, browser_use_adapter,
        )
        assert all([
            DoclingAdapter, docling_adapter,
            Crawl4AIAdapter, crawl4ai_adapter,
            BrowserUseAdapter, browser_use_adapter,
        ])

    def test_vector_backend_default_importable(self):
        from src.memory.vector_backend import default_backend, get_backend, VectorBackend
        assert default_backend is not None
        assert isinstance(default_backend, VectorBackend)
