"""
Document Pipeline — Multi-format Document Processing & Memory Indexing.
Supports PDF, DOCX, and TXT files with pure-Python zero-dependency fallbacks.

FASE A — Docling Integration:
DoclingAdapter is invoked as the primary extraction backend when DOCLING_ENABLED=true.
If unavailable or extraction fails, falls back to built-in extractors transparently.
Public API is unchanged.
"""

import io
import re
import zlib
import zipfile
import logging
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, Any, List, Optional, Union

from src.memory.memory_manager import memory_manager

log = logging.getLogger("document_pipeline")


class DocumentPipeline:
    def extract_text_from_txt(self, content_bytes: bytes) -> str:
        """Decode TXT file bytes using multiple encoding fallbacks."""
        for enc in ["utf-8", "utf-8-sig", "latin-1", "cp1252"]:
            try:
                return content_bytes.decode(enc)
            except UnicodeDecodeError:
                continue
        return content_bytes.decode("utf-8", errors="ignore")

    def extract_text_from_docx(self, content_bytes: bytes) -> str:
        """Extract text from DOCX using docx library if available, else zipfile + XML parsing."""
        try:
            import docx
            doc = docx.Document(io.BytesIO(content_bytes))
            return "\n".join([p.text for p in doc.paragraphs if p.text])
        except ImportError:
            pass

        # Pure Python fallback using built-in zipfile + XML parsing
        try:
            with zipfile.ZipFile(io.BytesIO(content_bytes)) as z:
                xml_content = z.read("word/document.xml")
                root = ET.fromstring(xml_content)
                text_nodes = []
                # Search for all text nodes <w:t>
                for elem in root.iter():
                    if elem.tag.endswith("t") and elem.text:
                        text_nodes.append(elem.text)
                return " ".join(text_nodes)
        except Exception as e:
            log.warning(f"[DocumentPipeline] DOCX XML parsing failed: {e}")
            return content_bytes.decode("utf-8", errors="ignore")

    def extract_text_from_pdf(self, content_bytes: bytes) -> str:
        """Extract text from PDF using pypdf/PyPDF2 if available, else stream regex parsing."""
        try:
            import pypdf
            reader = pypdf.PdfReader(io.BytesIO(content_bytes))
            text_pages = [page.extract_text() for page in reader.pages if page.extract_text()]
            if text_pages:
                return "\n".join(text_pages)
        except ImportError:
            pass

        try:
            import PyPDF2
            reader = PyPDF2.PdfReader(io.BytesIO(content_bytes))
            text_pages = [page.extract_text() for page in reader.pages if page.extract_text()]
            if text_pages:
                return "\n".join(text_pages)
        except ImportError:
            pass

        # Pure Python fallback stream parser
        extracted = []
        raw = content_bytes
        # Find stream data blocks
        for stream_match in re.finditer(rb"stream\r?\n(.*?)\r?\nendstream", raw, re.DOTALL):
            stream_data = stream_match.group(1)
            try:
                decompressed = zlib.decompress(stream_data)
                text = decompressed.decode("latin-1", errors="ignore")
            except Exception:
                text = stream_data.decode("latin-1", errors="ignore")

            # Extract text enclosed in parentheses (Tj / TJ operators in PDF syntax)
            tj_matches = re.findall(r"\((.*?)\)\s*Tj", text)
            if tj_matches:
                extracted.extend(tj_matches)
            else:
                # Also search for array text objects: [(...) ...] TJ
                array_matches = re.findall(r"\[(.*?)\]\s*TJ", text)
                for arr in array_matches:
                    sub_texts = re.findall(r"\((.*?)\)", arr)
                    extracted.extend(sub_texts)

        if extracted:
            return "\n".join(extracted)

        # Basic text fallback if streams unreadable
        plain = raw.decode("latin-1", errors="ignore")
        text_clips = re.findall(r"\(([\w\s.,!?-]{4,})\)", plain)
        return "\n".join(text_clips) if text_clips else plain[:2000]

    def extract_text(self, source: Union[str, Path, bytes], filename: str = "document.txt") -> str:
        """Extract text from TXT, DOCX, or PDF input.

        Extraction order:
          1. DoclingAdapter (if DOCLING_ENABLED=true and installed) — structured output.
          2. Built-in extractors (pypdf/docx/txt) — always available as fallback.
        """
        if isinstance(source, (str, Path)):
            path = Path(source)
            if not path.exists():
                raise FileNotFoundError(f"Document file not found: {source}")
            content_bytes = path.read_bytes()
            filename = path.name
        else:
            content_bytes = source

        # ── Step 1: Try DoclingAdapter (optional — structured extraction) ────
        try:
            from src.adapters.docling_adapter import docling_adapter
            docling_text = docling_adapter.extract(content_bytes, filename)
            if docling_text:
                log.info(f"[DocumentPipeline] Docling extracted '{filename}' ({len(docling_text)} chars)")
                return docling_text.strip()
        except Exception as e:
            log.debug(f"[DocumentPipeline] DoclingAdapter skipped: {e}")

        # ── Step 2: Built-in extractors (fallback — always available) ────────
        ext = filename.lower().split(".")[-1]
        if ext == "pdf":
            text = self.extract_text_from_pdf(content_bytes)
        elif ext in ("docx", "doc"):
            text = self.extract_text_from_docx(content_bytes)
        else:
            text = self.extract_text_from_txt(content_bytes)

        return text.strip()

    def chunk_text(self, text: str, chunk_size: int = 600, overlap: int = 100) -> List[str]:
        """Chunk document text into overlapping segments."""
        if not text:
            return []
        chunks = []
        start = 0
        while start < len(text):
            end = start + chunk_size
            chunk = text[start:end].strip()
            if chunk:
                chunks.append(chunk)
            start += (chunk_size - overlap)
        return chunks

    def index_document(
        self,
        source: Union[str, Path, bytes],
        filename: str = "document.txt",
        user_id: str = "daniel"
    ) -> Dict[str, Any]:
        """Extract text, chunk document, and store chunks into long-term memory."""
        extracted_text = self.extract_text(source, filename)
        if not extracted_text:
            return {"status": "FAILED", "filename": filename, "chunks_indexed": 0, "reason": "No text extracted"}

        chunks = self.chunk_text(extracted_text)
        stored_ids = []
        for i, chunk in enumerate(chunks):
            content_str = f"[Document: {filename} | Chunk {i+1}/{len(chunks)}]\n{chunk}"
            res = memory_manager.store_memory(
                content=content_str,
                category="document",
                importance=1.0,
                metadata={"filename": filename, "chunk_index": i, "total_chunks": len(chunks)}
            )
            stored_ids.append(res.get("memory_id"))

        log.info(f"[DocumentPipeline] Indexed document '{filename}' with {len(chunks)} chunks.")
        return {
            "status": "SUCCESS",
            "filename": filename,
            "text_length": len(extracted_text),
            "chunks_indexed": len(chunks),
            "memory_ids": stored_ids,
            "sample": extracted_text[:200]
        }

    def query_documents(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """Query indexed document memory snippets."""
        return memory_manager.retrieve_memory(query, top_k=top_k)


document_pipeline = DocumentPipeline()
