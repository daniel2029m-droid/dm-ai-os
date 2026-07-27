"""
Phase 11 — Multimodal Capabilities & Document Pipeline Test Suite
==================================================================
Tests:
  - Vision model detection & image extraction from OpenAI format (image_url / base64)
  - Multimodal request routing in BrainPipeline & OpenAI ChatCompletions endpoint
  - DocumentPipeline text extraction for TXT, DOCX, and PDF formats
  - Document indexing into persistent memory & QA querying
  - Web Search capability in BrowserAgent & MCP tools
  - Ollama local model detection & dynamic capability matrix (texto, razonamiento, visión, código, investigación)
"""

import json
import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.api.server import app
from src.providers.capability_selector import capability_selector, CAPABILITY_MAP
from src.documents.document_pipeline import document_pipeline
from src.api.openai_compat.chat_completions_router import _extract_multimodal_content
from src.mcp.registry import mcp_registry
from src.mcp.tools import index_document, search_documents, web_search, get_capability_matrix


@pytest.fixture(scope="module")
def client():
    return TestClient(app, raise_server_exceptions=True)


# ─────────────────────────────────────────────────────────────────────────────
# 1. Vision & Multimodal Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestVisionMultimodal:

    def test_vision_capability_mapping_exists(self):
        assert "vision" in CAPABILITY_MAP
        assert "ocr" in CAPABILITY_MAP
        assert "llava" in CAPABILITY_MAP["vision"] or "bakllava" in CAPABILITY_MAP["vision"]

    def test_extract_multimodal_content_text_and_base64_image(self):
        from src.api.openai_compat.schemas_openai import ChatMessage

        sample_b64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
        msg = ChatMessage(
            role="user",
            content=[
                {"type": "text", "text": "Describe esta imagen"},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{sample_b64}"}}
            ]
        )

        prompt, images = _extract_multimodal_content([msg])
        assert prompt == "Describe esta imagen"
        assert len(images) == 1
        assert images[0] == sample_b64

    def test_chat_completions_multimodal_image_request(self, client):
        from src.api.brain_pipeline import brain_pipeline
        brain_pipeline.cache.clear()

        sample_b64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
        payload = {
            "model": "dm-autonomous-brain",
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "¿Qué hay en esta imagen de prueba multimodal?"},
                        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{sample_b64}"}}
                    ]
                }
            ]
        }

        with patch("src.providers.capability_selector.capability_selector.generate") as mock_gen:
            mock_gen.return_value = "La imagen muestra un píxel o gráfico de prueba."
            resp = client.post("/v1/chat/completions", json=payload)
            assert resp.status_code == 200
            data = resp.json()
            content = data["choices"][0]["message"]["content"]
            assert "píxel" in content or "grafico" in content or "imagen" in content or "prueba" in content
            assert mock_gen.called
            _, kwargs = mock_gen.call_args
            assert kwargs.get("capability") == "vision"
            assert kwargs.get("images") == [sample_b64]


# ─────────────────────────────────────────────────────────────────────────────
# 2. Document Pipeline & Memory Indexing Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestDocumentPipeline:

    def test_extract_text_txt(self):
        sample_txt = "Demostración de extracción de texto TXT para DM AI OS.".encode("utf-8")
        text = document_pipeline.extract_text(sample_txt, "demo.txt")
        assert "Demostración" in text
        assert "DM AI OS" in text

    def test_extract_text_docx_xml_fallback(self):
        import io
        import zipfile

        # Generate a minimal valid docx in-memory
        docx_buffer = io.BytesIO()
        with zipfile.ZipFile(docx_buffer, 'w') as z:
            xml_content = (
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                '<w:body><w:p><w:r><w:t>Documento DOCX de prueba para DM AI OS.</w:t></w:r></w:p></w:body>'
                '</w:document>'
            )
            z.writestr("word/document.xml", xml_content)

        text = document_pipeline.extract_text(docx_buffer.getvalue(), "test.docx")
        assert "Documento DOCX de prueba" in text

    def test_extract_text_pdf_fallback(self):
        import io
        import zlib

        # Minimal PDF structure in-memory
        stream_content = b"(PDF de prueba para DM AI OS) Tj"
        compressed = zlib.compress(stream_content)
        pdf_bytes = (
            b"%PDF-1.4\n"
            b"1 0 obj\n<< /Length " + str(len(compressed)).encode() + b" /Filter /FlateDecode >>\n"
            b"stream\n" + compressed + b"\nendstream\n"
            b"endobj\n"
            b"%%EOF\n"
        )

        text = document_pipeline.extract_text(pdf_bytes, "manual.pdf")
        assert "PDF de prueba" in text or "DM AI OS" in text

    def test_index_and_query_document(self):
        doc_content = (
            "DM AI OS Phase 11 especificación de documentos:\n"
            "El sistema es capaz de indexar archivos PDF, DOCX y TXT en la memoria a largo plazo. "
            "Daniel Morales es el creador de la arquitectura multiagente."
        ).encode("utf-8")

        res = document_pipeline.index_document(doc_content, filename="fase11_spec.txt")
        assert res["status"] == "SUCCESS"
        assert res["chunks_indexed"] > 0

        # Query indexed document chunks
        queries = document_pipeline.query_documents("especificación de documentos", top_k=3)
        assert len(queries) > 0
        assert any("fase11_spec.txt" in q.get("content", "") or "especificación" in q.get("content", "") for q in queries)


# ─────────────────────────────────────────────────────────────────────────────
# 3. Web Search & Navigation Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestWebSearchNavigation:

    @pytest.mark.asyncio
    async def test_browser_agent_web_search(self):
        from src.agents.browser_agent import browser_agent_instance

        with patch("src.providers.capability_selector.capability_selector.generate") as mock_gen:
            mock_gen.return_value = "Resultado sintético de búsqueda web."
            res = await browser_agent_instance.search_web("noticias tecnología")
            assert res["status"] == "success"
            assert "results" in res
            assert len(res["results"]) > 0

    @pytest.mark.asyncio
    async def test_mcp_web_search_tool(self):
        with patch("src.agents.browser_agent.browser_agent_instance.search_web") as mock_search:
            mock_search.return_value = {"status": "success", "results": ["Página 1", "Página 2"]}
            res = await web_search(query="python mcp tools")
            assert res["status"] == "success"
            assert len(res["results"]) == 2


# ─────────────────────────────────────────────────────────────────────────────
# 4. Local Model Matrix Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestLocalModelMatrix:

    def test_get_capability_matrix_format(self):
        matrix = capability_selector.get_capability_matrix()
        assert "status" in matrix
        assert "installed_models" in matrix
        assert "capabilities" in matrix
        caps = matrix["capabilities"]
        assert "texto" in caps
        assert "razonamiento" in caps
        assert "visión" in caps
        assert "código" in caps
        assert "investigación" in caps

    @pytest.mark.asyncio
    async def test_mcp_capability_matrix_tool(self):
        res = await get_capability_matrix()
        assert "capabilities" in res
        assert "texto" in res["capabilities"]

    def test_mcp_registry_has_phase11_tools(self):
        tools = mcp_registry.list_tools()
        names = [t["name"] for t in tools]
        assert "index_document" in names
        assert "search_documents" in names
        assert "web_search" in names
        assert "get_capability_matrix" in names
