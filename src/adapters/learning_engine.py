"""
LearningEngine — Incremental Experience-Based Learning (Fase 17)
================================================================
Continuous learning for all 20 Autonomous Digital Employee Specialists.

NO model training. NO fine-tuning. NO neural networks.
Pure incremental experience accumulation:
- Records every execution outcome (success/failure/partial)
- Tracks business metrics (CTR, engagement, conversions, ROAS, virality)
- Builds strategy rankings per tenant+specialist over time
- Injects accumulated wisdom into future LLM prompts via experience context
- Specialists automatically improve without any human intervention

Pattern: Adapter pattern (no core changes). Fully decoupled.
"""

import os
import json
import sqlite3
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List

log = logging.getLogger("learning_engine")

def _get_default_db() -> Path:
    base_storage = os.getenv("DM_STORAGE_DIR") or os.getenv("DM_DATA_DIR")
    if base_storage:
        base = Path(base_storage)
    elif os.getenv("VERCEL"):
        base = Path("/tmp/Project_State")
    else:
        base = Path(__file__).parent.parent.parent / "Project_State"
    try:
        base.mkdir(parents=True, exist_ok=True)
    except Exception:
        base = Path("/tmp/Project_State")
        base.mkdir(parents=True, exist_ok=True)
    return base / "learning.db"


class LearningEngine:
    """
    Incremental learning engine for autonomous business specialists.
    Each specialist calls record_outcome() after every execution.
    Future executions call get_experience_context() to inject learnings into prompts.
    """

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or _get_default_db()
        try:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
        except Exception:
            self.db_path = Path("/tmp/Project_State") / "learning.db"
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS experiences (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tenant_id TEXT NOT NULL,
                    specialist_id TEXT NOT NULL,
                    task_type TEXT NOT NULL,
                    outcome TEXT NOT NULL,
                    metrics TEXT DEFAULT '{}',
                    context TEXT DEFAULT '{}',
                    feedback TEXT,
                    learned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS strategy_rankings (
                    tenant_id TEXT NOT NULL,
                    specialist_id TEXT NOT NULL,
                    strategy TEXT NOT NULL,
                    score REAL DEFAULT 0.0,
                    sample_count INTEGER DEFAULT 0,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (tenant_id, specialist_id, strategy)
                );
                CREATE INDEX IF NOT EXISTS idx_exp_lookup
                    ON experiences(tenant_id, specialist_id, task_type);
                CREATE INDEX IF NOT EXISTS idx_exp_outcome
                    ON experiences(tenant_id, specialist_id, outcome);
            """)
            conn.commit()

    # ── Recording ────────────────────────────────────────────────────────────

    def record_outcome(
        self,
        tenant_id: str,
        specialist_id: str,
        task_type: str,
        outcome: str,
        metrics: Optional[Dict[str, Any]] = None,
        context: Optional[Dict[str, Any]] = None,
        feedback: Optional[str] = None,
    ) -> None:
        """
        Record a specialist execution outcome for continuous learning.

        Args:
            tenant_id: Isolated client identifier.
            specialist_id: Specialist that ran the task e.g. 'facebook_specialist'.
            task_type: Task category e.g. 'content_creation', 'research', 'publish', 'ads'.
            outcome: 'success', 'failure', or 'partial'.
            metrics: Dict with CTR, engagement_rate, conversions, roas, viral_score, etc.
            context: Execution context (niche, platform, strategy, tone, format, etc.)
            feedback: Optional human or automated quality feedback string.
        """
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute(
                "INSERT INTO experiences (tenant_id, specialist_id, task_type, outcome, metrics, context, feedback) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    tenant_id, specialist_id, task_type, outcome,
                    json.dumps(metrics or {}),
                    json.dumps(context or {}),
                    feedback,
                )
            )
            conn.commit()

        # Auto-update strategy ranking for this execution
        if context:
            strategy = context.get("strategy", "default")
            delta = self._compute_score_delta(outcome, metrics or {})
            self._update_ranking(tenant_id, specialist_id, strategy, delta)

        log.info(
            f"[LearningEngine] Recorded '{outcome}' for {specialist_id}@{tenant_id} "
            f"task={task_type}"
        )

    def _compute_score_delta(self, outcome: str, metrics: Dict[str, Any]) -> float:
        """Compute learning score contribution from outcome + metrics."""
        base = {"success": 1.0, "partial": 0.3, "failure": -0.5}.get(outcome, 0.0)
        bonus = (
            float(metrics.get("ctr", 0)) * 2.0
            + float(metrics.get("engagement_rate", 0)) * 1.5
            + float(metrics.get("conversions", 0)) * 3.0
            + float(metrics.get("roas", 0)) * 0.5
            + float(metrics.get("viral_score", 0)) * 2.0
        )
        return base + min(bonus, 5.0)

    def _update_ranking(
        self,
        tenant_id: str,
        specialist_id: str,
        strategy: str,
        score_delta: float,
    ) -> None:
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute("""
                INSERT INTO strategy_rankings (tenant_id, specialist_id, strategy, score, sample_count)
                VALUES (?, ?, ?, ?, 1)
                ON CONFLICT(tenant_id, specialist_id, strategy) DO UPDATE SET
                    score = (score * sample_count + excluded.score) / (sample_count + 1),
                    sample_count = sample_count + 1,
                    updated_at = CURRENT_TIMESTAMP
            """, (tenant_id, specialist_id, strategy, score_delta))
            conn.commit()

    # ── Retrieval & Context ──────────────────────────────────────────────────

    def get_experience_context(
        self,
        tenant_id: str,
        specialist_id: str,
        task_type: Optional[str] = None,
        limit: int = 10,
    ) -> str:
        """
        Build an experience context string to inject into specialist LLM prompts.
        Future decisions automatically incorporate past learnings.

        Returns:
            Formatted multi-line string with accumulated wisdom for this specialist.
        """
        with sqlite3.connect(str(self.db_path)) as conn:
            if task_type:
                rows = conn.execute(
                    "SELECT task_type, outcome, metrics, context FROM experiences "
                    "WHERE tenant_id=? AND specialist_id=? AND task_type=? "
                    "ORDER BY learned_at DESC LIMIT ?",
                    (tenant_id, specialist_id, task_type, limit)
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT task_type, outcome, metrics, context FROM experiences "
                    "WHERE tenant_id=? AND specialist_id=? "
                    "ORDER BY learned_at DESC LIMIT ?",
                    (tenant_id, specialist_id, limit)
                ).fetchall()

        if not rows:
            return "Sin experiencia previa. Primera ejecución de este especialista."

        successes = sum(1 for r in rows if r[1] == "success")
        failures = sum(1 for r in rows if r[1] == "failure")

        lines = [
            "=== EXPERIENCIA ACUMULADA (usar para mejorar decisiones) ===",
            f"Registros: {len(rows)} | Éxitos: {successes} | Fallos: {failures}",
        ]

        best = self.get_best_strategy(tenant_id, specialist_id)
        if best:
            lines.append(f"Estrategia más efectiva: {best}")

        lines.append("Últimas ejecuciones:")
        for task_t, outcome, metrics_json, ctx_json in rows[:5]:
            metrics = json.loads(metrics_json or "{}")
            ctx = json.loads(ctx_json or "{}")
            metric_parts = [f"{k}={v}" for k, v in metrics.items() if v]
            metric_str = ", ".join(metric_parts) if metric_parts else "sin métricas"
            niche = ctx.get("niche", ctx.get("topic", ""))
            niche_str = f" [{niche}]" if niche else ""
            lines.append(f"  • [{outcome.upper()}]{niche_str} {task_t}: {metric_str}")

        return "\n".join(lines)

    def get_best_strategy(self, tenant_id: str, specialist_id: str) -> Optional[str]:
        """Return the highest-scoring strategy based on accumulated experience."""
        with sqlite3.connect(str(self.db_path)) as conn:
            row = conn.execute(
                "SELECT strategy FROM strategy_rankings "
                "WHERE tenant_id=? AND specialist_id=? AND sample_count >= 2 "
                "ORDER BY score DESC LIMIT 1",
                (tenant_id, specialist_id)
            ).fetchone()
        return row[0] if row else None

    def get_performance_summary(
        self, tenant_id: str, specialist_id: str
    ) -> Dict[str, Any]:
        """Get full performance summary for a specialist under a tenant."""
        with sqlite3.connect(str(self.db_path)) as conn:
            total = conn.execute(
                "SELECT COUNT(*) FROM experiences WHERE tenant_id=? AND specialist_id=?",
                (tenant_id, specialist_id)
            ).fetchone()[0]

            by_outcome = conn.execute(
                "SELECT outcome, COUNT(*) FROM experiences "
                "WHERE tenant_id=? AND specialist_id=? GROUP BY outcome",
                (tenant_id, specialist_id)
            ).fetchall()

            top_strategies = conn.execute(
                "SELECT strategy, score, sample_count FROM strategy_rankings "
                "WHERE tenant_id=? AND specialist_id=? ORDER BY score DESC LIMIT 3",
                (tenant_id, specialist_id)
            ).fetchall()

        outcome_counts = {r[0]: r[1] for r in by_outcome}
        success_rate = outcome_counts.get("success", 0) / max(total, 1)

        return {
            "specialist_id": specialist_id,
            "tenant_id": tenant_id,
            "total_executions": total,
            "success_rate": round(success_rate, 3),
            "outcomes": outcome_counts,
            "best_strategy": self.get_best_strategy(tenant_id, specialist_id),
            "top_strategies": [
                {"strategy": r[0], "score": round(r[1], 3), "samples": r[2]}
                for r in top_strategies
            ],
        }

    def get_recent_failures(
        self, tenant_id: str, limit: int = 5
    ) -> List[Dict[str, Any]]:
        """Return recent failure records for analysis and retry logic."""
        with sqlite3.connect(str(self.db_path)) as conn:
            rows = conn.execute(
                "SELECT specialist_id, task_type, context, learned_at FROM experiences "
                "WHERE tenant_id=? AND outcome='failure' ORDER BY learned_at DESC LIMIT ?",
                (tenant_id, limit)
            ).fetchall()
        return [
            {
                "specialist_id": r[0],
                "task_type": r[1],
                "context": json.loads(r[2] or "{}"),
                "learned_at": r[3],
            }
            for r in rows
        ]


# Module-level singleton
learning_engine = LearningEngine()
