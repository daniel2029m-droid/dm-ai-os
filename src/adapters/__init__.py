"""
DM AI OS — Adapters Package
Thin adapters that integrate mature Open Source engines as optional backends.

Pattern: Each adapter checks availability (_is_available()) before using the
external library. If unavailable, callers fall back to current behavior.
Zero regressions guaranteed.

Phase A: docling_adapter, crawl4ai_adapter
Phase B: browser_use_adapter, vector_backend
Phase C: pocketflow_adapter, vision_adapter
"""

from .docling_adapter import DoclingAdapter, docling_adapter
from .crawl4ai_adapter import Crawl4AIAdapter, crawl4ai_adapter
from .browser_use_adapter import BrowserUseAdapter, browser_use_adapter
from .pocketflow_adapter import PocketFlowAdapter, pocketflow_adapter
from .vision_adapter import VisionAdapter, vision_adapter
from .higgsfield_adapter import HiggsfieldAdapter, higgsfield_adapter

__all__ = [
    "DoclingAdapter",
    "docling_adapter",
    "Crawl4AIAdapter",
    "crawl4ai_adapter",
    "BrowserUseAdapter",
    "browser_use_adapter",
    "PocketFlowAdapter",
    "pocketflow_adapter",
    "VisionAdapter",
    "vision_adapter",
    "HiggsfieldAdapter",
    "higgsfield_adapter",
]

