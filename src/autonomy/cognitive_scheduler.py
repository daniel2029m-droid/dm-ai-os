"""
CognitiveScheduler — Autonomous Cognitive Goal Engine (Fase 18)
===============================================================
Runs without human intervention. Creates, prioritizes, executes, retries,
delegates, cancels and schedules goals based on system signals:

  • Inactivity detection  → "Facebook lleva 3 días sin publicar"
  • Opportunity detection → "Encontré una tendencia nueva"
  • Anomaly detection     → "El engagement cayó"
  • Scheduled missions    → recurring content cycles
  • Delegation            → route to best-fit specialist

Uses ONLY existing core: SpecialistRegistry, MemoryManager, WorkflowEngine.
Pattern: New module in src/autonomy/ — zero core changes.
"""

import asyncio
import json
import logging
import sqlite3
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

log = logging.getLogger("cognitive_scheduler")

_DEFAULT_DB = Path(__file__).parent.parent.parent / "Project_State" / "cognitive_scheduler.db"


class Goal:
    """Represents one autonomous system goal."""

    def __init__(
        self,
        goal_id: str,
        tenant_id: str,
        specialist_id: str,
        description: str,
        priority: int = 5,
        trigger: str = "manual",
        payload: Optional[Dict[str, Any]] = None,
        max_attempts: int = 3,
    ):
        self.goal_id = goal_id
        self.tenant_id = tenant_id
        self.specialist_id = specialist_id
        self.description = description
        self.priority = priority        # 1 = critical → 10 = low
        self.trigger = trigger          # "manual" | "inactivity" | "trend" | "schedule" | "anomaly"
        self.payload = payload or {}
        self.max_attempts = max_attempts
        self.status = "pending"         # pending | running | completed | failed | cancelled
        self.attempts = 0
        self.result: Optional[Dict] = None
        self.created_at = datetime.utcnow().isoformat()


class CognitiveScheduler:
    """
    Autonomous cognitive scheduler for DM AI OS.
    Detects system states and autonomously creates and executes goals.
    Designed to run as a background loop with no human intervention.
    """

    # Social specialists monitored for inactivity
    _SOCIAL_WATCHLIST = [
        ("facebook_specialist",  "Facebook lleva días sin publicar. Crea contenido y publica automáticamente."),
        ("instagram_specialist", "Instagram sin actividad. Crea Reels y publica automáticamente."),
        ("tiktok_specialist",    "TikTok sin publicar. Crea videos virales y publica."),
        ("youtube_specialist",   "YouTube sin actividad. Crea contenido y optimiza SEO."),
        ("whatsapp_specialist",  "WhatsApp sin campañas recientes. Envía promociones a contactos."),
    ]

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or _DEFAULT_DB
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._check_interval_seconds = 300      # default 5-minute cycles
        self._running = False
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS goals (
                    goal_id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    specialist_id TEXT NOT NULL,
                    description TEXT NOT NULL,
                    priority INTEGER DEFAULT 5,
                    trigger_type TEXT DEFAULT 'manual',
                    payload TEXT DEFAULT '{}',
                    status TEXT DEFAULT 'pending',
                    attempts INTEGER DEFAULT 0,
                    max_attempts INTEGER DEFAULT 3,
                    result TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS specialist_activity (
                    tenant_id TEXT NOT NULL,
                    specialist_id TEXT NOT NULL,
                    last_execution TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    execution_count INTEGER DEFAULT 0,
                    PRIMARY KEY (tenant_id, specialist_id)
                );
                CREATE INDEX IF NOT EXISTS idx_goals_pending
                    ON goals(status, priority ASC, created_at ASC);
                CREATE INDEX IF NOT EXISTS idx_goals_tenant
                    ON goals(tenant_id, status);
            """)
            conn.commit()

    # ── Goal Lifecycle ────────────────────────────────────────────────────────

    def create_goal(
        self,
        tenant_id: str,
        specialist_id: str,
        description: str,
        priority: int = 5,
        trigger: str = "manual",
        payload: Optional[Dict[str, Any]] = None,
        max_attempts: int = 3,
    ) -> Goal:
        """Create and persist a new autonomous goal."""
        goal_id = f"goal_{uuid.uuid4().hex[:12]}"
        goal = Goal(
            goal_id=goal_id,
            tenant_id=tenant_id,
            specialist_id=specialist_id,
            description=description,
            priority=priority,
            trigger=trigger,
            payload=payload or {},
            max_attempts=max_attempts,
        )

        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute("""
                INSERT INTO goals
                    (goal_id, tenant_id, specialist_id, description, priority, trigger_type, payload, max_attempts)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                goal.goal_id, goal.tenant_id, goal.specialist_id, goal.description,
                goal.priority, goal.trigger, json.dumps(goal.payload), goal.max_attempts,
            ))
            conn.commit()

        log.info(
            f"[CognitiveScheduler] Goal created: {goal_id} | "
            f"priority={priority} trigger={trigger} | {description[:60]}"
        )
        return goal

    def cancel_goal(self, goal_id: str) -> bool:
        """Cancel a pending goal. Returns True if cancelled."""
        with sqlite3.connect(str(self.db_path)) as conn:
            affected = conn.execute(
                "UPDATE goals SET status='cancelled', updated_at=CURRENT_TIMESTAMP "
                "WHERE goal_id=? AND status='pending'",
                (goal_id,)
            ).rowcount
            conn.commit()
        return affected > 0

    def get_goal_status(self, goal_id: str) -> Optional[Dict[str, Any]]:
        """Return current state of a goal."""
        with sqlite3.connect(str(self.db_path)) as conn:
            row = conn.execute(
                "SELECT goal_id, tenant_id, specialist_id, description, status, priority, "
                "attempts, max_attempts, result, trigger_type, created_at, updated_at "
                "FROM goals WHERE goal_id=?",
                (goal_id,)
            ).fetchone()
        if not row:
            return None
        return {
            "goal_id": row[0], "tenant_id": row[1], "specialist_id": row[2],
            "description": row[3], "status": row[4], "priority": row[5],
            "attempts": row[6], "max_attempts": row[7],
            "result": json.loads(row[8]) if row[8] else None,
            "trigger": row[9], "created_at": row[10], "updated_at": row[11],
        }

    def list_goals(
        self,
        tenant_id: str,
        status: Optional[str] = None,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """List goals for a tenant, optionally filtered by status."""
        with sqlite3.connect(str(self.db_path)) as conn:
            if status:
                rows = conn.execute(
                    "SELECT goal_id, specialist_id, description, status, priority, created_at "
                    "FROM goals WHERE tenant_id=? AND status=? "
                    "ORDER BY priority ASC, created_at DESC LIMIT ?",
                    (tenant_id, status, limit)
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT goal_id, specialist_id, description, status, priority, created_at "
                    "FROM goals WHERE tenant_id=? "
                    "ORDER BY priority ASC, created_at DESC LIMIT ?",
                    (tenant_id, limit)
                ).fetchall()
        return [
            {
                "goal_id": r[0], "specialist_id": r[1], "description": r[2],
                "status": r[3], "priority": r[4], "created_at": r[5],
            }
            for r in rows
        ]

    def get_pending_goals(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Return highest-priority pending goals across all tenants."""
        with sqlite3.connect(str(self.db_path)) as conn:
            rows = conn.execute(
                "SELECT goal_id, tenant_id, specialist_id, description, priority, "
                "trigger_type, payload, attempts, max_attempts "
                "FROM goals WHERE status='pending' AND attempts < max_attempts "
                "ORDER BY priority ASC, created_at ASC LIMIT ?",
                (limit,)
            ).fetchall()
        return [
            {
                "goal_id": r[0], "tenant_id": r[1], "specialist_id": r[2],
                "description": r[3], "priority": r[4], "trigger": r[5],
                "payload": json.loads(r[6] or "{}"), "attempts": r[7], "max_attempts": r[8],
            }
            for r in rows
        ]

    # ── Execution ─────────────────────────────────────────────────────────────

    async def execute_goal(self, goal_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute one goal by delegating to the appropriate specialist.
        Handles retry logic automatically.
        """
        goal_id = goal_data["goal_id"]
        tenant_id = goal_data["tenant_id"]
        specialist_id = goal_data["specialist_id"]
        description = goal_data["description"]
        payload = goal_data["payload"]
        new_attempts = goal_data["attempts"] + 1

        self._set_status(goal_id, "running", attempts=new_attempts)
        log.info(f"[CognitiveScheduler] Executing {goal_id} (attempt {new_attempts}): {description[:70]}")

        try:
            from ..specialists.specialist_registry import specialist_registry

            # Direct lookup first, then intent routing
            worker = specialist_registry.get_specialist(specialist_id)
            if worker is None:
                worker = specialist_registry.route_mission(description)
            if worker is None:
                raise ValueError(f"No specialist found for id='{specialist_id}'")

            # Apply tenant isolation
            worker.tenant_id = tenant_id
            worker._tenant_context = None   # Force lazy reload with correct tenant

            result = await worker.execute_task(description, payload)

            self._set_status(goal_id, "completed", result=result)
            self._record_activity(tenant_id, specialist_id)
            log.info(f"[CognitiveScheduler] Goal {goal_id} completed ✅")
            return result

        except Exception as exc:
            log.error(f"[CognitiveScheduler] Goal {goal_id} attempt {new_attempts} failed: {exc}")

            if new_attempts >= goal_data["max_attempts"]:
                self._set_status(goal_id, "failed", result={"error": str(exc)})
            else:
                # Reset to pending for retry
                self._set_status(goal_id, "pending")

            return {"status": "error", "error": str(exc), "goal_id": goal_id}

    def _set_status(
        self,
        goal_id: str,
        status: str,
        attempts: Optional[int] = None,
        result: Optional[Dict] = None,
    ) -> None:
        with sqlite3.connect(str(self.db_path)) as conn:
            if attempts is not None:
                conn.execute(
                    "UPDATE goals SET status=?, attempts=?, result=?, updated_at=CURRENT_TIMESTAMP WHERE goal_id=?",
                    (status, attempts, json.dumps(result) if result else None, goal_id)
                )
            else:
                conn.execute(
                    "UPDATE goals SET status=?, result=?, updated_at=CURRENT_TIMESTAMP WHERE goal_id=?",
                    (status, json.dumps(result) if result else None, goal_id)
                )
            conn.commit()

    def _record_activity(self, tenant_id: str, specialist_id: str) -> None:
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute("""
                INSERT INTO specialist_activity (tenant_id, specialist_id, last_execution, execution_count)
                VALUES (?, ?, CURRENT_TIMESTAMP, 1)
                ON CONFLICT(tenant_id, specialist_id) DO UPDATE SET
                    last_execution = CURRENT_TIMESTAMP,
                    execution_count = execution_count + 1
            """, (tenant_id, specialist_id))
            conn.commit()

    # ── Autonomous Detection ──────────────────────────────────────────────────

    def detect_inactivity_goals(
        self,
        tenant_id: str,
        inactivity_days: int = 3,
    ) -> List[Goal]:
        """
        Detect social specialists inactive for too long and auto-create catch-up goals.
        Implements: "Hace tres días que Facebook no publica."
        """
        with sqlite3.connect(str(self.db_path)) as conn:
            rows = conn.execute(
                "SELECT specialist_id, last_execution FROM specialist_activity WHERE tenant_id=?",
                (tenant_id,)
            ).fetchall()

        activity_map = {r[0]: r[1] for r in rows}
        threshold = datetime.utcnow() - timedelta(days=inactivity_days)
        created: List[Goal] = []

        for specialist_id, goal_desc in self._SOCIAL_WATCHLIST:
            last_raw = activity_map.get(specialist_id)

            should_create = False
            if last_raw is None:
                # Never executed — needs initial activation
                trigger = "inactivity_initial"
                should_create = True
            else:
                try:
                    last_dt = datetime.fromisoformat(str(last_raw))
                    if last_dt < threshold:
                        trigger = "inactivity"
                        should_create = True
                except (ValueError, TypeError):
                    trigger = "inactivity"
                    should_create = True

            if should_create:
                goal = self.create_goal(
                    tenant_id=tenant_id,
                    specialist_id=specialist_id,
                    description=goal_desc,
                    priority=2,
                    trigger=trigger,
                )
                created.append(goal)

        return created

    def detect_opportunity_goals(
        self,
        tenant_id: str,
        trending_topics: Optional[List[str]] = None,
    ) -> List[Goal]:
        """
        Create goals from detected opportunities (trends, new content ideas).
        Implements: "Descubrí una tendencia nueva."
        """
        created: List[Goal] = []
        if not trending_topics:
            return created

        for topic in trending_topics[:3]:     # max 3 opportunity goals per cycle
            goal = self.create_goal(
                tenant_id=tenant_id,
                specialist_id="content_specialist",
                description=f"Tendencia detectada: '{topic}'. Crear contenido viral aprovechando esta tendencia.",
                priority=3,
                trigger="trend",
                payload={"topic": topic, "context": "trending_opportunity"},
            )
            created.append(goal)

        return created

    def detect_engagement_anomaly_goals(
        self,
        tenant_id: str,
        specialist_id: str,
        drop_percentage: float = 20.0,
    ) -> Optional[Goal]:
        """
        Create a recovery goal when engagement anomaly is detected.
        Implements: "El engagement cayó."
        """
        goal = self.create_goal(
            tenant_id=tenant_id,
            specialist_id=specialist_id,
            description=(
                f"El engagement cayó {drop_percentage:.0f}%. "
                "Analiza las métricas, identifica el problema y crea contenido de recuperación."
            ),
            priority=2,
            trigger="anomaly",
            payload={"drop_percentage": drop_percentage, "action": "recovery"},
        )
        return goal

    # ── Autonomous Cycle ──────────────────────────────────────────────────────

    async def run_cycle(self, max_goals: int = 5) -> List[Dict[str, Any]]:
        """
        Execute one autonomous cycle: process highest-priority pending goals.
        Call this from a background task loop.
        """
        pending = self.get_pending_goals(limit=max_goals)
        results = []

        for goal_data in pending:
            result = await self.execute_goal(goal_data)
            results.append(result)

        log.info(
            f"[CognitiveScheduler] Cycle complete — processed {len(results)} goals"
        )
        return results


# Module-level singleton
cognitive_scheduler = CognitiveScheduler()
