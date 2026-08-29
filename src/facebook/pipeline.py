"""
Facebook Learning Loop
======================
Collect → Normalize → Store → Analyze → Recommend → Optimize

Orchestrates connector collection (optional), intelligence modules,
monetization analysis, recommendations, prompt optimization, and LLM review.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .database import FacebookDatabase, facebook_db
from .intelligence.audience import AudienceIntelligence
from .intelligence.comments import CommentIntelligence
from .intelligence.competitors import CompetitorIntelligence
from .intelligence.content import ContentIntelligence
from .intelligence.monetization import MonetizationIntelligence
from .intelligence.profile import ProfileIntelligence
from .intelligence.prompts import PromptIntelligence
from .intelligence.recommendations import RecommendationEngine
from .llm_analyzer import FacebookLLMAnalyzer
from .network_interceptor import NetworkInterceptor, normalize_json
from .session_manager import FacebookSessionManager, facebook_session_manager

log = logging.getLogger("facebook.pipeline")


class FacebookLearningLoop:
    """End-to-end autonomous learning pipeline for a Facebook page."""

    def __init__(
        self,
        db: Optional[FacebookDatabase] = None,
        session_manager: Optional[FacebookSessionManager] = None,
    ):
        self.db = db or facebook_db
        self.sessions = session_manager or facebook_session_manager
        self.profile = ProfileIntelligence(self.db)
        self.content = ContentIntelligence(self.db)
        self.comments = CommentIntelligence(self.db)
        self.audience = AudienceIntelligence(self.db)
        self.prompts = PromptIntelligence(self.db)
        self.monetization = MonetizationIntelligence(self.db)
        self.recommendations = RecommendationEngine(self.db)
        self.competitors = CompetitorIntelligence(self.db)
        self.llm = FacebookLLMAnalyzer(self.db)

    def run(
        self,
        page_id: str,
        *,
        profile_metrics: Optional[Dict[str, Any]] = None,
        posts: Optional[List[Dict[str, Any]]] = None,
        comments: Optional[List[Dict[str, Any]]] = None,
        audience_rows: Optional[List[Dict[str, Any]]] = None,
        active_hours: Optional[List[Dict[str, Any]]] = None,
        network_captures: Optional[List[Dict[str, Any]]] = None,
        competitors: Optional[List[Dict[str, Any]]] = None,
        use_llm: bool = True,
        backup: bool = True,
    ) -> Dict[str, Any]:
        """
        Execute the full offline/online-agnostic learning loop with provided data.
        Live Playwright collection is available via run_live().
        """
        if backup:
            self.db.backup(label="pre_learning_loop")

        run_id = self.db.start_learning_run(page_id, stage="collect")
        stages: Dict[str, Any] = {}

        try:
            # ── 1. Collect / ingest raw inputs ───────────────────────────────
            self.db.update_learning_run(run_id, stage="collect")
            stages["collect"] = self._stage_collect(
                page_id,
                profile_metrics=profile_metrics,
                posts=posts,
                comments=comments,
                audience_rows=audience_rows,
                active_hours=active_hours,
                network_captures=network_captures,
                competitors=competitors,
            )

            # ── 2. Normalize (content already normalizes on ingest) ──────────
            self.db.update_learning_run(run_id, stage="normalize")
            stages["normalize"] = {
                "status": "success",
                "posts_normalized": stages["collect"].get("posts_stored", 0),
                "comments_normalized": stages["collect"].get("comments_stored", 0),
            }

            # ── 3. Store confirmed via DB counts ─────────────────────────────
            self.db.update_learning_run(run_id, stage="store")
            stages["store"] = {
                "status": "success",
                "content_count": self.db.content_aggregates(page_id).get("post_count", 0),
                "profile_snapshots": len(self.db.get_profile_insights(page_id, limit=1000)),
                "schema_version": self.db.schema_version(),
            }

            # ── 4. Analyze ───────────────────────────────────────────────────
            self.db.update_learning_run(run_id, stage="analyze")
            stages["analyze"] = self._stage_analyze(page_id, use_llm=use_llm)

            # ── 5. Recommend ─────────────────────────────────────────────────
            self.db.update_learning_run(run_id, stage="recommend")
            stages["recommend"] = self.recommendations.generate_daily(page_id)

            # ── 6. Optimize (prompt variants + learning engine bridge) ───────
            self.db.update_learning_run(run_id, stage="optimize")
            stages["optimize"] = self._stage_optimize(page_id, stages)

            self.db.update_learning_run(
                run_id,
                stage="optimize",
                status="completed",
                metrics={
                    "posts": stages["collect"].get("posts_stored", 0),
                    "recommendations": stages["recommend"].get("count", 0),
                },
                finished=True,
            )

            return {
                "status": "success",
                "page_id": page_id,
                "run_id": run_id,
                "stages": stages,
                "finished_at": _now(),
            }
        except Exception as e:
            log.exception("[LearningLoop] run failed")
            self.db.update_learning_run(
                run_id,
                status="failed",
                error=str(e),
                finished=True,
            )
            return {
                "status": "error",
                "page_id": page_id,
                "run_id": run_id,
                "error": str(e),
                "stages": stages,
            }

    async def run_live(
        self,
        page_id: str,
        account_key: str,
        page_slug: str,
        *,
        use_llm: bool = True,
        extra_posts: Optional[List[Dict[str, Any]]] = None,
        extra_comments: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Live collection via Playwright connector, then full learning loop."""
        from .connector import FacebookConnector

        connector = FacebookConnector(db=self.db, session_manager=self.sessions)
        live: Dict[str, Any] = {}
        try:
            live = await connector.collect_page_snapshot(
                account_key=account_key,
                page_slug=page_slug,
                page_id=page_id,
            )
        finally:
            await connector.stop()

        profile_metrics = {}
        for step_name in ("business_suite", "professional_dashboard", "insights"):
            step = (live.get("steps") or {}).get(step_name) or {}
            profile_metrics.update(step.get("metrics") or {})

        posts = list(extra_posts or [])
        posts.extend(((live.get("steps") or {}).get("posts") or {}).get("posts") or [])

        return self.run(
            page_id,
            profile_metrics=profile_metrics or None,
            posts=posts or None,
            comments=extra_comments,
            use_llm=use_llm,
        )

    def _stage_collect(
        self,
        page_id: str,
        *,
        profile_metrics,
        posts,
        comments,
        audience_rows,
        active_hours,
        network_captures,
        competitors,
    ) -> Dict[str, Any]:
        out: Dict[str, Any] = {"status": "success"}

        if profile_metrics:
            out["profile"] = self.profile.ingest_metrics(page_id, profile_metrics, source="learning_loop")

        posts_stored = 0
        if posts:
            res = self.content.ingest_posts(page_id, posts)
            posts_stored = res.get("stored", 0)
            out["posts"] = res
        out["posts_stored"] = posts_stored

        comments_stored = 0
        if comments:
            res = self.comments.ingest_comments(page_id, comments, analyze=True)
            comments_stored = res.get("stored", 0)
            out["comments"] = res
        out["comments_stored"] = comments_stored

        if audience_rows:
            out["audience"] = self.audience.ingest_demographics(page_id, audience_rows)
        if active_hours:
            out["active_hours"] = self.audience.ingest_active_hours(page_id, active_hours)

        if network_captures:
            interceptor = NetworkInterceptor(db=self.db, page_id=page_id)
            captured = 0
            for cap in network_captures:
                r = interceptor.ingest(
                    url=cap.get("url", "https://facebook.com/api/graphql"),
                    body=cap.get("body") or cap.get("normalized") or cap,
                    method=cap.get("method", "GET"),
                    status_code=cap.get("status_code"),
                    resource_type=cap.get("resource_type", "xhr"),
                )
                if r:
                    captured += 1
            # Promote extracted metrics into profile
            metrics = interceptor.extract_metrics_from_captures()
            if metrics:
                self.profile.ingest_metrics(page_id, metrics, source="network")
            out["network"] = {"captured": captured, "metrics": metrics}

        if competitors:
            out["competitors"] = self.competitors.analyze_many(page_id, competitors)

        return out

    def _stage_analyze(self, page_id: str, use_llm: bool = True) -> Dict[str, Any]:
        result = {
            "profile": self.profile.collect_summary(page_id),
            "content": self.content.performance_report(page_id),
            "comments": self.comments.summary(page_id),
            "audience": self.audience.profile(page_id),
            "monetization": self.monetization.analyze(page_id),
            "prompts": {"ranked": self.prompts.rank(page_id, limit=10)},
        }
        if use_llm:
            result["llm"] = {
                "changes": self.llm.explain_changes(page_id),
                "anomalies": self.llm.detect_anomalies(page_id),
                "predictions": self.llm.predict_performance(page_id),
            }
        return result

    def _stage_optimize(self, page_id: str, stages: Dict[str, Any]) -> Dict[str, Any]:
        variants = self.prompts.generate_variants(page_id, n=5, use_llm=True)
        # Bridge to LearningEngine for specialist continuous learning
        learning_recorded = False
        try:
            from src.adapters.learning_engine import learning_engine
            mono = (stages.get("analyze") or {}).get("monetization") or {}
            outcome = "success"
            rpm_delta = mono.get("rpm_delta_pct")
            if rpm_delta is not None and rpm_delta < -10:
                outcome = "partial"
            learning_engine.record_outcome(
                tenant_id="default",
                specialist_id="facebook_specialist",
                task_type="learning_loop",
                outcome=outcome,
                metrics={
                    "rpm": mono.get("rpm_current") or 0,
                    "engagement_rate": (mono.get("aggregates") or {}).get("avg_engagement") or 0,
                    "revenue": (mono.get("aggregates") or {}).get("total_revenue") or 0,
                },
                context={
                    "strategy": "facebook_learning_loop",
                    "page_id": page_id,
                    "rpm_delta_pct": rpm_delta,
                },
                feedback=(mono.get("summary") or "")[:500],
            )
            learning_recorded = True
        except Exception as e:
            log.debug("[LearningLoop] learning_engine bridge skipped: %s", e)

        return {
            "status": "success",
            "prompt_variants": variants,
            "learning_engine_recorded": learning_recorded,
            "posting_windows": self.audience.best_posting_windows(page_id)[:5],
        }


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


facebook_learning_loop = FacebookLearningLoop()
