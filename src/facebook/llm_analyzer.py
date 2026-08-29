"""
Facebook LLM Analyzer
=====================
Integrates with the existing local LLM (CapabilitySelector / Ollama) to:
- Analyze historical data
- Explain performance changes
- Predict future performance
- Detect anomalies
- Recommend improvements
"""

from __future__ import annotations

import json
import logging
import re
import statistics
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .database import FacebookDatabase, facebook_db
from .intelligence.content import ContentIntelligence
from .intelligence.monetization import MonetizationIntelligence
from .intelligence.profile import ProfileIntelligence

log = logging.getLogger("facebook.llm_analyzer")


class FacebookLLMAnalyzer:
    def __init__(self, db: Optional[FacebookDatabase] = None):
        self.db = db or facebook_db
        self.profile = ProfileIntelligence(self.db)
        self.content = ContentIntelligence(self.db)
        self.monetization = MonetizationIntelligence(self.db)

    def _generate(self, prompt: str, system: str) -> str:
        try:
            from src.providers.capability_selector import capability_selector
            return capability_selector.generate(
                prompt=prompt,
                capability="reasoning",
                system_prompt=system,
            )
        except Exception as e:
            log.warning("[LLMAnalyzer] generate failed: %s", e)
            return ""

    def build_context(self, page_id: str) -> Dict[str, Any]:
        return {
            "profile": self.profile.collect_summary(page_id),
            "content": self.content.performance_report(page_id),
            "monetization": self.monetization.analyze(page_id),
            "aggregates": self.db.content_aggregates(page_id),
            "recent_posts": self.db.list_content(page_id, limit=15),
        }

    def analyze_history(self, page_id: str) -> Dict[str, Any]:
        ctx = self.build_context(page_id)
        deterministic = self._deterministic_analysis(page_id, ctx)
        prompt = (
            "Analiza el historial de rendimiento de esta página de Facebook.\n"
            f"DATOS (JSON):\n{json.dumps(_shrink(ctx), ensure_ascii=False, default=str)[:6000]}\n\n"
            "Entrega: 1) Diagnóstico 2) Cambios clave 3) Riesgos 4) Oportunidades."
        )
        llm_text = self._generate(
            prompt,
            "Eres un analista senior de monetización de Meta/Facebook Reels y Pages.",
        )
        return {
            "status": "success",
            "page_id": page_id,
            "deterministic": deterministic,
            "llm_analysis": llm_text or deterministic.get("summary"),
            "generated_at": _now(),
        }

    def explain_changes(self, page_id: str) -> Dict[str, Any]:
        mono = self.monetization.analyze(page_id)
        profile = self.profile.collect_summary(page_id)
        base = {
            "rpm_delta_pct": mono.get("rpm_delta_pct"),
            "drop_reasons": mono.get("rpm_drop_reasons"),
            "rise_reasons": mono.get("rpm_rise_reasons"),
            "profile_deltas": profile.get("deltas"),
            "summary": mono.get("summary"),
        }
        prompt = (
            "Explica los cambios de rendimiento de forma clara y accionable.\n"
            f"{json.dumps(base, ensure_ascii=False, default=str)}\n"
            "Prioriza causas probables sobre especulación."
        )
        llm_text = self._generate(prompt, "Eres un growth analyst de redes sociales.")
        return {
            "status": "success",
            "page_id": page_id,
            "explanation": llm_text or mono.get("summary"),
            "structured": base,
            "generated_at": _now(),
        }

    def predict_performance(self, page_id: str, horizon_days: int = 7) -> Dict[str, Any]:
        """Simple trend extrapolation + optional LLM narrative."""
        predictions = {}
        for metric in ("followers", "reach", "views", "revenue", "rpm"):
            series = self.db.get_growth_series(page_id, metric, limit=30)
            values = [float(p["metric_value"]) for p in series]
            if len(values) < 2:
                # fallback from content
                posts = self.db.list_content(page_id, limit=30)
                if metric in ("revenue", "rpm", "reach", "views"):
                    values = [float(p[metric]) for p in posts if p.get(metric) is not None]
                    values = list(reversed(values))  # rough
            pred = _linear_forecast(values, steps=max(1, horizon_days // 1))
            predictions[metric] = pred

        prompt = (
            f"Con base en estas predicciones a {horizon_days} días, resume el outlook:\n"
            f"{json.dumps(predictions, default=str)}\n"
            "Sé conservador y menciona incertidumbre."
        )
        llm_text = self._generate(prompt, "Eres un forecasting analyst de social media.")
        return {
            "status": "success",
            "page_id": page_id,
            "horizon_days": horizon_days,
            "predictions": predictions,
            "narrative": llm_text,
            "generated_at": _now(),
        }

    def detect_anomalies(self, page_id: str, z_threshold: float = 2.5) -> Dict[str, Any]:
        anomalies: List[Dict[str, Any]] = []
        posts = self.db.list_content(page_id, limit=500)
        for field in ("revenue", "rpm", "reach", "views", "engagement_rate"):
            vals = [float(p[field]) for p in posts if p.get(field) is not None]
            if len(vals) < 5:
                continue
            mean = statistics.mean(vals)
            stdev = statistics.pstdev(vals) or 1e-9
            for p in posts:
                if p.get(field) is None:
                    continue
                v = float(p[field])
                z = (v - mean) / stdev
                if abs(z) >= z_threshold:
                    anomalies.append({
                        "post_id": p.get("post_id"),
                        "field": field,
                        "value": v,
                        "z_score": round(z, 3),
                        "direction": "high" if z > 0 else "low",
                        "mean": mean,
                    })

        # Growth series spikes
        for metric in ("followers", "rpm", "revenue"):
            series = self.db.get_growth_series(page_id, metric, limit=60)
            values = [float(p["metric_value"]) for p in series]
            if len(values) < 5:
                continue
            mean = statistics.mean(values)
            stdev = statistics.pstdev(values) or 1e-9
            for i, p in enumerate(series):
                z = (values[i] - mean) / stdev
                if abs(z) >= z_threshold:
                    anomalies.append({
                        "metric": metric,
                        "recorded_at": p.get("recorded_at"),
                        "value": values[i],
                        "z_score": round(z, 3),
                        "direction": "high" if z > 0 else "low",
                        "type": "time_series",
                    })

        anomalies.sort(key=lambda a: abs(a.get("z_score", 0)), reverse=True)
        prompt = (
            "Detecta y explica anomalías de rendimiento:\n"
            f"{json.dumps(anomalies[:15], default=str)}\n"
            "Indica cuáles requieren investigación inmediata."
        )
        llm_text = self._generate(prompt, "Eres un anomaly detection analyst.")
        return {
            "status": "success",
            "page_id": page_id,
            "count": len(anomalies),
            "anomalies": anomalies[:50],
            "llm_review": llm_text,
            "generated_at": _now(),
        }

    def recommend_improvements(self, page_id: str) -> Dict[str, Any]:
        from .intelligence.recommendations import RecommendationEngine
        engine = RecommendationEngine(self.db)
        daily = engine.generate_daily(page_id)
        ctx = {
            "recommendations": daily.get("recommendations"),
            "monetization_summary": (self.monetization.analyze(page_id) or {}).get("summary"),
        }
        prompt = (
            "Prioriza y refina estas recomendaciones de Facebook para el creador:\n"
            f"{json.dumps(ctx, ensure_ascii=False, default=str)[:5000]}\n"
            "Devuelve un plan de acción de 5 puntos para los próximos 7 días."
        )
        llm_text = self._generate(prompt, "Eres un strategist de crecimiento orgánico en Meta.")
        return {
            "status": "success",
            "page_id": page_id,
            "structured_recommendations": daily.get("recommendations"),
            "action_plan": llm_text,
            "generated_at": _now(),
        }

    def full_report(self, page_id: str) -> Dict[str, Any]:
        return {
            "status": "success",
            "page_id": page_id,
            "history": self.analyze_history(page_id),
            "changes": self.explain_changes(page_id),
            "predictions": self.predict_performance(page_id),
            "anomalies": self.detect_anomalies(page_id),
            "improvements": self.recommend_improvements(page_id),
            "generated_at": _now(),
        }

    def _deterministic_analysis(self, page_id: str, ctx: Dict[str, Any]) -> Dict[str, Any]:
        mono = ctx.get("monetization") or {}
        profile = ctx.get("profile") or {}
        agg = ctx.get("aggregates") or {}
        summary_parts = [
            mono.get("summary") or "",
            f"Posts tracked: {agg.get('post_count', 0)}",
            f"Total revenue: {agg.get('total_revenue', 0)}",
        ]
        trends = profile.get("trends") or {}
        for k, t in trends.items():
            if isinstance(t, dict) and t.get("direction"):
                summary_parts.append(f"{k} trend: {t['direction']}")
        return {
            "summary": " | ".join(p for p in summary_parts if p),
            "rpm_delta_pct": mono.get("rpm_delta_pct"),
            "trends": trends,
            "deltas": profile.get("deltas"),
        }


def _linear_forecast(values: List[float], steps: int = 7) -> Dict[str, Any]:
    if not values:
        return {"status": "insufficient_data", "forecast": []}
    if len(values) == 1:
        return {
            "status": "flat",
            "latest": values[0],
            "forecast": [values[0]] * steps,
            "slope": 0.0,
        }
    n = len(values)
    x_mean = (n - 1) / 2.0
    y_mean = sum(values) / n
    num = sum((i - x_mean) * (values[i] - y_mean) for i in range(n))
    den = sum((i - x_mean) ** 2 for i in range(n)) or 1.0
    slope = num / den
    intercept = y_mean - slope * x_mean
    forecast = []
    for s in range(1, steps + 1):
        forecast.append(round(intercept + slope * (n - 1 + s), 4))
    return {
        "status": "ok",
        "latest": values[-1],
        "slope": round(slope, 6),
        "forecast": forecast,
        "points_used": n,
    }


def _shrink(obj: Any, max_list: int = 8) -> Any:
    if isinstance(obj, list):
        return [_shrink(x, max_list) for x in obj[:max_list]]
    if isinstance(obj, dict):
        return {k: _shrink(v, max_list) for k, v in obj.items()}
    if isinstance(obj, str) and len(obj) > 300:
        return obj[:300] + "…"
    return obj


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


facebook_llm = FacebookLLMAnalyzer()
