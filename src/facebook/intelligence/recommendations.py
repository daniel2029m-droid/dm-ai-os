"""
Recommendation Engine
=====================
Generate daily recommendations based on historical Facebook intelligence data.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ..database import FacebookDatabase, facebook_db
from .audience import AudienceIntelligence
from .comments import CommentIntelligence
from .content import ContentIntelligence
from .monetization import MonetizationIntelligence
from .profile import ProfileIntelligence
from .prompts import PromptIntelligence

log = logging.getLogger("facebook.intelligence.recommendations")


class RecommendationEngine:
    def __init__(self, db: Optional[FacebookDatabase] = None):
        self.db = db or facebook_db
        self.profile = ProfileIntelligence(self.db)
        self.content = ContentIntelligence(self.db)
        self.monetization = MonetizationIntelligence(self.db)
        self.prompts = PromptIntelligence(self.db)
        self.audience = AudienceIntelligence(self.db)
        self.comments = CommentIntelligence(self.db)

    def generate_daily(self, page_id: str, rec_date: Optional[str] = None) -> Dict[str, Any]:
        rec_date = rec_date or _now()[:10]
        recs: List[Dict[str, Any]] = []

        # Monetization-driven
        mono = self.monetization.analyze(page_id)
        if mono.get("rpm_delta_pct") is not None and mono["rpm_delta_pct"] < -5:
            recs.append({
                "category": "monetization",
                "priority": 1,
                "title": "RPM declining — adjust content mix",
                "body": "; ".join((mono.get("rpm_drop_reasons") or [])[:3])
                or "RPM dropped significantly. Review low-earning posts and shift toward top categories.",
                "evidence": {
                    "rpm_current": mono.get("rpm_current"),
                    "rpm_delta_pct": mono.get("rpm_delta_pct"),
                },
            })
        elif mono.get("rpm_delta_pct") is not None and mono["rpm_delta_pct"] > 5:
            recs.append({
                "category": "monetization",
                "priority": 3,
                "title": "RPM rising — double down",
                "body": "; ".join((mono.get("rpm_rise_reasons") or [])[:3])
                or "RPM is increasing. Scale formats and schedules that are working.",
                "evidence": {
                    "rpm_current": mono.get("rpm_current"),
                    "rpm_delta_pct": mono.get("rpm_delta_pct"),
                },
            })

        if mono.get("best_hours"):
            hours = ", ".join(f"{h.get('hour')}:00" for h in mono["best_hours"][:3])
            recs.append({
                "category": "schedule",
                "priority": 2,
                "title": "Optimal posting windows",
                "body": f"Publish during peak earning hours: {hours}.",
                "evidence": {"best_hours": mono["best_hours"][:3]},
            })

        if mono.get("best_categories"):
            cats = mono["best_categories"][:3]
            cat_str = ", ".join(
                f"{c.get('category')} (rev={c.get('total_revenue')})" for c in cats
            )
            recs.append({
                "category": "content",
                "priority": 2,
                "title": "Prioritize top earning categories",
                "body": f"Focus production on: {cat_str}.",
                "evidence": {"categories": cats},
            })

        highest = mono.get("highest_earning")
        lowest = mono.get("lowest_earning")
        if highest and highest.get("prompt"):
            recs.append({
                "category": "prompt",
                "priority": 2,
                "title": "Reuse patterns from top earner",
                "body": f"Top post {highest.get('post_id')} used prompt patterns worth replicating (not copying captions).",
                "evidence": {
                    "post_id": highest.get("post_id"),
                    "revenue": highest.get("revenue"),
                    "style": highest.get("style"),
                    "ai_model": highest.get("ai_model"),
                },
            })
        if lowest and highest and lowest.get("post_id") != highest.get("post_id"):
            recs.append({
                "category": "content",
                "priority": 4,
                "title": "Reduce low-earning formats",
                "body": (
                    f"Post {lowest.get('post_id')} underperformed "
                    f"(revenue={lowest.get('revenue')}, type={lowest.get('post_type')}). "
                    f"Deprioritize similar style/image_type."
                ),
                "evidence": {
                    "post_id": lowest.get("post_id"),
                    "style": lowest.get("style"),
                    "image_type": lowest.get("image_type"),
                },
            })

        # Audience windows
        windows = self.audience.best_posting_windows(page_id)
        if windows:
            top_w = windows[0]
            recs.append({
                "category": "audience",
                "priority": 3,
                "title": "Align posts with audience activity",
                "body": f"Best combined audience+performance hour: {top_w.get('hour')}:00.",
                "evidence": {"window": top_w},
            })

        # Comments / community
        csum = self.comments.summary(page_id)
        if csum.get("total", 0) > 0:
            if csum.get("negative_ratio", 0) > 0.3:
                recs.append({
                    "category": "community",
                    "priority": 1,
                    "title": "Address negative sentiment spike",
                    "body": (
                        f"Negative comments ratio is {csum['negative_ratio']:.0%}. "
                        f"Top intents: {csum.get('intents')}. Review support/complaint threads."
                    ),
                    "evidence": csum,
                })
            clusters = self.comments.cluster_recurring_requests(page_id)
            if clusters:
                top_cl = clusters[0]
                recs.append({
                    "category": "community",
                    "priority": 3,
                    "title": "Respond to recurring audience request",
                    "body": (
                        f"Cluster '{top_cl.get('cluster_id')}' has {top_cl.get('size')} similar requests: "
                        f"{(top_cl.get('sample') or '')[:120]}"
                    ),
                    "evidence": top_cl,
                })
            if csum.get("questions", 0) > 5:
                recs.append({
                    "category": "community",
                    "priority": 4,
                    "title": "Answer open questions in comments",
                    "body": f"There are {csum['questions']} question-like comments — answering boosts engagement and ranking.",
                    "evidence": {"questions": csum["questions"]},
                })

        # Prompt variants
        top_prompts = self.prompts.best_monetizing(page_id, limit=3)
        if top_prompts:
            variants = self.prompts.generate_variants(
                page_id,
                prompt_text=top_prompts[0].get("prompt_text"),
                n=3,
                use_llm=False,
            )
            recs.append({
                "category": "prompt",
                "priority": 3,
                "title": "Test optimized prompt variants",
                "body": "Generate next assets using variants of your best-monetizing prompt.",
                "evidence": {
                    "base": top_prompts[0].get("prompt_text"),
                    "variants": variants.get("variants", [])[:3],
                    "score": top_prompts[0].get("score"),
                },
            })

        # Profile growth
        profile = self.profile.collect_summary(page_id)
        followers_trend = (profile.get("trends") or {}).get("followers") or {}
        if followers_trend.get("direction") == "down":
            recs.append({
                "category": "growth",
                "priority": 2,
                "title": "Follower growth is declining",
                "body": (
                    f"Followers trend down (change_pct={followers_trend.get('change_pct')}). "
                    f"Increase reel frequency and CTA strength during peak hours."
                ),
                "evidence": followers_trend,
            })

        # Ensure at least a baseline recommendation
        if not recs:
            recs.append({
                "category": "general",
                "priority": 5,
                "title": "Collect more performance data",
                "body": (
                    "Not enough historical data for strong recommendations. "
                    "Run the learning loop after publishing more instrumented posts."
                ),
                "evidence": {"aggregates": mono.get("aggregates")},
            })

        stored_ids = []
        for rec in recs:
            rec["rec_date"] = rec_date
            rec["generated_at"] = _now()
            rid = self.db.store_recommendation(page_id, rec)
            if rid:
                stored_ids.append(rid)
                rec["id"] = rid

        return {
            "status": "success",
            "page_id": page_id,
            "rec_date": rec_date,
            "count": len(recs),
            "stored": len(stored_ids),
            "recommendations": sorted(recs, key=lambda r: r.get("priority", 99)),
        }

    def list_daily(self, page_id: str, rec_date: Optional[str] = None) -> List[Dict[str, Any]]:
        return self.db.list_recommendations(page_id, rec_date=rec_date)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
