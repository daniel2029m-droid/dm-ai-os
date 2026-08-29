"""Facebook intelligence subpackage — analytics, NLP, monetization, recommendations."""

from .profile import ProfileIntelligence
from .comments import CommentIntelligence
from .audience import AudienceIntelligence
from .content import ContentIntelligence
from .prompts import PromptIntelligence
from .monetization import MonetizationIntelligence
from .recommendations import RecommendationEngine
from .competitors import CompetitorIntelligence

__all__ = [
    "ProfileIntelligence",
    "CommentIntelligence",
    "AudienceIntelligence",
    "ContentIntelligence",
    "PromptIntelligence",
    "MonetizationIntelligence",
    "RecommendationEngine",
    "CompetitorIntelligence",
]
