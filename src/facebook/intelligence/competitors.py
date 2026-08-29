"""
Competitor Intelligence
=======================
Analyze public competitor pages, detect trends, compare performance patterns,
and generate recommendations WITHOUT copying content.
"""

from __future__ import annotations

import logging
import re
from collections import Counter
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from ..database import FacebookDatabase, facebook_db
from .content import ContentIntelligence

log = logging.getLogger("facebook.intelligence.competitors")

_HASHTAG_RE = re.compile(r"#[\wáéíóúñüÁÉÍÓÚÑÜ]+", re.U)
_STOP = {
    "the", "and", "for", "with", "this", "that", "from", "your", "about",
    "que", "de", "la", "el", "en", "los", "las", "del", "una", "por", "con", "para",
}


class CompetitorIntelligence:
    def __init__(self, db: Optional[FacebookDatabase] = None):
        self.db = db or facebook_db
        self.content = ContentIntelligence(self.db)

    def ingest_public_snapshot(
        self,
        page_id: str,
        competitor: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Store a competitor snapshot from public data (DOM scrape, research, manual).

        competitor keys:
          competitor_id, name, url, followers, posts (list of public post dicts),
          avg_engagement (optional)
        """
        competitor_id = str(
            competitor.get("competitor_id")
            or competitor.get("id")
            or _slug_from_url(competitor.get("url") or competitor.get("name") or "unknown")
        )
        posts = competitor.get("posts") or competitor.get("sample_posts") or []
        topics, hashtags, post_types, hours = self._extract_signals(posts)
        avg_eng = competitor.get("avg_engagement")
        if avg_eng is None and posts:
            eng_vals = [
                float(p.get("engagement_rate") or p.get("likes") or 0)
                for p in posts
            ]
            avg_eng = sum(eng_vals) / len(eng_vals) if eng_vals else 0.0

        trend_signals = self._detect_trends(topics, hashtags, post_types, hours)
        comparison = self.compare_to_own(page_id, {
            "followers": competitor.get("followers"),
            "avg_engagement": avg_eng,
            "top_topics": topics[:10],
            "post_types": post_types,
            "best_hours": hours,
        })
        recommendations = self._recommendations_from_comparison(comparison, trend_signals)

        payload = {
            "competitor_id": competitor_id,
            "competitor_name": competitor.get("competitor_name") or competitor.get("name"),
            "competitor_url": competitor.get("competitor_url") or competitor.get("url"),
            "followers": competitor.get("followers"),
            "posts_sampled": len(posts),
            "avg_engagement": avg_eng,
            "top_topics": topics[:15],
            "trend_signals": trend_signals,
            "comparison": comparison,
            "recommendations": recommendations,
            "snapshot_at": competitor.get("snapshot_at") or _now(),
            "raw_posts_count": len(posts),
        }
        row_id = self.db.store_competitor(page_id, payload)
        return {
            "status": "success" if row_id else "duplicate",
            "row_id": row_id,
            "competitor_id": competitor_id,
            "analysis": payload,
        }

    def analyze_many(self, page_id: str, competitors: List[Dict[str, Any]]) -> Dict[str, Any]:
        results = [self.ingest_public_snapshot(page_id, c) for c in competitors]
        overview = self.portfolio_overview(page_id)
        return {"status": "success", "analyzed": len(results), "results": results, "overview": overview}

    def compare_to_own(self, page_id: str, competitor_stats: Dict[str, Any]) -> Dict[str, Any]:
        own_posts = self.db.list_content(page_id, limit=200)
        own_agg = self.db.content_aggregates(page_id)
        own_hours = self.db.best_posting_hours(page_id, limit=5)
        own_latest = self.db.latest_profile_insight(page_id) or {}

        own_topics = Counter()
        for p in own_posts:
            for tag in (p.get("hashtags") or []):
                own_topics[str(tag).lower()] += 1
            style = p.get("style") or p.get("post_type")
            if style:
                own_topics[str(style).lower()] += 1

        comp_topics = {
            str(t.get("topic") if isinstance(t, dict) else t).lower(): (
                t.get("count", 1) if isinstance(t, dict) else 1
            )
            for t in (competitor_stats.get("top_topics") or [])
        }

        shared = set(own_topics) & set(comp_topics)
        only_comp = set(comp_topics) - set(own_topics)

        followers_gap = None
        if competitor_stats.get("followers") is not None and own_latest.get("followers") is not None:
            followers_gap = float(competitor_stats["followers"]) - float(own_latest["followers"])

        eng_gap = None
        if competitor_stats.get("avg_engagement") is not None and own_agg.get("avg_engagement") is not None:
            eng_gap = float(competitor_stats["avg_engagement"]) - float(own_agg["avg_engagement"])

        return {
            "followers_own": own_latest.get("followers"),
            "followers_competitor": competitor_stats.get("followers"),
            "followers_gap": followers_gap,
            "engagement_own": own_agg.get("avg_engagement"),
            "engagement_competitor": competitor_stats.get("avg_engagement"),
            "engagement_gap": eng_gap,
            "shared_topics": sorted(shared)[:20],
            "competitor_only_topics": sorted(only_comp)[:20],
            "own_best_hours": own_hours,
            "competitor_hours": competitor_stats.get("best_hours") or [],
            "own_post_count": own_agg.get("post_count"),
        }

    def portfolio_overview(self, page_id: str) -> Dict[str, Any]:
        rows = self.db.list_competitors(page_id, limit=50)
        if not rows:
            return {"competitors": 0, "trends": [], "recommendations": []}

        all_trends: Counter = Counter()
        all_recs: Counter = Counter()
        for r in rows:
            for t in r.get("trend_signals") or []:
                key = t if isinstance(t, str) else t.get("signal") or str(t)
                all_trends[key] += 1
            for rec in r.get("recommendations") or []:
                key = rec if isinstance(rec, str) else rec.get("title") or str(rec)
                all_recs[key] += 1

        return {
            "competitors": len({r.get("competitor_id") for r in rows}),
            "snapshots": len(rows),
            "common_trends": [{"signal": k, "count": v} for k, v in all_trends.most_common(10)],
            "common_recommendations": [{"text": k, "count": v} for k, v in all_recs.most_common(10)],
            "generated_at": _now(),
        }

    async def fetch_public_page_via_browser(
        self,
        page_id: str,
        competitor_url: str,
        connector=None,
    ) -> Dict[str, Any]:
        """
        Optional live public scrape using FacebookConnector / Playwright page.
        Only public surface data — no private insights.
        """
        from ..connector import FacebookConnector

        own_connector = connector is None
        connector = connector or FacebookConnector(db=self.db)
        try:
            if connector.page is None:
                # Public pages often work without login; still start browser
                start = await connector.start(account_key=f"public_{page_id}")
                if start.get("status") == "error":
                    return start

            await connector._retry_goto(competitor_url)
            await connector.page.wait_for_timeout(2000)
            await connector.infinite_scroll(max_scrolls=6)

            data = await connector.page.evaluate(
                """() => {
                    const name = document.title || '';
                    let followers = null;
                    const body = document.body ? document.body.innerText : '';
                    const m = body.match(/([\\d.,]+[KkMm]?)\\s*(followers|seguidores|likes|me gusta)/i);
                    if (m) followers = m[1];
                    const posts = [];
                    document.querySelectorAll('[role="article"]').forEach((el, idx) => {
                        const text = (el.innerText || '').slice(0, 1500);
                        posts.push({ post_id: 'pub_' + idx, caption: text, post_type: 'post' });
                    });
                    return { name, followers_raw: followers, body_snippet: body.slice(0, 500), posts };
                }"""
            )
            followers = _parse_count(data.get("followers_raw"))
            snapshot = {
                "competitor_id": _slug_from_url(competitor_url),
                "name": data.get("name"),
                "url": competitor_url,
                "followers": followers,
                "posts": data.get("posts") or [],
            }
            return self.ingest_public_snapshot(page_id, snapshot)
        except Exception as e:
            log.exception("[CompetitorIntel] public fetch failed")
            return {"status": "error", "message": str(e)}
        finally:
            if own_connector:
                await connector.stop()

    # ── Internals ────────────────────────────────────────────────────────────

    def _extract_signals(self, posts: List[Dict[str, Any]]):
        topic_counter: Counter = Counter()
        hashtag_counter: Counter = Counter()
        type_counter: Counter = Counter()
        hour_counter: Counter = Counter()

        for p in posts:
            caption = p.get("caption") or p.get("message") or p.get("text") or ""
            for tag in _HASHTAG_RE.findall(caption):
                hashtag_counter[tag.lower()] += 1
                topic_counter[tag.lower()] += 1
            for tok in re.findall(r"[a-záéíóúñü]{4,}", caption.lower()):
                if tok not in _STOP:
                    topic_counter[tok] += 1
            type_counter[str(p.get("post_type") or p.get("type") or "post")] += 1
            hour = p.get("publish_hour")
            if hour is not None:
                hour_counter[int(hour)] += 1

        topics = [{"topic": t, "count": c} for t, c in topic_counter.most_common(20)]
        hashtags = [{"tag": t, "count": c} for t, c in hashtag_counter.most_common(15)]
        post_types = [{"type": t, "count": c} for t, c in type_counter.most_common()]
        hours = [{"hour": h, "count": c} for h, c in hour_counter.most_common(5)]
        return topics, hashtags, post_types, hours

    def _detect_trends(self, topics, hashtags, post_types, hours) -> List[str]:
        signals = []
        if post_types:
            top_type = post_types[0]["type"]
            signals.append(f"Dominant format: {top_type}")
            if top_type == "reel":
                signals.append("Reels-heavy strategy detected")
        if hashtags:
            top_tags = ", ".join(h["tag"] for h in hashtags[:5])
            signals.append(f"Recurring hashtags: {top_tags}")
        if topics:
            top_topics = ", ".join(
                (t["topic"] if isinstance(t, dict) else str(t)) for t in topics[:5]
            )
            signals.append(f"Topic focus: {top_topics}")
        if hours:
            hs = ", ".join(f"{h['hour']}:00" for h in hours[:3])
            signals.append(f"Competitor posting hours: {hs}")
        return signals

    def _recommendations_from_comparison(
        self,
        comparison: Dict[str, Any],
        trend_signals: List[str],
    ) -> List[str]:
        recs = []
        # Never suggest copying captions/content — only patterns
        only = comparison.get("competitor_only_topics") or []
        if only:
            recs.append(
                f"Explore original content angles around themes your audience overlaps with competitors on sparingly; "
                f"gap themes observed: {', '.join(list(only)[:5])} — create ORIGINAL takes, do not copy."
            )
        eng_gap = comparison.get("engagement_gap")
        if eng_gap is not None and eng_gap > 0:
            recs.append(
                "Competitor shows higher average engagement — improve hooks in the first 3 seconds of reels "
                "and strengthen CTAs without imitating their creative."
            )
        elif eng_gap is not None and eng_gap < 0:
            recs.append(
                "Your engagement outperforms this competitor — maintain cadence and document winning formats in content intelligence."
            )
        followers_gap = comparison.get("followers_gap")
        if followers_gap is not None and followers_gap > 0:
            recs.append(
                "Competitor has a larger audience — prioritize consistent publishing frequency and collaborations; "
                "do not mirror their posts."
            )
        for sig in trend_signals:
            if "Reels-heavy" in sig:
                recs.append("Industry trend favors short-form video — increase original reel production.")
            if "posting hours" in sig.lower():
                recs.append(
                    "Test posting near competitor peak hours only if they align with YOUR audience active hours."
                )
        if not recs:
            recs.append("Continue monitoring; insufficient differential signal for action.")
        return recs


def _slug_from_url(url_or_name: str) -> str:
    if not url_or_name:
        return "unknown"
    if "://" in url_or_name:
        path = urlparse(url_or_name).path.strip("/")
        return (path.split("/")[0] if path else "unknown") or "unknown"
    return re.sub(r"[^a-zA-Z0-9_-]+", "_", url_or_name)[:64]


def _parse_count(raw: Any) -> Optional[float]:
    if raw is None:
        return None
    from ..ocr_extractor import parse_number
    return parse_number(str(raw))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
