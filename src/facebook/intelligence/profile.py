"""
Profile Intelligence
====================
Collect and analyze page-level insights: reach, views, followers,
revenue, RPM, earnings, engagement.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ..database import FacebookDatabase, facebook_db

log = logging.getLogger("facebook.intelligence.profile")


class ProfileIntelligence:
    def __init__(self, db: Optional[FacebookDatabase] = None):
        self.db = db or facebook_db

    def ingest_metrics(
        self,
        page_id: str,
        metrics: Dict[str, Any],
        source: str = "manual",
    ) -> Dict[str, Any]:
        """Store a profile metrics snapshot and growth points."""
        payload = {
            "followers": _num(metrics.get("followers") or metrics.get("follower_count")),
            "following": _num(metrics.get("following")),
            "reach": _num(metrics.get("reach")),
            "views": _num(metrics.get("views") or metrics.get("video_views")),
            "impressions": _num(metrics.get("impressions")),
            "revenue": _num(metrics.get("revenue") or metrics.get("earnings") or metrics.get("estimated_earnings")),
            "rpm": _num(metrics.get("rpm")),
            "earnings": _num(metrics.get("earnings") or metrics.get("revenue")),
            "engagement_rate": _num(metrics.get("engagement_rate") or metrics.get("engagement")),
            "snapshot_at": metrics.get("snapshot_at") or _now(),
        }
        # Drop pure Nones for cleanliness but keep structure
        row_id = self.db.store_profile_insight(page_id, {**payload, **metrics}, source=source)
        growth_stored = 0
        for key in ("followers", "reach", "views", "revenue", "rpm", "engagement_rate", "impressions"):
            if payload.get(key) is not None:
                if self.db.store_growth_point(page_id, key, float(payload[key]), recorded_at=payload["snapshot_at"]):
                    growth_stored += 1
        return {
            "status": "success" if row_id else "duplicate",
            "row_id": row_id,
            "metrics": payload,
            "growth_points_stored": growth_stored,
            "source": source,
        }

    def collect_summary(self, page_id: str) -> Dict[str, Any]:
        """Build a current profile intelligence summary from stored history."""
        latest = self.db.latest_profile_insight(page_id)
        history = self.db.get_profile_insights(page_id, limit=30)
        content_agg = self.db.content_aggregates(page_id)

        trends = {}
        for metric in ("followers", "reach", "views", "revenue", "rpm"):
            series = self.db.get_growth_series(page_id, metric, limit=30)
            trends[metric] = self._trend_from_series(series)

        deltas = self._compute_deltas(history)

        return {
            "page_id": page_id,
            "latest": latest,
            "history_count": len(history),
            "content_aggregates": content_agg,
            "trends": trends,
            "deltas": deltas,
            "generated_at": _now(),
        }

    def _compute_deltas(self, history: List[Dict[str, Any]]) -> Dict[str, Any]:
        if len(history) < 2:
            return {}
        newest, older = history[0], history[1]
        deltas = {}
        for key in ("followers", "reach", "views", "revenue", "rpm", "earnings", "engagement_rate"):
            a = _num(newest.get(key))
            b = _num(older.get(key))
            if a is None or b is None:
                continue
            abs_delta = a - b
            pct = ((a - b) / b * 100.0) if b else None
            deltas[key] = {"absolute": abs_delta, "percent": pct, "from": b, "to": a}
        return deltas

    @staticmethod
    def _trend_from_series(series: List[Dict[str, Any]]) -> Dict[str, Any]:
        if not series:
            return {"direction": "unknown", "points": 0}
        values = [float(p["metric_value"]) for p in series]
        if len(values) == 1:
            return {"direction": "flat", "points": 1, "latest": values[0]}
        first, last = values[0], values[-1]
        change = last - first
        pct = (change / first * 100.0) if first else None
        if change > 0:
            direction = "up"
        elif change < 0:
            direction = "down"
        else:
            direction = "flat"
        # Simple slope
        n = len(values)
        x_mean = (n - 1) / 2.0
        y_mean = sum(values) / n
        num = sum((i - x_mean) * (values[i] - y_mean) for i in range(n))
        den = sum((i - x_mean) ** 2 for i in range(n)) or 1.0
        slope = num / den
        return {
            "direction": direction,
            "points": n,
            "latest": last,
            "first": first,
            "change": change,
            "change_pct": pct,
            "slope": slope,
        }


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _num(v: Any) -> Optional[float]:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None
