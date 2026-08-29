"""
Audience Intelligence
=====================
Age, gender, country, city, active hours, and growth trends.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ..database import FacebookDatabase, facebook_db

log = logging.getLogger("facebook.intelligence.audience")


class AudienceIntelligence:
    def __init__(self, db: Optional[FacebookDatabase] = None):
        self.db = db or facebook_db

    def ingest_demographics(
        self,
        page_id: str,
        rows: List[Dict[str, Any]],
        snapshot_at: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Ingest demographic rows. Each row may include:
        age_bucket, gender, country, city, percentage, absolute_count.
        """
        snapshot_at = snapshot_at or _now()
        stored = 0
        for row in rows:
            payload = {
                "snapshot_at": snapshot_at,
                "age_bucket": row.get("age_bucket") or row.get("age"),
                "gender": row.get("gender"),
                "country": row.get("country"),
                "city": row.get("city"),
                "percentage": _num(row.get("percentage") or row.get("pct")),
                "absolute_count": _int(row.get("absolute_count") or row.get("count")),
                "metric_type": row.get("metric_type", "demographic"),
            }
            if self.db.store_audience_row(page_id, payload) is not None:
                stored += 1
        return {"status": "success", "stored": stored, "received": len(rows)}

    def ingest_active_hours(
        self,
        page_id: str,
        hours: List[Dict[str, Any]],
        snapshot_at: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        hours: list of {hour: 0-23, day: 0-6 optional, percentage or absolute_count}
        """
        snapshot_at = snapshot_at or _now()
        stored = 0
        for h in hours:
            payload = {
                "snapshot_at": snapshot_at,
                "active_hour": _int(h.get("active_hour", h.get("hour"))),
                "active_day": _int(h.get("active_day", h.get("day"))),
                "percentage": _num(h.get("percentage") or h.get("pct")),
                "absolute_count": _int(h.get("absolute_count") or h.get("count")),
                "metric_type": "active_hours",
            }
            if self.db.store_audience_row(page_id, payload) is not None:
                stored += 1
        return {"status": "success", "stored": stored}

    def profile(self, page_id: str) -> Dict[str, Any]:
        """Aggregate audience intelligence view."""
        demo = self.db.get_audience(page_id, metric_type="demographic", limit=500)
        hours = self.db.get_audience(page_id, metric_type="active_hours", limit=500)

        by_age: Dict[str, float] = defaultdict(float)
        by_gender: Dict[str, float] = defaultdict(float)
        by_country: Dict[str, float] = defaultdict(float)
        by_city: Dict[str, float] = defaultdict(float)

        for r in demo:
            weight = r.get("percentage")
            if weight is None:
                weight = float(r.get("absolute_count") or 0)
            weight = float(weight or 0)
            if r.get("age_bucket"):
                by_age[str(r["age_bucket"])] += weight
            if r.get("gender"):
                by_gender[str(r["gender"]).lower()] += weight
            if r.get("country"):
                by_country[str(r["country"])] += weight
            if r.get("city"):
                by_city[str(r["city"])] += weight

        hour_scores: Dict[int, float] = defaultdict(float)
        for r in hours:
            h = r.get("active_hour")
            if h is None:
                continue
            weight = float(r.get("percentage") or r.get("absolute_count") or 0)
            hour_scores[int(h)] += weight

        top_hours = sorted(hour_scores.items(), key=lambda x: x[1], reverse=True)[:5]
        growth = self.growth_trends(page_id)

        return {
            "page_id": page_id,
            "age": _top_dict(by_age, 10),
            "gender": _top_dict(by_gender, 5),
            "country": _top_dict(by_country, 15),
            "city": _top_dict(by_city, 15),
            "active_hours": [{"hour": h, "score": s} for h, s in top_hours],
            "growth_trends": growth,
            "sample_demographics": len(demo),
            "sample_hours": len(hours),
            "generated_at": _now(),
        }

    def growth_trends(self, page_id: str) -> Dict[str, Any]:
        """Follower / reach growth from profile growth series."""
        out = {}
        for metric in ("followers", "reach", "views", "engagement_rate"):
            series = self.db.get_growth_series(page_id, metric, limit=60)
            if not series:
                out[metric] = {"points": 0}
                continue
            values = [float(p["metric_value"]) for p in series]
            first, last = values[0], values[-1]
            change = last - first
            pct = (change / first * 100.0) if first else None
            out[metric] = {
                "points": len(values),
                "first": first,
                "latest": last,
                "change": change,
                "change_pct": pct,
                "direction": "up" if change > 0 else ("down" if change < 0 else "flat"),
            }
        return out

    def best_posting_windows(self, page_id: str) -> List[Dict[str, Any]]:
        """Combine audience active hours with content performance hours."""
        audience = self.profile(page_id)
        active = {x["hour"]: x["score"] for x in audience.get("active_hours") or []}
        perf = self.db.best_posting_hours(page_id, limit=24)
        combined = []
        seen = set()
        for row in perf:
            h = row.get("hour")
            if h is None:
                continue
            seen.add(int(h))
            combined.append({
                "hour": int(h),
                "avg_revenue": row.get("avg_revenue"),
                "avg_rpm": row.get("avg_rpm"),
                "avg_engagement": row.get("avg_engagement"),
                "audience_score": active.get(int(h), 0),
                "score": float(row.get("avg_revenue") or 0) * 2
                + float(row.get("avg_engagement") or 0) * 10
                + float(active.get(int(h), 0)),
            })
        for h, score in active.items():
            if h not in seen:
                combined.append({
                    "hour": h,
                    "avg_revenue": 0,
                    "avg_rpm": 0,
                    "avg_engagement": 0,
                    "audience_score": score,
                    "score": float(score),
                })
        combined.sort(key=lambda x: x["score"], reverse=True)
        return combined[:8]


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
        return int(v)
    except (TypeError, ValueError):
        return None


def _top_dict(d: Dict[str, float], n: int) -> List[Dict[str, Any]]:
    items = sorted(d.items(), key=lambda x: x[1], reverse=True)[:n]
    total = sum(v for _, v in items) or 1.0
    return [{"key": k, "value": v, "share": v / total} for k, v in items]
