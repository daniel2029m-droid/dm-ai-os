"""
Tests de Fase 17 — Aprendizaje Continuo (LearningEngine)
=========================================================
Valida:
1. Registro de outcomes por especialista+tenant
2. Cálculo de score delta y rankings de estrategia
3. Recuperación de contexto de experiencia
4. Resumen de rendimiento
5. Aislamiento de aprendizaje entre tenants
6. Historial de fallos para retry logic

Ejecutar: python -m pytest tests/test_fase17_learning.py -v
"""

import pytest
from pathlib import Path


class TestOutcomeRecording:
    """Valida el registro de outcomes de ejecución."""

    def test_record_success_outcome(self, tmp_path):
        from src.adapters.learning_engine import LearningEngine
        engine = LearningEngine(db_path=tmp_path / "learning.db")

        engine.record_outcome(
            tenant_id="t1",
            specialist_id="facebook_specialist",
            task_type="content_creation",
            outcome="success",
            metrics={"engagement_rate": 0.08, "ctr": 0.03},
            context={"niche": "ropa", "strategy": "viral_hook"},
        )

        summary = engine.get_performance_summary("t1", "facebook_specialist")
        assert summary["total_executions"] == 1
        assert summary["outcomes"]["success"] == 1

    def test_record_failure_outcome(self, tmp_path):
        from src.adapters.learning_engine import LearningEngine
        engine = LearningEngine(db_path=tmp_path / "learning.db")

        engine.record_outcome(
            tenant_id="t1",
            specialist_id="tiktok_specialist",
            task_type="video_creation",
            outcome="failure",
        )

        summary = engine.get_performance_summary("t1", "tiktok_specialist")
        assert summary["outcomes"].get("failure", 0) == 1

    def test_record_multiple_outcomes(self, tmp_path):
        from src.adapters.learning_engine import LearningEngine
        engine = LearningEngine(db_path=tmp_path / "learning.db")

        for i in range(5):
            engine.record_outcome(
                tenant_id="t1",
                specialist_id="instagram_specialist",
                task_type="reel_creation",
                outcome="success" if i < 4 else "failure",
            )

        summary = engine.get_performance_summary("t1", "instagram_specialist")
        assert summary["total_executions"] == 5
        assert summary["outcomes"]["success"] == 4
        assert summary["outcomes"]["failure"] == 1

    def test_feedback_field_stored(self, tmp_path):
        from src.adapters.learning_engine import LearningEngine
        import sqlite3

        engine = LearningEngine(db_path=tmp_path / "learning.db")
        engine.record_outcome(
            tenant_id="t1",
            specialist_id="seo_specialist",
            task_type="keyword_research",
            outcome="success",
            feedback="Excelente resultado, +40% tráfico orgánico",
        )

        with sqlite3.connect(str(tmp_path / "learning.db")) as conn:
            row = conn.execute(
                "SELECT feedback FROM experiences WHERE tenant_id='t1'"
            ).fetchone()
        assert row is not None
        assert "tráfico" in row[0]


class TestStrategyRankings:
    """Valida el ranking de estrategias basado en experiencia."""

    def test_best_strategy_emerges_after_samples(self, tmp_path):
        from src.adapters.learning_engine import LearningEngine
        engine = LearningEngine(db_path=tmp_path / "learning.db")

        # Record winning strategy
        for _ in range(3):
            engine.record_outcome(
                tenant_id="t1",
                specialist_id="content_specialist",
                task_type="blog",
                outcome="success",
                metrics={"ctr": 0.05, "engagement_rate": 0.1},
                context={"strategy": "storytelling"},
            )

        # Record losing strategy
        for _ in range(3):
            engine.record_outcome(
                tenant_id="t1",
                specialist_id="content_specialist",
                task_type="blog",
                outcome="failure",
                metrics={},
                context={"strategy": "generic_post"},
            )

        best = engine.get_best_strategy("t1", "content_specialist")
        assert best == "storytelling"

    def test_no_best_strategy_before_2_samples(self, tmp_path):
        from src.adapters.learning_engine import LearningEngine
        engine = LearningEngine(db_path=tmp_path / "learning.db")

        engine.record_outcome(
            tenant_id="t1",
            specialist_id="new_specialist",
            task_type="test",
            outcome="success",
            context={"strategy": "only_one_sample"},
        )

        # Should return None — need at least 2 samples
        best = engine.get_best_strategy("t1", "new_specialist")
        assert best is None


class TestExperienceContext:
    """Valida la generación de contexto de experiencia para inyección en prompts."""

    def test_experience_context_no_history(self, tmp_path):
        from src.adapters.learning_engine import LearningEngine
        engine = LearningEngine(db_path=tmp_path / "learning.db")

        ctx = engine.get_experience_context("new_tenant", "facebook_specialist")
        assert "primera" in ctx.lower() or "sin experiencia" in ctx.lower()

    def test_experience_context_with_history(self, tmp_path):
        from src.adapters.learning_engine import LearningEngine
        engine = LearningEngine(db_path=tmp_path / "learning.db")

        engine.record_outcome("t1", "youtube_specialist", "seo", "success",
                              metrics={"ctr": 0.12}, context={"niche": "finanzas"})
        engine.record_outcome("t1", "youtube_specialist", "thumbnail", "failure")

        ctx = engine.get_experience_context("t1", "youtube_specialist")
        assert "EXPERIENCIA" in ctx
        assert "success" in ctx.lower() or "SUCCESS" in ctx


class TestTenantLearningIsolation:
    """Verifica que el aprendizaje no se filtre entre tenants."""

    def test_outcomes_isolated_between_tenants(self, tmp_path):
        from src.adapters.learning_engine import LearningEngine
        engine = LearningEngine(db_path=tmp_path / "learning.db")

        engine.record_outcome("empresa_a", "facebook_specialist", "post", "success")
        engine.record_outcome("empresa_b", "facebook_specialist", "post", "failure")

        summary_a = engine.get_performance_summary("empresa_a", "facebook_specialist")
        summary_b = engine.get_performance_summary("empresa_b", "facebook_specialist")

        assert summary_a["outcomes"].get("success") == 1
        assert summary_a["outcomes"].get("failure", 0) == 0
        assert summary_b["outcomes"].get("failure") == 1
        assert summary_b["outcomes"].get("success", 0) == 0

    def test_strategy_rankings_isolated_between_tenants(self, tmp_path):
        from src.adapters.learning_engine import LearningEngine
        engine = LearningEngine(db_path=tmp_path / "learning.db")

        for _ in range(3):
            engine.record_outcome("t1", "ads_specialist", "campaign", "success",
                                  context={"strategy": "retargeting"})
        for _ in range(3):
            engine.record_outcome("t2", "ads_specialist", "campaign", "success",
                                  context={"strategy": "cold_audience"})

        assert engine.get_best_strategy("t1", "ads_specialist") == "retargeting"
        assert engine.get_best_strategy("t2", "ads_specialist") == "cold_audience"


class TestPerformanceSummary:
    """Valida el resumen de rendimiento por especialista."""

    def test_success_rate_calculation(self, tmp_path):
        from src.adapters.learning_engine import LearningEngine
        engine = LearningEngine(db_path=tmp_path / "learning.db")

        engine.record_outcome("t1", "whatsapp_specialist", "campaign", "success")
        engine.record_outcome("t1", "whatsapp_specialist", "campaign", "success")
        engine.record_outcome("t1", "whatsapp_specialist", "campaign", "failure")

        summary = engine.get_performance_summary("t1", "whatsapp_specialist")
        assert summary["success_rate"] == pytest.approx(2/3, rel=0.01)
        assert summary["total_executions"] == 3

    def test_recent_failures_retrieval(self, tmp_path):
        from src.adapters.learning_engine import LearningEngine
        engine = LearningEngine(db_path=tmp_path / "learning.db")

        engine.record_outcome("t1", "crypto_specialist", "analysis", "failure",
                              context={"topic": "bitcoin"})
        engine.record_outcome("t1", "research_specialist", "research", "failure")

        failures = engine.get_recent_failures("t1", limit=5)
        assert len(failures) == 2
        assert all(f["specialist_id"] in ["crypto_specialist", "research_specialist"] for f in failures)

    def test_zero_executions_summary(self, tmp_path):
        from src.adapters.learning_engine import LearningEngine
        engine = LearningEngine(db_path=tmp_path / "learning.db")

        summary = engine.get_performance_summary("empty_tenant", "any_specialist")
        assert summary["total_executions"] == 0
        assert summary["success_rate"] == 0.0
        assert summary["best_strategy"] is None
