"""
Content Intelligence
====================
For every publication store and query:
prompt, AI model, character ID, publish date/hour, caption, CTA, hashtags,
style, image type, reach, views, comments, shares, revenue, RPM.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ..database import FacebookDatabase, facebook_db

log = logging.getLogger("facebook.intelligence.content")

_HASHTAG_RE = re.compile(r"#[\wáéíóúñüÁÉÍÓÚÑÜ]+", re.U)
_CTA_PATTERNS = [
    re.compile(r"(link in bio|enlace en bio|compra ahora|buy now|shop now|aprende m[aá]s|learn more|sign up|reg[ií]strate|comenta|comment|share|comparte|s[ií]gueme|follow|dm|inbox)", re.I),
    re.compile(r"(https?://\S+)", re.I),
]


class ContentIntelligence:
    def __init__(self, db: Optional[FacebookDatabase] = None):
        self.db = db or facebook_db

    def ingest_post(self, page_id: str, post: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize and store a single publication record."""
        normalized = self.normalize_post(post)
        row_id = self.db.upsert_content(page_id, normalized)
        return {"status": "success", "row_id": row_id, "post_id": normalized["post_id"], "post": normalized}

    def ingest_posts(self, page_id: str, posts: List[Dict[str, Any]]) -> Dict[str, Any]:
        results = []
        for p in posts:
            try:
                results.append(self.ingest_post(page_id, p))
            except Exception as e:
                results.append({"status": "error", "error": str(e), "post": p})
        ok = sum(1 for r in results if r.get("status") == "success")
        return {"status": "success", "stored": ok, "total": len(posts), "results": results}

    def normalize_post(self, post: Dict[str, Any]) -> Dict[str, Any]:
        caption = post.get("caption") or post.get("message") or post.get("text") or ""
        hashtags = post.get("hashtags")
        if not hashtags:
            hashtags = _HASHTAG_RE.findall(caption)
        elif isinstance(hashtags, str):
            hashtags = [h.strip() for h in re.split(r"[\s,]+", hashtags) if h.strip()]

        publish_date = post.get("publish_date") or post.get("created_time") or post.get("date")
        publish_hour = post.get("publish_hour")
        if publish_hour is None and publish_date:
            publish_hour = _extract_hour(str(publish_date))

        cta = post.get("cta")
        if not cta:
            cta = self._detect_cta(caption)

        reach = _num(post.get("reach"))
        views = _num(post.get("views") or post.get("video_views"))
        comments = _int(post.get("comments_count", post.get("comments")))
        shares = _int(post.get("shares"))
        likes = _int(post.get("likes") or post.get("reactions"))
        revenue = _num(post.get("revenue") or post.get("earnings"))
        rpm = _num(post.get("rpm"))
        if rpm is None and revenue is not None and views:
            # RPM = revenue per 1000 views
            rpm = (revenue / views) * 1000.0 if views else None

        engagement_rate = _num(post.get("engagement_rate"))
        if engagement_rate is None and reach:
            eng = (likes or 0) + (comments or 0) + (shares or 0)
            engagement_rate = eng / reach if reach else None

        post_id = str(post.get("post_id") or post.get("id") or "")
        if not post_id:
            raise ValueError("post_id required")

        return {
            "post_id": post_id,
            "post_type": post.get("post_type") or post.get("type") or "post",
            "prompt": post.get("prompt"),
            "ai_model": post.get("ai_model") or post.get("model"),
            "character_id": post.get("character_id"),
            "publish_date": str(publish_date) if publish_date else None,
            "publish_hour": publish_hour,
            "caption": caption,
            "cta": cta,
            "hashtags": hashtags,
            "style": post.get("style"),
            "image_type": post.get("image_type") or post.get("media_type"),
            "reach": reach,
            "views": views,
            "comments_count": comments or 0,
            "shares": shares or 0,
            "likes": likes or 0,
            "revenue": revenue,
            "rpm": rpm,
            "engagement_rate": engagement_rate,
            "permalink": post.get("permalink") or post.get("url"),
        }

    def list_posts(self, page_id: str, order_by: str = "publish_date", limit: int = 100) -> List[Dict[str, Any]]:
        return self.db.list_content(page_id, limit=limit, order_by=order_by)

    def top_by(self, page_id: str, metric: str = "revenue", limit: int = 10) -> List[Dict[str, Any]]:
        allowed = {"revenue", "rpm", "reach", "views"}
        if metric not in allowed:
            metric = "revenue"
        return self.db.list_content(page_id, limit=limit, order_by=metric)

    def performance_report(self, page_id: str) -> Dict[str, Any]:
        agg = self.db.content_aggregates(page_id)
        top_rev = self.top_by(page_id, "revenue", 5)
        top_rpm = self.top_by(page_id, "rpm", 5)
        by_hour = self.db.best_posting_hours(page_id, limit=8)
        by_cat = self.db.content_by_category_proxy(page_id)
        return {
            "page_id": page_id,
            "aggregates": agg,
            "top_revenue": top_rev,
            "top_rpm": top_rpm,
            "best_hours": by_hour,
            "categories": by_cat,
            "generated_at": _now(),
        }

    def link_generation_metadata(
        self,
        page_id: str,
        post_id: str,
        *,
        prompt: Optional[str] = None,
        ai_model: Optional[str] = None,
        character_id: Optional[str] = None,
        style: Optional[str] = None,
        image_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Attach AI generation metadata to an existing or new post record."""
        existing = self.db.get_content(page_id, post_id) or {"post_id": post_id}
        if prompt is not None:
            existing["prompt"] = prompt
        if ai_model is not None:
            existing["ai_model"] = ai_model
        if character_id is not None:
            existing["character_id"] = character_id
        if style is not None:
            existing["style"] = style
        if image_type is not None:
            existing["image_type"] = image_type
        return self.ingest_post(page_id, existing)

    @staticmethod
    def _detect_cta(caption: str) -> Optional[str]:
        for p in _CTA_PATTERNS:
            m = p.search(caption or "")
            if m:
                return m.group(0)
        return None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _num(v: Any) -> Optional[float]:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _int(v: Any) -> Optional[int]:
    if v is None:
        return None
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


def _extract_hour(date_str: str) -> Optional[int]:
    # ISO or "YYYY-MM-DD HH:MM"
    m = re.search(r"T(\d{2})", date_str) or re.search(r"\s(\d{2}):", date_str)
    if m:
        try:
            return int(m.group(1))
        except ValueError:
            return None
    return None
