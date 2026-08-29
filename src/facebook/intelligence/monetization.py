"""
Monetization Intelligence
=========================
Automatically determine:
- Why RPM dropped / increased
- Highest / lowest earning content
- Best posting schedule
- Best content categories
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ..database import FacebookDatabase, facebook_db

log = logging.getLogger("facebook.intelligence.monetization")


class MonetizationIntelligence:
    def __init__(self, db: Optional[FacebookDatabase] = None):
        self.db = db or facebook_db

    def analyze(self, page_id: str) -> Dict[str, Any]:
        posts = self.db.list_content(page_id, limit=2000)
        insights = self.db.get_profile_insights(page_id, limit=30)
        agg = self.db.content_aggregates(page_id)

        rpm_series = self._rpm_series(page_id, posts, insights)
        rpm_current = rpm_series[-1] if rpm_series else None
        rpm_previous = rpm_series[-2] if len(rpm_series) >= 2 else None
        rpm_delta_pct = None
        if rpm_current is not None and rpm_previous not in (None, 0):
            rpm_delta_pct = ((rpm_current - rpm_previous) / rpm_previous) * 100.0

        drop_reasons, rise_reasons = self._explain_rpm_change(page_id, posts, insights, rpm_delta_pct)

        highest = self._extreme_post(posts, "revenue", reverse=True)
        lowest = self._extreme_post(posts, "revenue", reverse=False)
        # Prefer non-zero lowest among posts that have revenue data
        revenue_posts = [p for p in posts if p.get("revenue") is not None]
        if revenue_posts:
            highest = max(revenue_posts, key=lambda p: float(p.get("revenue") or 0))
            lowest = min(revenue_posts, key=lambda p: float(p.get("revenue") or 0))

        best_hours = self.db.best_posting_hours(page_id, limit=5)
        best_categories = self.db.content_by_category_proxy(page_id)[:5]

        summary = self._build_summary(
            rpm_current, rpm_previous, rpm_delta_pct,
            drop_reasons, rise_reasons, highest, lowest, best_hours, best_categories, agg,
        )

        analysis = {
            "analysis_at": _now(),
            "rpm_current": rpm_current,
            "rpm_previous": rpm_previous,
            "rpm_delta_pct": rpm_delta_pct,
            "rpm_drop_reasons": drop_reasons,
            "rpm_rise_reasons": rise_reasons,
            "highest_earning_post_id": (highest or {}).get("post_id"),
            "lowest_earning_post_id": (lowest or {}).get("post_id"),
            "highest_earning": highest,
            "lowest_earning": lowest,
            "best_hours": best_hours,
            "best_categories": best_categories,
            "aggregates": agg,
            "summary": summary,
        }
        row_id = self.db.store_monetization(page_id, analysis)
        analysis["row_id"] = row_id
        analysis["status"] = "success"
        analysis["page_id"] = page_id
        return analysis

    def _rpm_series(
        self,
        page_id: str,
        posts: List[Dict[str, Any]],
        insights: List[Dict[str, Any]],
    ) -> List[float]:
        series = []
        # From profile insights (newest first → reverse for chrono)
        for ins in reversed(insights):
            if ins.get("rpm") is not None:
                series.append(float(ins["rpm"]))
        growth = self.db.get_growth_series(page_id, "rpm", limit=30)
        if growth:
            series = [float(g["metric_value"]) for g in growth]
        # Fallback: rolling avg from posts by date
        if len(series) < 2 and posts:
            dated = [p for p in posts if p.get("rpm") is not None and p.get("publish_date")]
            dated.sort(key=lambda p: str(p.get("publish_date")))
            # chunk into windows
            if dated:
                window = max(1, len(dated) // 4)
                for i in range(0, len(dated), window):
                    chunk = dated[i:i + window]
                    vals = [float(p["rpm"]) for p in chunk]
                    series.append(sum(vals) / len(vals))
        return series

    def _explain_rpm_change(
        self,
        page_id: str,
        posts: List[Dict[str, Any]],
        insights: List[Dict[str, Any]],
        rpm_delta_pct: Optional[float],
    ) -> tuple:
        drop: List[str] = []
        rise: List[str] = []
        if rpm_delta_pct is None:
            return (
                ["Insufficient historical RPM data to explain changes."],
                ["Insufficient historical RPM data to explain changes."],
            )

        # Split posts into recent vs older half by publish_date
        dated = [p for p in posts if p.get("publish_date")]
        dated.sort(key=lambda p: str(p.get("publish_date")))
        if len(dated) >= 4:
            mid = len(dated) // 2
            older, recent = dated[:mid], dated[mid:]
            def avg(field, rows):
                vals = [float(r[field]) for r in rows if r.get(field) is not None]
                return sum(vals) / len(vals) if vals else None

            for field, label in (
                ("views", "average views"),
                ("reach", "average reach"),
                ("engagement_rate", "engagement rate"),
                ("revenue", "average revenue per post"),
            ):
                a, b = avg(field, older), avg(field, recent)
                if a is None or b is None or a == 0:
                    continue
                change = (b - a) / a * 100.0
                if change < -10:
                    drop.append(f"{label} fell {abs(change):.1f}% in recent posts vs earlier period")
                elif change > 10:
                    rise.append(f"{label} rose {change:.1f}% in recent posts vs earlier period")

            # Category mix shift
            def top_cat(rows):
                from collections import Counter
                c = Counter(
                    (r.get("style") or r.get("image_type") or r.get("post_type") or "unknown")
                    for r in rows
                )
                return c.most_common(1)[0][0] if c else None

            oc, rc = top_cat(older), top_cat(recent)
            if oc and rc and oc != rc:
                msg = f"Dominant content category shifted from '{oc}' to '{rc}'"
                if rpm_delta_pct < 0:
                    drop.append(msg)
                else:
                    rise.append(msg)

            # Posting hour shift
            def top_hour(rows):
                from collections import Counter
                c = Counter(r.get("publish_hour") for r in rows if r.get("publish_hour") is not None)
                return c.most_common(1)[0][0] if c else None

            oh, rh = top_hour(older), top_hour(recent)
            if oh is not None and rh is not None and oh != rh:
                msg = f"Primary posting hour shifted from {oh}:00 to {rh}:00"
                if rpm_delta_pct < 0:
                    drop.append(msg + " (may miss peak audience)")
                else:
                    rise.append(msg + " (better audience alignment)")

        # Profile-level deltas
        if len(insights) >= 2:
            n, o = insights[0], insights[1]
            for key, label in (("followers", "followers"), ("reach", "page reach"), ("views", "page views")):
                a, b = o.get(key), n.get(key)
                if a and b:
                    pct = (float(b) - float(a)) / float(a) * 100.0
                    if pct < -5:
                        drop.append(f"Page {label} declined {abs(pct):.1f}% between latest snapshots")
                    elif pct > 5:
                        rise.append(f"Page {label} grew {pct:.1f}% between latest snapshots")

        if rpm_delta_pct < -1 and not drop:
            drop.append(f"RPM decreased {abs(rpm_delta_pct):.1f}% without a single dominant factor; review content mix and audience quality.")
        if rpm_delta_pct > 1 and not rise:
            rise.append(f"RPM increased {rpm_delta_pct:.1f}%; sustained by overall content performance improvements.")

        if rpm_delta_pct >= 0:
            # Still report potential risks
            if not drop:
                drop.append("No significant RPM drop detected in the latest window.")
        if rpm_delta_pct <= 0:
            if not rise:
                rise.append("No significant RPM increase detected in the latest window.")

        return drop, rise

    @staticmethod
    def _extreme_post(posts: List[Dict[str, Any]], field: str, reverse: bool) -> Optional[Dict[str, Any]]:
        eligible = [p for p in posts if p.get(field) is not None]
        if not eligible:
            return None
        return sorted(eligible, key=lambda p: float(p.get(field) or 0), reverse=reverse)[0]

    @staticmethod
    def _build_summary(
        rpm_current, rpm_previous, rpm_delta_pct,
        drop_reasons, rise_reasons, highest, lowest, best_hours, best_categories, agg,
    ) -> str:
        parts = []
        if rpm_current is not None:
            parts.append(f"Current RPM: {rpm_current:.4f}")
        if rpm_delta_pct is not None:
            direction = "up" if rpm_delta_pct > 0 else ("down" if rpm_delta_pct < 0 else "flat")
            parts.append(f"RPM trend: {direction} ({rpm_delta_pct:+.1f}%)")
        if highest:
            parts.append(
                f"Highest earner: post {highest.get('post_id')} "
                f"(revenue={highest.get('revenue')}, rpm={highest.get('rpm')})"
            )
        if lowest:
            parts.append(
                f"Lowest earner: post {lowest.get('post_id')} "
                f"(revenue={lowest.get('revenue')}, rpm={lowest.get('rpm')})"
            )
        if best_hours:
            hours = ", ".join(f"{h.get('hour')}:00" for h in best_hours[:3])
            parts.append(f"Best posting hours: {hours}")
        if best_categories:
            cats = ", ".join(str(c.get("category")) for c in best_categories[:3])
            parts.append(f"Best categories: {cats}")
        if agg:
            parts.append(
                f"Totals — posts={agg.get('post_count')}, revenue={agg.get('total_revenue')}, "
                f"avg_rpm={agg.get('avg_rpm')}"
            )
        if rpm_delta_pct is not None and rpm_delta_pct < 0 and drop_reasons:
            parts.append("Drop drivers: " + "; ".join(drop_reasons[:3]))
        if rpm_delta_pct is not None and rpm_delta_pct > 0 and rise_reasons:
            parts.append("Rise drivers: " + "; ".join(rise_reasons[:3]))
        return " | ".join(parts) if parts else "No monetization data available yet."


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
