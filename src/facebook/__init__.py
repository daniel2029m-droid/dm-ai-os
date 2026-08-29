"""
DM AI OS — Facebook Intelligence Platform
==========================================
Autonomous Facebook growth, analytics, monetization and learning stack.

Modules:
  - connector          Playwright automation + persistent session
  - session_manager    Cookie/session storage & recovery
  - network_interceptor  XHR/Fetch capture & dedup
  - ocr_extractor      Screenshot + OCR for graphic-only metrics
  - database           Normalized schema, migrations, backups
  - intelligence.*     Profile, comments, audience, content, prompts,
                       monetization, recommendations, competitors
  - llm_analyzer       Local LLM analysis of historical data
  - pipeline           Learning loop: Collect→Normalize→Store→Analyze→Recommend→Optimize
"""

from .database import FacebookDatabase, facebook_db
from .session_manager import FacebookSessionManager, facebook_session_manager
from .connector import FacebookConnector, facebook_connector
from .network_interceptor import NetworkInterceptor
from .ocr_extractor import FacebookOCRExtractor, facebook_ocr
from .llm_analyzer import FacebookLLMAnalyzer, facebook_llm
from .pipeline import FacebookLearningLoop, facebook_learning_loop

__all__ = [
    "FacebookDatabase",
    "facebook_db",
    "FacebookSessionManager",
    "facebook_session_manager",
    "FacebookConnector",
    "facebook_connector",
    "NetworkInterceptor",
    "FacebookOCRExtractor",
    "facebook_ocr",
    "FacebookLLMAnalyzer",
    "facebook_llm",
    "FacebookLearningLoop",
    "facebook_learning_loop",
]
