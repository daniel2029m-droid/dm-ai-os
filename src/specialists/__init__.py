"""
DM AI OS — Autonomous Digital Employees & Specialists Package (Fase 14)
======================================================================
Contains all 20 Autonomous Business Specialist Workers:
1. FacebookSpecialist
2. InstagramSpecialist
3. TikTokSpecialist
4. YouTubeSpecialist
5. FanvueSpecialist
6. WhatsAppSpecialist
7. SEOSpecialist
8. ResearchSpecialist
9. ContentSpecialist
10. AdsSpecialist
11. LocalBusinessSpecialist
12. SalesSpecialist
13. CryptoSpecialist
14. CustomerSupportSpecialist
15. EducationSpecialist
16. BusinessSpecialist
17. AnalyticsSpecialist
18. AutomationSpecialist
19. CourseBuilderSpecialist
20. WorkflowSpecialist
"""

from .tenant_manager import tenant_manager, TenantContext, TenantManager
from .base_specialist import BaseSpecialist
from .specialist_registry import specialist_registry, SpecialistRegistry

from .facebook_specialist import FacebookSpecialist
from .instagram_specialist import InstagramSpecialist
from .tiktok_specialist import TikTokSpecialist
from .youtube_specialist import YouTubeSpecialist
from .fanvue_specialist import FanvueSpecialist
from .whatsapp_specialist import WhatsAppSpecialist

from .seo_specialist import SEOSpecialist
from .research_specialist import ResearchSpecialist
from .content_specialist import ContentSpecialist
from .ads_specialist import AdsSpecialist
from .local_business_specialist import LocalBusinessSpecialist
from .sales_specialist import SalesSpecialist

from .crypto_specialist import CryptoSpecialist
from .customer_support_specialist import CustomerSupportSpecialist
from .education_specialist import EducationSpecialist
from .business_specialist import BusinessSpecialist
from .analytics_specialist import AnalyticsSpecialist
from .automation_specialist import AutomationSpecialist
from .course_builder_specialist import CourseBuilderSpecialist
from .workflow_specialist import WorkflowSpecialist
from .higgsfield_specialist import HiggsfieldSpecialist

# Register default instances of all specialists into the registry
_all_specialist_classes = [
    FacebookSpecialist,
    InstagramSpecialist,
    TikTokSpecialist,
    YouTubeSpecialist,
    FanvueSpecialist,
    WhatsAppSpecialist,
    SEOSpecialist,
    ResearchSpecialist,
    ContentSpecialist,
    AdsSpecialist,
    LocalBusinessSpecialist,
    SalesSpecialist,
    CryptoSpecialist,
    CustomerSupportSpecialist,
    EducationSpecialist,
    BusinessSpecialist,
    AnalyticsSpecialist,
    AutomationSpecialist,
    CourseBuilderSpecialist,
    WorkflowSpecialist,
    HiggsfieldSpecialist,
]

for cls in _all_specialist_classes:
    specialist_registry.register(cls())

__all__ = [
    "tenant_manager",
    "TenantContext",
    "TenantManager",
    "BaseSpecialist",
    "specialist_registry",
    "SpecialistRegistry",
    "FacebookSpecialist",
    "InstagramSpecialist",
    "TikTokSpecialist",
    "YouTubeSpecialist",
    "FanvueSpecialist",
    "WhatsAppSpecialist",
    "SEOSpecialist",
    "ResearchSpecialist",
    "ContentSpecialist",
    "AdsSpecialist",
    "LocalBusinessSpecialist",
    "SalesSpecialist",
    "CryptoSpecialist",
    "CustomerSupportSpecialist",
    "EducationSpecialist",
    "BusinessSpecialist",
    "AnalyticsSpecialist",
    "AutomationSpecialist",
    "CourseBuilderSpecialist",
    "WorkflowSpecialist",
    "HiggsfieldSpecialist",
]
