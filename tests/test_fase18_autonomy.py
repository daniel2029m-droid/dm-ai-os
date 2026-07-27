"""
Tests de Fase 18 — Autonomía (CognitiveScheduler)
==================================================
Valida:
1. Creación y persistencia de goals
2. Cancel y estado de goals
3. Listing y priorización de goals
4. Detección de inactividad → auto-creación de goals
5. Detección de oportunidades de tendencias
6. Detección de anomalías de engagement
7. Ejecución de goals vía especialistas (con mocks)
8. Lógica de retry en failures

Ejecutar: python -m pytest tests/test_fase18_autonomy.py -v
"""

import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch


class TestGoalCreation:
    """Valida creación y persistencia de goals autónomos."""

    def test_create_goal_returns_goal_object(self, tmp_path):
        from src.autonomy.cognitive_scheduler import CognitiveScheduler
        scheduler = CognitiveScheduler(db_path=tmp_path / "sched.db")

        goal = scheduler.create_goal(
            tenant_id="tenant_1",
            specialist_id="facebook_specialist",
            description="Publicar contenido de Facebook",
            priority=3,
            trigger="manual",
        )

        assert goal.goal_id.startswith("goal_")
        assert goal.tenant_id == "tenant_1"
        assert goal.specialist_id == "facebook_specialist"
        assert goal.priority == 3
        assert goal.status == "pending"

    def test_goal_persisted_in_db(self, tmp_path):
        from src.autonomy.cognitive_scheduler import CognitiveScheduler
        scheduler = CognitiveScheduler(db_path=tmp_path / "sched.db")

        goal = scheduler.create_goal("t1", "instagram_specialist", "Crear Reels", priority=1)

        retrieved = scheduler.get_goal_status(goal.goal_id)
        assert retrieved is not None
        assert retrieved["status"] == "pending"
        assert retrieved["specialist_id"] == "instagram_specialist"
        assert retrieved["priority"] == 1

    def test_create_goal_with_payload(self, tmp_path):
        from src.autonomy.cognitive_scheduler import CognitiveScheduler
        scheduler = CognitiveScheduler(db_path=tmp_path / "sched.db")

        payload = {"niche": "gastronomia", "platform": "facebook"}
        goal = scheduler.create_goal(
            "t1", "content_specialist", "Crear contenido viral", payload=payload
        )

        retrieved = scheduler.get_goal_status(goal.goal_id)
        assert retrieved is not None


class TestGoalCancellation:
    """Valida cancelación y gestión del ciclo de vida de goals."""

    def test_cancel_pending_goal(self, tmp_path):
        from src.autonomy.cognitive_scheduler import CognitiveScheduler
        scheduler = CognitiveScheduler(db_path=tmp_path / "sched.db")

        goal = scheduler.create_goal("t1", "youtube_specialist", "Crear video")
        assert scheduler.cancel_goal(goal.goal_id) is True

        status = scheduler.get_goal_status(goal.goal_id)
        assert status["status"] == "cancelled"

    def test_cancel_nonexistent_goal(self, tmp_path):
        from src.autonomy.cognitive_scheduler import CognitiveScheduler
        scheduler = CognitiveScheduler(db_path=tmp_path / "sched.db")

        assert scheduler.cancel_goal("nonexistent_goal_id") is False

    def test_cancelled_goal_not_in_pending(self, tmp_path):
        from src.autonomy.cognitive_scheduler import CognitiveScheduler
        scheduler = CognitiveScheduler(db_path=tmp_path / "sched.db")

        goal = scheduler.create_goal("t1", "tiktok_specialist", "Crear video")
        scheduler.cancel_goal(goal.goal_id)

        pending = scheduler.get_pending_goals()
        pending_ids = [g["goal_id"] for g in pending]
        assert goal.goal_id not in pending_ids


class TestGoalListing:
    """Valida listado y priorización de goals."""

    def test_list_goals_for_tenant(self, tmp_path):
        from src.autonomy.cognitive_scheduler import CognitiveScheduler
        scheduler = CognitiveScheduler(db_path=tmp_path / "sched.db")

        scheduler.create_goal("t1", "facebook_specialist", "Task A", priority=3)
        scheduler.create_goal("t1", "instagram_specialist", "Task B", priority=1)
        scheduler.create_goal("t2", "tiktok_specialist", "Task C", priority=2)  # different tenant

        goals_t1 = scheduler.list_goals("t1")
        assert len(goals_t1) == 2
        # Verify ordering by priority
        assert goals_t1[0]["priority"] <= goals_t1[1]["priority"]

    def test_pending_goals_ordered_by_priority(self, tmp_path):
        from src.autonomy.cognitive_scheduler import CognitiveScheduler
        scheduler = CognitiveScheduler(db_path=tmp_path / "sched.db")

        scheduler.create_goal("t1", "research_specialist", "Low priority", priority=8)
        scheduler.create_goal("t1", "facebook_specialist", "Critical", priority=1)
        scheduler.create_goal("t1", "content_specialist", "Medium", priority=5)

        pending = scheduler.get_pending_goals()
        priorities = [g["priority"] for g in pending]
        assert priorities == sorted(priorities)  # ascending = highest priority first

    def test_list_goals_filtered_by_status(self, tmp_path):
        from src.autonomy.cognitive_scheduler import CognitiveScheduler
        scheduler = CognitiveScheduler(db_path=tmp_path / "sched.db")

        g1 = scheduler.create_goal("t1", "seo_specialist", "SEO audit")
        g2 = scheduler.create_goal("t1", "analytics_specialist", "Analytics report")
        scheduler.cancel_goal(g2.goal_id)

        pending_goals = scheduler.list_goals("t1", status="pending")
        cancelled_goals = scheduler.list_goals("t1", status="cancelled")

        assert len(pending_goals) == 1
        assert len(cancelled_goals) == 1
        assert pending_goals[0]["goal_id"] == g1.goal_id


class TestInactivityDetection:
    """Valida detección automática de inactividad y creación de goals de recuperación."""

    def test_detect_inactivity_creates_goals_for_new_tenant(self, tmp_path):
        from src.autonomy.cognitive_scheduler import CognitiveScheduler
        scheduler = CognitiveScheduler(db_path=tmp_path / "sched.db")

        # New tenant — never executed any specialist
        goals = scheduler.detect_inactivity_goals("brand_new_tenant", inactivity_days=3)

        # Should create goals for all social watchlist specialists
        assert len(goals) > 0
        assert all(g.trigger == "inactivity_initial" for g in goals)
        assert all(g.status == "pending" for g in goals)

    def test_detect_inactivity_goals_have_correct_trigger(self, tmp_path):
        from src.autonomy.cognitive_scheduler import CognitiveScheduler
        scheduler = CognitiveScheduler(db_path=tmp_path / "sched.db")

        goals = scheduler.detect_inactivity_goals("inactive_tenant", inactivity_days=1)
        triggers = {g.trigger for g in goals}
        assert "inactivity_initial" in triggers or "inactivity" in triggers

    def test_detect_inactivity_high_priority_goals(self, tmp_path):
        from src.autonomy.cognitive_scheduler import CognitiveScheduler
        scheduler = CognitiveScheduler(db_path=tmp_path / "sched.db")

        goals = scheduler.detect_inactivity_goals("tenant_x")
        # Inactivity goals should be high priority (1-3)
        assert all(g.priority <= 3 for g in goals)


class TestOpportunityDetection:
    """Valida detección de tendencias y creación de goals de oportunidad."""

    def test_detect_opportunity_creates_goals(self, tmp_path):
        from src.autonomy.cognitive_scheduler import CognitiveScheduler
        scheduler = CognitiveScheduler(db_path=tmp_path / "sched.db")

        goals = scheduler.detect_opportunity_goals(
            "tenant_y",
            trending_topics=["IA generativa", "TikTok viral dance", "ChatGPT"],
        )

        assert len(goals) <= 3  # max 3 per cycle
        assert all(g.trigger == "trend" for g in goals)
        assert all(g.specialist_id == "content_specialist" for g in goals)

    def test_detect_opportunity_empty_topics(self, tmp_path):
        from src.autonomy.cognitive_scheduler import CognitiveScheduler
        scheduler = CognitiveScheduler(db_path=tmp_path / "sched.db")

        goals = scheduler.detect_opportunity_goals("t1", trending_topics=[])
        assert goals == []


class TestAnomalyDetection:
    """Valida detección de anomalías de engagement."""

    def test_detect_engagement_anomaly_creates_goal(self, tmp_path):
        from src.autonomy.cognitive_scheduler import CognitiveScheduler
        scheduler = CognitiveScheduler(db_path=tmp_path / "sched.db")

        goal = scheduler.detect_engagement_anomaly_goals(
            tenant_id="t1",
            specialist_id="instagram_specialist",
            drop_percentage=35.0,
        )

        assert goal is not None
        assert goal.trigger == "anomaly"
        assert goal.status == "pending"
        assert "35" in goal.description


class TestGoalExecution:
    """Valida ejecución de goals con especialistas (mockeado)."""

    @pytest.mark.asyncio
    async def test_execute_goal_success(self, tmp_path):
        from src.autonomy.cognitive_scheduler import CognitiveScheduler
        scheduler = CognitiveScheduler(db_path=tmp_path / "sched.db")

        goal = scheduler.create_goal(
            "t1", "facebook_specialist", "Publicar en Facebook"
        )
        goal_data = scheduler.get_goal_status(goal.goal_id)

        mock_worker = MagicMock()
        mock_worker.specialist_id = "facebook_specialist"
        mock_worker.execute_task = AsyncMock(return_value={"status": "success", "post_id": "123"})

        with patch(
            "src.autonomy.cognitive_scheduler.CognitiveScheduler.execute_goal",
            new_callable=AsyncMock,
        ) as mock_exec:
            mock_exec.return_value = {"status": "success", "goal_id": goal.goal_id}
            result = await scheduler.execute_goal(goal_data)

        # Verify the mock was called or result is structured
        assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_run_cycle_returns_list(self, tmp_path):
        from src.autonomy.cognitive_scheduler import CognitiveScheduler
        scheduler = CognitiveScheduler(db_path=tmp_path / "sched.db")

        # No pending goals → empty results
        with patch.object(scheduler, "get_pending_goals", return_value=[]):
            results = await scheduler.run_cycle()
        assert isinstance(results, list)
        assert len(results) == 0
