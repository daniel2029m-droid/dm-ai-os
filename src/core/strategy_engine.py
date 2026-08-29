"""
StrategyEngine — Creative Strategy Synthesis & Brief Generation for DM AI OS v1.5.1.
Transforms audience performance metrics, prompt genome patterns, and experiment outcomes
into structured, testable, and actionable Creative Briefs for Phase 14 autonomous execution.
"""
import sqlite3
import os
import json
import time
import hashlib
import logging
from dataclasses import dataclass
from typing import Dict, Any, List, Optional, Set

from ..storage.storage_layer import storage
from ..core.creative_memory import creative_memory, CreativeMemoryManager
from ..core.experiment_engine import experiment_engine, ExperimentEngine
from ..core.creative_engine import creative_engine

log = logging.getLogger("strategy_engine")

VALID_BRIEF_STATES: Set[str] = {
    "PROPOSED",
    "ACCEPTED",
    "DISPATCHED",
    "REJECTED"
}

TERMINAL_BRIEF_STATES: Set[str] = {
    "DISPATCHED",
    "REJECTED"
}


class StrategyError(ValueError):
    """Raised when brief generation or lifecycle state transitions fail."""
    def __init__(self, message: str, error_code: str = "STRATEGY_ERROR", details: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.error_code = error_code
        self.details = details or {}


class StrategyEngine:
    """
    Synthesizes creative intelligence into actionable creative briefs.
    Decoupled from execution; strictly dispatches via Phase 14 public interfaces.
    """

    def __init__(
        self,
        db_path: Optional[str] = None,
        memory_manager: Optional[CreativeMemoryManager] = None,
        experiment_eng: Optional[ExperimentEngine] = None
    ):
        if not db_path:
            db_dir_env = os.getenv("DM_STORAGE_DIR") or os.getenv("DM_DATA_DIR")
            if db_dir_env:
                db_dir = os.path.join(db_dir_env, "Storage")
            elif os.getenv("VERCEL"):
                db_dir = "/tmp/Project_State/Storage"
            else:
                db_dir = os.path.join(
                    os.path.expanduser("~"),
                    ".gemini", "antigravity-ide", "scratch", "Project_State", "Storage"
                )
            db_path = os.path.join(db_dir, "knowledge.db")

        self.db_path = db_path
        self.memory = memory_manager or creative_memory
        self.experiments = experiment_eng or experiment_engine
        self._db_initialized = False

    def _ensure_db(self):
        if self._db_initialized:
            return
        db_dir = os.path.dirname(self.db_path)
        try:
            os.makedirs(db_dir, exist_ok=True)
        except Exception:
            db_dir = "/tmp/Project_State/Storage"
            os.makedirs(db_dir, exist_ok=True)
            self.db_path = os.path.join(db_dir, "knowledge.db")

        self._init_db()
        self._db_initialized = True

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS creative_strategy_briefs (
                    brief_id TEXT PRIMARY KEY,
                    topic TEXT NOT NULL,
                    workflow_template TEXT NOT NULL,
                    model_name TEXT,
                    recommended_prompt TEXT NOT NULL,
                    recommended_negative_prompt TEXT,
                    recommended_parameters_json TEXT,
                    recommended_genome_json TEXT,
                    evidence_patterns_json TEXT,
                    hypothesis TEXT,
                    confidence_score REAL DEFAULT 0.0,
                    status TEXT NOT NULL DEFAULT 'PROPOSED',
                    dispatched_job_id TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    concluded_at TIMESTAMP
                );
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_creative_strategy_briefs_status ON creative_strategy_briefs(status);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_creative_strategy_briefs_created ON creative_strategy_briefs(created_at);")
            conn.commit()

    def _compute_brief_hash(
        self,
        topic: str,
        template: str,
        model: Optional[str],
        prompt: str,
        params: Dict[str, Any]
    ) -> str:
        payload = {
            "topic": topic.strip().lower(),
            "template": template.strip(),
            "model": (model or "").strip(),
            "prompt": prompt.strip(),
            "params": params
        }
        canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def create_brief(
        self,
        topic: str,
        target_channel: Optional[str] = None,
        base_template: Optional[str] = None,
        model_name: Optional[str] = None,
        custom_hypothesis: Optional[str] = None,
        parameters: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Synthesizes historical memory, pattern statistics, and concluded experiments to generate an optimal Creative Brief.
        """
        self._ensure_db()

        if not topic or not isinstance(topic, str) or not topic.strip():
            raise StrategyError("Topic must be a non-empty string.", error_code="INVALID_TOPIC")

        topic_clean = topic.strip()
        template = base_template or "flux2_klein_txt2img"
        model = model_name or "flux2_klein"
        params = dict(parameters or {})

        # Query top reliable patterns from Creative Memory
        top_styles = self.memory.get_top_patterns(category="STYLE", limit=5)
        top_hooks = self.memory.get_top_patterns(category="HOOK", limit=5)
        top_compositions = self.memory.get_top_patterns(category="COMPOSITION", limit=5)
        top_lightings = self.memory.get_top_patterns(category="LIGHTING", limit=5)
        underperforming = self.memory.get_underperforming_patterns(limit=10)
        underperforming_descs = {p.get("descriptor") for p in underperforming if p.get("classification") == "UNDERPERFORMING" and p.get("is_reliable_evidence")}

        # Filter for high-confidence outperforming patterns
        reliable_styles = [p for p in top_styles if p.get("classification") == "OUTPERFORMING" and p.get("descriptor") not in underperforming_descs]
        reliable_hooks = [p for p in top_hooks if p.get("classification") == "OUTPERFORMING" and p.get("descriptor") not in underperforming_descs]
        reliable_compositions = [p for p in top_compositions if p.get("classification") == "OUTPERFORMING" and p.get("descriptor") not in underperforming_descs]
        reliable_lightings = [p for p in top_lightings if p.get("classification") == "OUTPERFORMING" and p.get("descriptor") not in underperforming_descs]

        evidence_list = []
        genome_recommendation: Dict[str, str] = {}

        is_cold_start = not (reliable_styles or reliable_hooks or reliable_compositions or reliable_lightings)

        if is_cold_start:
            # Cold-start exploration policy: select neutral balanced defaults
            selected_style = "photorealistic"
            selected_hook = "hero_shot"
            selected_comp = "centered"
            selected_light = "cinematic lighting"
            confidence = 0.30
            hypothesis = custom_hypothesis or f"Exploration baseline: Testing visual performance of '{topic_clean}' with balanced photographic composition."
            rationale_mode = "COLD_START_EXPLORATION"
        else:
            # Evidence exploitation policy: select top performing descriptors
            selected_style = reliable_styles[0]["descriptor"] if reliable_styles else "cinematic"
            selected_hook = reliable_hooks[0]["descriptor"] if reliable_hooks else "dynamic_action"
            selected_comp = reliable_compositions[0]["descriptor"] if reliable_compositions else "centered"
            selected_light = reliable_lightings[0]["descriptor"] if reliable_lightings else "neon"

            used_patterns = reliable_styles[:1] + reliable_hooks[:1] + reliable_compositions[:1] + reliable_lightings[:1]
            evidence_list = [
                {
                    "pattern_id": p["pattern_id"],
                    "pattern_type": p["pattern_type"],
                    "descriptor": p["descriptor"],
                    "lift": p.get("lift", 0.0),
                    "sample_count": p.get("sample_count", 0),
                    "classification": p.get("classification")
                }
                for p in used_patterns
            ]

            # Calculate confidence score deterministically
            avg_lift = sum(p.get("lift", 0.0) for p in used_patterns) / max(len(used_patterns), 1)
            confidence = min(0.95, round(0.60 + (avg_lift * 0.03), 2))
            hypothesis = custom_hypothesis or f"Exploiting winning pattern combination ({selected_style} + {selected_hook} + {selected_light}) to maximize engagement for '{topic_clean}'."
            rationale_mode = "EVIDENCE_BASED_EXPLOITATION"

        genome_recommendation = {
            "STYLE": selected_style,
            "HOOK": selected_hook,
            "COMPOSITION": selected_comp,
            "LIGHTING": selected_light
        }

        # Synthesize prompt
        hook_phrase = selected_hook.replace("_", " ")
        style_phrase = selected_style.replace("_", " ")
        comp_phrase = selected_comp.replace("_", " ")
        light_phrase = selected_light.replace("_", " ")

        recommended_prompt = f"A {style_phrase} {hook_phrase} of {topic_clean}, {comp_phrase} composition, {light_phrase} lighting, masterwork, 8k resolution"
        recommended_negative_prompt = "low quality, blurry, distorted, overexposed, bad anatomy"

        import uuid
        brief_id = f"brf_{uuid.uuid4().hex[:12]}"
        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

        # Check existing equivalent brief for idempotency
        brief_hash = self._compute_brief_hash(topic_clean, template, model, recommended_prompt, params)
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("""
                SELECT brief_id FROM creative_strategy_briefs
                WHERE topic = ? AND workflow_template = ? AND recommended_prompt = ? AND status = 'PROPOSED'
                ORDER BY created_at DESC LIMIT 1
            """, (topic_clean, template, recommended_prompt))
            existing = cursor.fetchone()
            if existing:
                log.info(f"[StrategyEngine] Idempotent hit: Reusing proposed brief ({existing['brief_id']})")
                return self.get_brief(existing["brief_id"])

            cursor.execute("""
                INSERT INTO creative_strategy_briefs (
                    brief_id, topic, workflow_template, model_name, recommended_prompt,
                    recommended_negative_prompt, recommended_parameters_json, recommended_genome_json,
                    evidence_patterns_json, hypothesis, confidence_score, status, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'PROPOSED', ?)
            """, (
                brief_id,
                topic_clean,
                template,
                model,
                recommended_prompt,
                recommended_negative_prompt,
                json.dumps(params, ensure_ascii=False),
                json.dumps(genome_recommendation, ensure_ascii=False),
                json.dumps(evidence_list, ensure_ascii=False),
                hypothesis,
                confidence,
                now
            ))
            conn.commit()

        log.info(f"[StrategyEngine] Generated brief '{brief_id}' (Mode: {rationale_mode}, Confidence: {confidence}) for topic '{topic_clean}'")
        return self.get_brief(brief_id)

    def get_brief(self, brief_id: str) -> Optional[Dict[str, Any]]:
        self._ensure_db()
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM creative_strategy_briefs WHERE brief_id = ?", (brief_id,))
            row = cursor.fetchone()
            if not row:
                return None

            d = dict(row)
            try:
                d["recommended_parameters"] = json.loads(d.pop("recommended_parameters_json", "{}"))
            except Exception:
                d["recommended_parameters"] = {}

            try:
                d["recommended_genome"] = json.loads(d.pop("recommended_genome_json", "{}"))
            except Exception:
                d["recommended_genome"] = {}

            try:
                d["evidence_patterns"] = json.loads(d.pop("evidence_patterns_json", "[]"))
            except Exception:
                d["evidence_patterns"] = []

            return d

    def list_briefs(self, limit: int = 50, status: Optional[str] = None) -> List[Dict[str, Any]]:
        self._ensure_db()
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            if status:
                cursor.execute(
                    "SELECT brief_id FROM creative_strategy_briefs WHERE status = ? ORDER BY created_at DESC LIMIT ?",
                    (status.upper(), limit)
                )
            else:
                cursor.execute(
                    "SELECT brief_id FROM creative_strategy_briefs ORDER BY created_at DESC LIMIT ?",
                    (limit,)
                )
            ids = [r["brief_id"] for r in cursor.fetchall()]

        return [self.get_brief(b_id) for b_id in ids if b_id]

    def accept_brief(self, brief_id: str) -> Dict[str, Any]:
        """Transitions a brief from PROPOSED to ACCEPTED."""
        brief = self.get_brief(brief_id)
        if not brief:
            raise StrategyError(f"Brief '{brief_id}' not found.", error_code="BRIEF_NOT_FOUND")

        if brief["status"] in TERMINAL_BRIEF_STATES:
            raise StrategyError(f"Cannot accept brief in terminal state '{brief['status']}'.", error_code="BRIEF_TERMINAL_STATE")

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE creative_strategy_briefs SET status = 'ACCEPTED' WHERE brief_id = ?", (brief_id,))
            conn.commit()

        return self.get_brief(brief_id)

    async def execute_brief(self, brief_id: str) -> Dict[str, Any]:
        """
        Executes an approved or proposed creative brief via Phase 14 public CreativeEngine interface.
        Transitions brief to DISPATCHED and attaches the resulting job_id.
        """
        brief = self.get_brief(brief_id)
        if not brief:
            raise StrategyError(f"Brief '{brief_id}' not found.", error_code="BRIEF_NOT_FOUND")

        if brief["status"] == "DISPATCHED":
            raise StrategyError(f"Brief '{brief_id}' is already DISPATCHED (immutable).", error_code="BRIEF_ALREADY_DISPATCHED")

        if brief["status"] == "REJECTED":
            raise StrategyError(f"Cannot execute a REJECTED brief.", error_code="BRIEF_REJECTED")

        template = brief["workflow_template"]
        prompt = brief["recommended_prompt"]
        neg_prompt = brief.get("recommended_negative_prompt")
        params = brief.get("recommended_parameters", {})

        try:
            res = await creative_engine.run_workflow(
                template_name_or_path=template,
                prompt=prompt,
                parameters=params,
                negative_prompt=neg_prompt
            )
        except Exception as e:
            log.error(f"[StrategyEngine] Execution dispatch failed for brief '{brief_id}': {e}")
            raise StrategyError(f"Execution failed: {e}", error_code="DISPATCH_FAILED")

        job_id = res.get("job_id")
        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE creative_strategy_briefs
                SET status = 'DISPATCHED', dispatched_job_id = ?, concluded_at = ?
                WHERE brief_id = ?
            """, (job_id, now, brief_id))
            conn.commit()

        log.info(f"[StrategyEngine] Dispatched brief '{brief_id}' -> Job '{job_id}'")
        executed = self.get_brief(brief_id)
        executed["execution_response"] = res
        return executed

    def reject_brief(self, brief_id: str, reason: str = "User rejected") -> Dict[str, Any]:
        """Rejects a brief and moves it to the terminal REJECTED state."""
        brief = self.get_brief(brief_id)
        if not brief:
            raise StrategyError(f"Brief '{brief_id}' not found.", error_code="BRIEF_NOT_FOUND")

        if brief["status"] == "DISPATCHED":
            raise StrategyError("Cannot reject an already DISPATCHED brief.", error_code="BRIEF_ALREADY_DISPATCHED")

        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE creative_strategy_briefs
                SET status = 'REJECTED', concluded_at = ?
                WHERE brief_id = ?
            """, (now, brief_id))
            conn.commit()

        log.warning(f"[StrategyEngine] Rejected brief '{brief_id}': {reason}")
        return self.get_brief(brief_id)

# Global singleton
strategy_engine = StrategyEngine()
