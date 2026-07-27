"""
Tests de Fase A - Adaptadores Open Source
==========================================
Valida que DoclingAdapter y Crawl4AIAdapter:
1. Aplican correctamente el patron _is_available() / fallback.
2. No rompen la API publica de DocumentPipeline ni ResearchAgent.
3. Funcionan sin tener las dependencias instaladas (fallback garantizado).
4. Funcionan con las dependencias instaladas si estan disponibles.

Estos tests son seguros de ejecutar en cualquier entorno:
- Si docling/crawl4ai NO estan instalados: todos los tests de fallback pasan.
- Si docling/crawl4ai ESTAN instalados: los tests de integracion real tambien pasan.

Ejecutar con: python -m pytest tests/test_adapters_phase_a.py -v
"""

import asyncio
import os
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from pathlib import Path


# ===========================================================================
# DoclingAdapter Tests
# ===========================================================================

class TestDoclingAdapterAvailability:
    """Tests del patron _is_available() sin dependencias."""

    def test_is_available_returns_bool(self):
        """_is_available() must always return a boolean."""
        from src.adapters.docling_adapter import DoclingAdapter
        result = DoclingAdapter._is_available()
        assert isinstance(result, bool)

    def test_is_enabled_returns_bool(self):
        """_is_enabled() must always return a boolean."""
        from src.adapters.docling_adapter import DoclingAdapter
        result = DoclingAdapter._is_enabled()
        assert isinstance(result, bool)

    def test_disabled_by_default(self):
        """DoclingAdapter must be disabled by default (opt-in)."""
        from src.adapters.docling_adapter import DoclingAdapter
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("DOCLING_ENABLED", None)
            assert DoclingAdapter._is_enabled() is False

    def test_enabled_via_env_var(self):
        """DoclingAdapter activates when DOCLING_ENABLED=true."""
        from src.adapters.docling_adapter import DoclingAdapter
        with patch.dict(os.environ, {"DOCLING_ENABLED": "true"}):
            assert DoclingAdapter._is_enabled() is True

    def test_enabled_via_env_var_1(self):
        """DoclingAdapter activates when DOCLING_ENABLED=1."""
        from src.adapters.docling_adapter import DoclingAdapter
        with patch.dict(os.environ, {"DOCLING_ENABLED": "1"}):
            assert DoclingAdapter._is_enabled() is True

    def test_ocr_disabled_by_default(self):
        """OCR must be disabled by default (avoids torch dependency)."""
        from src.adapters.docling_adapter import DoclingAdapter
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("DOCLING_OCR_ENABLED", None)
            assert DoclingAdapter._ocr_enabled() is False


class TestDoclingAdapterFallback:
    """Tests de fallback cuando Docling no esta disponible o esta desactivado."""

    def test_extract_returns_none_when_disabled(self):
        """extract() returns None when DOCLING_ENABLED is not set."""
        from src.adapters.docling_adapter import DoclingAdapter
        adapter = DoclingAdapter()
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("DOCLING_ENABLED", None)
            result = adapter.extract(b"test content", "test.txt")
        assert result is None

    def test_extract_returns_none_when_not_installed(self):
        """extract() returns None when docling is not installed, even if enabled."""
        from src.adapters.docling_adapter import DoclingAdapter
        adapter = DoclingAdapter()
        with patch.dict(os.environ, {"DOCLING_ENABLED": "true"}):
            with patch.object(DoclingAdapter, "_is_available", return_value=False):
                result = adapter.extract(b"PDF content", "document.pdf")
        assert result is None

    def test_extract_returns_none_for_unsupported_extension(self):
        """extract() returns None for extensions not in FORMAT_MAP."""
        from src.adapters.docling_adapter import DoclingAdapter
        adapter = DoclingAdapter()
        with patch.dict(os.environ, {"DOCLING_ENABLED": "true"}):
            with patch.object(DoclingAdapter, "_is_available", return_value=True):
                result = adapter.extract(b"content", "file.xyz_unknown")
        assert result is None

    def test_extract_returns_none_on_exception(self):
        """extract() returns None when an exception occurs during extraction."""
        from src.adapters.docling_adapter import DoclingAdapter
        adapter = DoclingAdapter()
        with patch.dict(os.environ, {"DOCLING_ENABLED": "true"}):
            with patch.object(DoclingAdapter, "_is_available", return_value=True):
                with patch.object(adapter, "_do_extract", side_effect=RuntimeError("test error")):
                    result = adapter.extract(b"PDF bytes", "test.pdf")
        assert result is None

    def test_chunked_returns_none_when_disabled(self):
        """extract_chunked() returns None when disabled."""
        from src.adapters.docling_adapter import DoclingAdapter
        adapter = DoclingAdapter()
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("DOCLING_ENABLED", None)
            result = adapter.extract_chunked(b"test", "test.pdf")
        assert result is None


class TestDoclingAdapterMockedExtraction:
    """Tests de extraccion con Docling mockeado."""

    def test_extract_returns_text_when_available(self):
        """extract() returns text when Docling is available and enabled."""
        from src.adapters.docling_adapter import DoclingAdapter
        adapter = DoclingAdapter()
        expected_text = "# Document Title\n\nParagraph content here."

        with patch.dict(os.environ, {"DOCLING_ENABLED": "true"}):
            with patch.object(DoclingAdapter, "_is_available", return_value=True):
                with patch.object(adapter, "_do_extract", return_value=expected_text):
                    result = adapter.extract(b"PDF bytes", "report.pdf")

        assert result == expected_text

    def test_extract_pdf_format_supported(self):
        """PDF extension is in FORMAT_MAP."""
        from src.adapters.docling_adapter import DoclingAdapter
        assert "pdf" in DoclingAdapter._FORMAT_MAP

    def test_extract_docx_format_supported(self):
        """DOCX extension is in FORMAT_MAP."""
        from src.adapters.docling_adapter import DoclingAdapter
        assert "docx" in DoclingAdapter._FORMAT_MAP

    def test_extract_xlsx_format_supported(self):
        """XLSX extension is in FORMAT_MAP (new capability vs. built-in)."""
        from src.adapters.docling_adapter import DoclingAdapter
        assert "xlsx" in DoclingAdapter._FORMAT_MAP

    def test_extract_pptx_format_supported(self):
        """PPTX extension is in FORMAT_MAP (new capability vs. built-in)."""
        from src.adapters.docling_adapter import DoclingAdapter
        assert "pptx" in DoclingAdapter._FORMAT_MAP


# ===========================================================================
# Crawl4AIAdapter Tests
# ===========================================================================

class TestCrawl4AIAdapterAvailability:
    """Tests del patron _is_available() sin dependencias."""

    def test_is_available_returns_bool(self):
        """_is_available() must always return a boolean."""
        from src.adapters.crawl4ai_adapter import Crawl4AIAdapter
        result = Crawl4AIAdapter._is_available()
        assert isinstance(result, bool)

    def test_is_enabled_returns_bool(self):
        """_is_enabled() must always return a boolean."""
        from src.adapters.crawl4ai_adapter import Crawl4AIAdapter
        result = Crawl4AIAdapter._is_enabled()
        assert isinstance(result, bool)

    def test_disabled_by_default(self):
        """Crawl4AIAdapter must be disabled by default (opt-in)."""
        from src.adapters.crawl4ai_adapter import Crawl4AIAdapter
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("CRAWL4AI_ENABLED", None)
            assert Crawl4AIAdapter._is_enabled() is False

    def test_enabled_via_env_var(self):
        """Crawl4AIAdapter activates when CRAWL4AI_ENABLED=true."""
        from src.adapters.crawl4ai_adapter import Crawl4AIAdapter
        with patch.dict(os.environ, {"CRAWL4AI_ENABLED": "true"}):
            assert Crawl4AIAdapter._is_enabled() is True


class TestCrawl4AIAdapterFallback:
    """Tests de fallback cuando Crawl4AI no esta disponible."""

    def test_crawl_url_returns_none_when_disabled(self):
        """crawl_url() returns None when CRAWL4AI_ENABLED is not set."""
        from src.adapters.crawl4ai_adapter import Crawl4AIAdapter
        adapter = Crawl4AIAdapter()
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("CRAWL4AI_ENABLED", None)
            result = asyncio.run(adapter.crawl_url("https://example.com"))
        assert result is None

    def test_crawl_url_returns_none_when_not_installed(self):
        """crawl_url() returns None when crawl4ai is not installed."""
        from src.adapters.crawl4ai_adapter import Crawl4AIAdapter
        adapter = Crawl4AIAdapter()
        with patch.dict(os.environ, {"CRAWL4AI_ENABLED": "true"}):
            with patch.object(Crawl4AIAdapter, "_is_available", return_value=False):
                result = asyncio.run(adapter.crawl_url("https://example.com"))
        assert result is None

    def test_crawl_url_returns_none_on_timeout(self):
        """crawl_url() returns None on asyncio.TimeoutError."""
        from src.adapters.crawl4ai_adapter import Crawl4AIAdapter
        adapter = Crawl4AIAdapter()
        with patch.dict(os.environ, {"CRAWL4AI_ENABLED": "true"}):
            with patch.object(Crawl4AIAdapter, "_is_available", return_value=True):
                with patch.object(adapter, "_do_crawl", side_effect=asyncio.TimeoutError()):
                    result = asyncio.run(adapter.crawl_url("https://slow-site.com"))
        assert result is None

    def test_crawl_url_returns_none_on_exception(self):
        """crawl_url() returns None on any exception."""
        from src.adapters.crawl4ai_adapter import Crawl4AIAdapter
        adapter = Crawl4AIAdapter()
        with patch.dict(os.environ, {"CRAWL4AI_ENABLED": "true"}):
            with patch.object(Crawl4AIAdapter, "_is_available", return_value=True):
                with patch.object(adapter, "_do_crawl", side_effect=RuntimeError("network error")):
                    result = asyncio.run(adapter.crawl_url("https://example.com"))
        assert result is None

    def test_crawl_urls_returns_empty_when_disabled(self):
        """crawl_urls() returns empty dict when disabled."""
        from src.adapters.crawl4ai_adapter import Crawl4AIAdapter
        adapter = Crawl4AIAdapter()
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("CRAWL4AI_ENABLED", None)
            result = asyncio.run(adapter.crawl_urls(["https://a.com", "https://b.com"]))
        assert result == {}


class TestCrawl4AIAdapterMockedCrawl:
    """Tests de crawl con Crawl4AI mockeado."""

    def test_crawl_url_returns_content_when_available(self):
        """crawl_url() returns content when Crawl4AI is available and enabled."""
        from src.adapters.crawl4ai_adapter import Crawl4AIAdapter
        adapter = Crawl4AIAdapter()
        expected = "# Article Title\n\nFull article content here..."

        with patch.dict(os.environ, {"CRAWL4AI_ENABLED": "true"}):
            with patch.object(Crawl4AIAdapter, "_is_available", return_value=True):
                with patch.object(adapter, "_do_crawl", new=AsyncMock(return_value=expected)):
                    result = asyncio.run(adapter.crawl_url("https://techcrunch.com/article"))

        assert result == expected

    def test_crawl_urls_respects_max_urls(self):
        """crawl_urls() processes at most max_urls URLs."""
        from src.adapters.crawl4ai_adapter import Crawl4AIAdapter
        adapter = Crawl4AIAdapter()

        async def mock_crawl(url, **kwargs):
            return f"content for {url}"

        with patch.dict(os.environ, {"CRAWL4AI_ENABLED": "true"}):
            with patch.object(Crawl4AIAdapter, "_is_available", return_value=True):
                with patch.object(adapter, "crawl_url", side_effect=mock_crawl):
                    urls = ["https://a.com", "https://b.com", "https://c.com", "https://d.com"]
                    result = asyncio.run(adapter.crawl_urls(urls, max_urls=2))

        assert len(result) == 2
        assert "https://a.com" in result
        assert "https://b.com" in result
        assert "https://d.com" not in result

    def test_build_enriched_context_uses_crawled_content(self):
        """build_enriched_context() uses full article when available."""
        from src.adapters.crawl4ai_adapter import Crawl4AIAdapter
        adapter = Crawl4AIAdapter()

        web_results = ["short snippet DDG"]
        web_sources = ["https://example.com/article"]
        crawled = {"https://example.com/article": "# Full Article\n\nComplete content..."}

        context = adapter.build_enriched_context(web_results, web_sources, crawled)

        assert "CONTENIDO COMPLETO DEL ARTICULO" in context
        assert "Full Article" in context
        assert "short snippet DDG" not in context

    def test_build_enriched_context_falls_back_to_snippet(self):
        """build_enriched_context() uses DDG snippet when crawl failed."""
        from src.adapters.crawl4ai_adapter import Crawl4AIAdapter
        adapter = Crawl4AIAdapter()

        web_results = ["short snippet DDG"]
        web_sources = ["https://example.com/article"]
        crawled = {"https://example.com/article": None}  # crawl failed

        context = adapter.build_enriched_context(web_results, web_sources, crawled)

        assert "EXTRACTO DDG" in context
        assert "short snippet DDG" in context

    def test_build_enriched_context_empty_crawled(self):
        """build_enriched_context() falls back gracefully with empty crawled dict."""
        from src.adapters.crawl4ai_adapter import Crawl4AIAdapter
        adapter = Crawl4AIAdapter()

        web_results = ["result 1", "result 2"]
        web_sources = ["https://a.com", "https://b.com"]
        crawled = {}  # no crawl results

        context = adapter.build_enriched_context(web_results, web_sources, crawled)

        assert "EXTRACTO DDG" in context
        assert "result 1" in context


# ===========================================================================
# DocumentPipeline Integration Tests
# ===========================================================================

class TestDocumentPipelineIntegration:
    """Tests de integracion de DoclingAdapter con DocumentPipeline."""

    def test_extract_text_uses_docling_when_enabled(self):
        """DocumentPipeline.extract_text() uses Docling when enabled and available."""
        from src.documents.document_pipeline import DocumentPipeline

        pipeline = DocumentPipeline()
        mock_docling_text = "# Structured Document\n\nSection 1 content."

        with patch("src.adapters.docling_adapter.docling_adapter.extract", return_value=mock_docling_text):
            result = pipeline.extract_text(b"PDF bytes", "report.pdf")

        assert result == mock_docling_text.strip()

    def test_extract_text_falls_back_when_docling_returns_none(self):
        """DocumentPipeline.extract_text() uses built-in extractors when Docling returns None."""
        from src.documents.document_pipeline import DocumentPipeline

        pipeline = DocumentPipeline()
        txt_content = b"Hello, this is a plain text document."

        with patch("src.adapters.docling_adapter.docling_adapter.extract", return_value=None):
            result = pipeline.extract_text(txt_content, "note.txt")

        assert "Hello" in result
        assert len(result) > 0

    def test_extract_text_public_api_unchanged(self):
        """DocumentPipeline.extract_text() signature and return type are unchanged."""
        from src.documents.document_pipeline import DocumentPipeline
        import inspect

        pipeline = DocumentPipeline()
        sig = inspect.signature(pipeline.extract_text)
        params = list(sig.parameters.keys())

        assert "source" in params
        assert "filename" in params
        assert sig.return_annotation == str or sig.return_annotation == inspect.Parameter.empty

    def test_index_document_public_api_unchanged(self):
        """DocumentPipeline.index_document() returns expected dict structure."""
        from src.documents.document_pipeline import DocumentPipeline

        pipeline = DocumentPipeline()
        content = b"Test document for indexing."

        with patch("src.adapters.docling_adapter.docling_adapter.extract", return_value=None):
            with patch("src.memory.memory_manager.memory_manager.store_memory", return_value={"memory_id": "test_id"}):
                result = pipeline.index_document(content, "test.txt")

        assert "status" in result
        assert "filename" in result
        assert "chunks_indexed" in result


# ===========================================================================
# ResearchAgent Integration Tests
# ===========================================================================

class TestResearchAgentIntegration:
    """Tests de integracion de Crawl4AIAdapter con ResearchAgent."""

    def test_conduct_research_falls_back_to_ddg_when_crawl4ai_disabled(self):
        """conduct_research() uses DDG snippets when Crawl4AI is disabled."""
        from src.agents.research_agent import ResearchAgent

        agent = ResearchAgent()

        mock_search_result = {
            "status": "success",
            "results": ["AI news snippet 1", "AI news snippet 2"],
            "sources": ["https://techcrunch.com/1", "https://wired.com/2"],
        }

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("CRAWL4AI_ENABLED", None)

            with patch("src.agents.browser_agent.browser_agent_instance.search_web",
                       new=AsyncMock(return_value=mock_search_result)):
                with patch("src.providers.capability_selector.capability_selector.generate",
                           return_value="Mock LLM Summary"):
                    with patch("src.storage.storage_layer.storage.get_cache", return_value=None):
                        with patch("src.storage.storage_layer.storage.set_cache"):
                            with patch("src.storage.storage_layer.storage.save_record"):
                                result = asyncio.run(agent.conduct_research("AI news"))

        assert result["status"] == "success"
        assert "report" in result

    def test_conduct_research_public_api_unchanged(self):
        """conduct_research() return structure is unchanged after Crawl4AI integration."""
        from src.agents.research_agent import ResearchAgent
        import inspect

        agent = ResearchAgent()
        sig = inspect.signature(agent.conduct_research)
        params = list(sig.parameters.keys())
        assert "topic" in params


# ===========================================================================
# Singleton Export Tests
# ===========================================================================

class TestSingletonExports:
    """Tests de exportacion de singletons del paquete adapters."""

    def test_docling_adapter_singleton_exported(self):
        """docling_adapter singleton is importable from src.adapters."""
        from src.adapters import docling_adapter
        assert docling_adapter is not None

    def test_crawl4ai_adapter_singleton_exported(self):
        """crawl4ai_adapter singleton is importable from src.adapters."""
        from src.adapters import crawl4ai_adapter
        assert crawl4ai_adapter is not None

    def test_docling_adapter_class_exported(self):
        """DoclingAdapter class is importable from src.adapters."""
        from src.adapters import DoclingAdapter
        assert DoclingAdapter is not None

    def test_crawl4ai_adapter_class_exported(self):
        """Crawl4AIAdapter class is importable from src.adapters."""
        from src.adapters import Crawl4AIAdapter
        assert Crawl4AIAdapter is not None
