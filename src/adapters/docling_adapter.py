"""
DoclingAdapter — P3 Open Source Integration (Fase A)
=====================================================
Wraps Docling (IBM Research) as an optional extraction backend for DocumentPipeline.

Docling soporta: PDF (con/sin OCR), DOCX, XLSX, PPTX, HTML, AsciiDoc, Markdown.
Produce salida estructurada con jerarquia de secciones, tablas y metadatos preservados.

Patron DM AI OS:
- _is_available() verifica instalacion antes de invocar.
- Si no disponible: retorna None y DocumentPipeline usa extractores actuales.
- DOCLING_ENABLED=true en .env para activar (opt-in).
- DOCLING_OCR_ENABLED=true para activar OCR (requiere torch, opcional).

NO modifica ningun modulo congelado. DocumentPipeline.extract_text() lo invoca
opcionalmente ANTES de sus extractores actuales.

Referencia: https://github.com/DS4SD/docling
"""

import io
import os
import logging
from pathlib import Path
from typing import Optional

log = logging.getLogger("docling_adapter")


class DoclingAdapter:
    """Thin adapter that wraps Docling as a structured document extraction backend."""

    _ENABLED_ENV = "DOCLING_ENABLED"
    _OCR_ENV = "DOCLING_OCR_ENABLED"

    # Supported extension -> Docling format mapping
    _FORMAT_MAP = {
        "pdf": "pdf",
        "docx": "docx",
        "doc": "docx",
        "xlsx": "xlsx",
        "xls": "xlsx",
        "pptx": "pptx",
        "ppt": "pptx",
        "html": "html",
        "htm": "html",
        "md": "markdown",
        "txt": "asciidoc",
        "adoc": "asciidoc",
    }

    @staticmethod
    def _is_available() -> bool:
        """Check if Docling library is installed."""
        try:
            import docling  # noqa: F401
            return True
        except ImportError:
            return False

    @staticmethod
    def _is_enabled() -> bool:
        """Check DOCLING_ENABLED env var (defaults to False — opt-in)."""
        return os.getenv("DOCLING_ENABLED", "false").lower() in ("true", "1", "yes")

    @staticmethod
    def _ocr_enabled() -> bool:
        """Check DOCLING_OCR_ENABLED env var (defaults to False — requires torch)."""
        return os.getenv("DOCLING_OCR_ENABLED", "false").lower() in ("true", "1", "yes")

    def extract(self, content_bytes: bytes, filename: str) -> Optional[str]:
        """
        Extract structured text from document bytes using Docling.

        Returns:
            str  — Markdown-formatted extracted text with preserved structure.
            None — If Docling unavailable, disabled, or extraction fails.
                   Caller must fall back to current extractors.

        Args:
            content_bytes: Raw document bytes.
            filename: Original filename (used to determine format).
        """
        if not self._is_enabled():
            log.debug("[DoclingAdapter] Disabled (DOCLING_ENABLED != true). Using fallback.")
            return None

        if not self._is_available():
            log.warning(
                "[DoclingAdapter] Docling not installed. Install with: pip install docling. "
                "Falling back to built-in extractors."
            )
            return None

        ext = Path(filename).suffix.lstrip(".").lower()
        if ext not in self._FORMAT_MAP:
            log.debug(f"[DoclingAdapter] Unsupported extension '{ext}'. Using fallback.")
            return None

        try:
            return self._do_extract(content_bytes, filename, ext)
        except Exception as e:
            log.warning(f"[DoclingAdapter] Extraction failed for '{filename}': {e}. Using fallback.")
            return None

    def _do_extract(self, content_bytes: bytes, filename: str, ext: str) -> str:
        """Perform the actual Docling extraction."""
        from docling.document_converter import DocumentConverter, PdfFormatOption
        from docling.datamodel.base_models import InputFormat
        from docling.datamodel.pipeline_options import PdfPipelineOptions

        # Build pipeline options
        pipeline_options = None
        input_format = self._FORMAT_MAP.get(ext, "pdf")

        if ext == "pdf":
            pdf_opts = PdfPipelineOptions()
            pdf_opts.do_ocr = self._ocr_enabled()
            pdf_opts.do_table_structure = True  # Always preserve tables
            pipeline_options = {
                InputFormat.PDF: PdfFormatOption(pipeline_options=pdf_opts)
            }

        # Build converter
        if pipeline_options:
            converter = DocumentConverter(format_options=pipeline_options)
        else:
            converter = DocumentConverter()

        # Convert from bytes via temp BytesIO
        # Docling requires a file path or URL; we use a temp file approach
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=f".{ext}", delete=False) as tmp:
            tmp.write(content_bytes)
            tmp_path = tmp.name

        try:
            result = converter.convert(tmp_path)
            doc = result.document
            extracted = doc.export_to_markdown()
            log.info(
                f"[DoclingAdapter] Extracted '{filename}' ({ext}) -> "
                f"{len(extracted)} chars | OCR={self._ocr_enabled()}"
            )
            return extracted
        finally:
            import os as _os
            try:
                _os.unlink(tmp_path)
            except Exception:
                pass

    def extract_chunked(
        self,
        content_bytes: bytes,
        filename: str,
        max_chunk_size: int = 600
    ) -> Optional[list]:
        """
        Extract using Docling's semantic chunking (sections, paragraphs).

        Returns list of semantic chunk dicts:
            [{"text": str, "type": str, "level": int}, ...]
        or None if unavailable.

        Semantic chunks are preferred over character-based chunking because
        they preserve section boundaries for better RAG retrieval.
        """
        if not self._is_enabled() or not self._is_available():
            return None

        ext = Path(filename).suffix.lstrip(".").lower()
        if ext not in self._FORMAT_MAP:
            return None

        try:
            from docling.document_converter import DocumentConverter
            from docling.chunking import HybridChunker

            converter = DocumentConverter()

            import tempfile
            with tempfile.NamedTemporaryFile(suffix=f".{ext}", delete=False) as tmp:
                tmp.write(content_bytes)
                tmp_path = tmp.name

            try:
                result = converter.convert(tmp_path)
                doc = result.document

                chunker = HybridChunker(max_tokens=max_chunk_size)
                chunks_iter = chunker.chunk(dl_doc=doc)
                chunks = []
                for chunk in chunks_iter:
                    chunks.append({
                        "text": chunk.text,
                        "type": getattr(chunk, "label", "text"),
                        "level": getattr(chunk, "level", 0),
                    })

                log.info(
                    f"[DoclingAdapter] Semantic chunking '{filename}' -> {len(chunks)} chunks"
                )
                return chunks
            finally:
                import os as _os
                try:
                    _os.unlink(tmp_path)
                except Exception:
                    pass

        except Exception as e:
            log.warning(f"[DoclingAdapter] Semantic chunking failed for '{filename}': {e}")
            return None


# Module-level singleton
docling_adapter = DoclingAdapter()
