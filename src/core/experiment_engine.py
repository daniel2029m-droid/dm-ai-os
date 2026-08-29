"""
ExperimentEngine — Deterministic, multivariate creative experimentation for DM AI OS v1.5.1.
Coordinates hypothesis design, variant matrix generation, lineage tracking, and evidence-based statistical evaluation.
"""
import sqlite3
import os
import json
import time
import hashlib
import logging
from dataclasses import dataclass, asdict
from typing import Dict, Any, List, Optional, Set, Tuple

from ..storage.storage_layer import storage
from ..storage.content_metrics_store import content_metrics_store, ContentMetricsStore
from ..core.creative_engine import creative_engine

log = logging.getLogger("experiment_engine")

ALLOWED_VARIABLES: Set[str] = {
    "SEED",
    "PROMPT_HOOK",
    "CFG",
    "STEPS",
    "DENOISE",
    "WIDTH",
    "HEIGHT",
    "LORA_STRENGTH",
    "NEGATIVE_PROMPT"
}

VALID_EXPERIMENT_STATES: Set[str] = {
    "DRAFT",
    "RUNNING",
    "CONCLUDED",
    "ABORTED",
    "INSUFFICIENT_EVIDENCE"
}

TERMINAL_STATES: Set[str] = {
    "CONCLUDED",
    "ABORTED"
}


class ExperimentError(ValueError):
    """Raised when experiment design or state transitions violate rules."""
    def __init__(self, message: str, error_code: str = "INVALID_EXPERIMENT", details: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.error_code = error_code
        self.details = details or {}


class ExperimentEngine:
    """
    Manages controlled multivariate creative experiments without modifying execution layers.
    """

    def __init__(
        self,
        db_path: Optional[str] = None,
        metrics_store: Optional[ContentMetricsStore] = None
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
        self.metrics_store = metrics_store or ContentMetricsStore(db_path=self.db_path)
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
                CREATE TABLE IF NOT EXISTS creative_experiments (
                    experiment_id TEXT PRIMARY KEY,
                    idempotency_hash TEXT UNIQUE,
                    name TEXT NOT NULL,
                    hypothesis TEXT,
                    base_template TEXT NOT NULL,
                    base_prompt TEXT NOT NULL,
                    variable_tested TEXT NOT NULL,
                    control_value_json TEXT NOT NULL,
                    fixed_parameters_json TEXT,
                    status TEXT NOT NULL DEFAULT 'DRAFT',
                    winning_variant_id TEXT,
                    winning_job_id TEXT,
                    evaluation_summary_json TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    concluded_at TIMESTAMP
                );
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS creative_experiment_variants (
                    variant_id TEXT PRIMARY KEY,
                    experiment_id TEXT NOT NULL,
                    variant_name TEXT NOT NULL,
                    variable_value_json TEXT NOT NULL,
                    prompt TEXT NOT NULL,
                    parameters_json TEXT NOT NULL,
                    seed INTEGER,
                    job_id TEXT,
                    is_control INTEGER DEFAULT 0,
                    status TEXT NOT NULL DEFAULT 'PENDING',
                    avg_performance_score REAL,
                    sample_count INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (experiment_id) REFERENCES creative_experiments(experiment_id)
                );
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_creative_experiments_status ON creative_experiments(status);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_creative_experiment_variants_exp ON creative_experiment_variants(experiment_id);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_creative_experiment_variants_job ON creative_experiment_variants(job_id);")
            conn.commit()

    def _compute_experiment_hash(
        self,
        base_template: str,
        base_prompt: str,
        variable_tested: str,
        control_value: Any,
        variant_values: List[Any],
        fixed_parameters: Optional[Dict[str, Any]] = None
    ) -> str:
        payload = {
            "template": base_template.strip(),
            "prompt": base_prompt.strip(),
            "variable": variable_tested.strip().upper(),
            "control": control_value,
            "variants": sorted([json.dumps(v, sort_keys=True) if isinstance(v, (dict, list)) else str(v) for v in variant_values]),
            "fixed_params": fixed_parameters or {}
        }
        canonical_json = json.dumps(payload, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()

    def create_experiment(
        self,
        name: str,
        base_template: str,
        base_prompt: str,
        variable_tested: str,
        control_value: Any,
        variant_values: List[Any],
        hypothesis: Optional[str] = None,
        fixed_parameters: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Creates a new controlled multivariate experiment.
        Ensures strict variable validation, deterministic matrix generation, and idempotent registration.
        """
        self._ensure_db()

        if not name or not isinstance(name, str) or not name.strip():
            raise ExperimentError("Experiment name must be a non-empty string.", error_code="INVALID_EXPERIMENT_NAME")

        if not base_template or not isinstance(base_template, str) or not base_template.strip():
            raise ExperimentError("Base template must be specified.", error_code="INVALID_BASE_TEMPLATE")

        if not base_prompt or not isinstance(base_prompt, str) or not base_prompt.strip():
            raise ExperimentError("Base prompt must be specified.", error_code="INVALID_BASE_PROMPT")

        var_upper = variable_tested.strip().upper()
        if var_upper not in ALLOWED_VARIABLES:
            raise ExperimentError(
                f"Variable '{variable_tested}' is not supported. Allowed: {sorted(list(ALLOWED_VARIABLES))}",
                error_code="INVALID_EXPERIMENT_VARIABLE",
                details={"variable": variable_tested, "allowed": list(ALLOWED_VARIABLES)}
            )

        if not variant_values or not isinstance(variant_values, list):
            raise ExperimentError("Variant values list cannot be empty.", error_code="EMPTY_VARIANTS")

        idemp_hash = self._compute_experiment_hash(
            base_template=base_template,
            base_prompt=base_prompt,
            variable_tested=var_upper,
            control_value=control_value,
            variant_values=variant_values,
            fixed_parameters=fixed_parameters
        )

        # Check existing idempotency
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM creative_experiments WHERE idempotency_hash = ?", (idemp_hash,))
            existing = cursor.fetchone()
            if existing:
                log.info(f"[ExperimentEngine] Idempotent hit: experiment already exists ({existing['experiment_id']})")
                return self.get_experiment(existing["experiment_id"])

        import uuid
        exp_id = f"exp_{uuid.uuid4().hex[:12]}"
        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        fixed_params = fixed_parameters or {}

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO creative_experiments (
                    experiment_id, idempotency_hash, name, hypothesis, base_template,
                    base_prompt, variable_tested, control_value_json, fixed_parameters_json,
                    status, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'DRAFT', ?)
            """, (
                exp_id,
                idemp_hash,
                name.strip(),
                hypothesis or "",
                base_template.strip(),
                base_prompt.strip(),
                var_upper,
                json.dumps(control_value, ensure_ascii=False),
                json.dumps(fixed_params, ensure_ascii=False),
                now
            ))

            # Build variant matrix
            # 1. Control Variant
            self._insert_variant(
                cursor=cursor,
                experiment_id=exp_id,
                variant_name="Control",
                variable_tested=var_upper,
                variable_value=control_value,
                base_prompt=base_prompt,
                fixed_params=fixed_params,
                is_control=1,
                created_at=now
            )

            # 2. Candidate Variants
            for idx, val in enumerate(variant_values):
                self._insert_variant(
                    cursor=cursor,
                    experiment_id=exp_id,
                    variant_name=f"Variant_{chr(65 + idx)}", # Variant_A, Variant_B, ...
                    variable_tested=var_upper,
                    variable_value=val,
                    base_prompt=base_prompt,
                    fixed_params=fixed_params,
                    is_control=0,
                    created_at=now
                )

            conn.commit()

        log.info(f"[ExperimentEngine] Created experiment '{name}' ({exp_id}) with {len(variant_values) + 1} variants.")
        return self.get_experiment(exp_id)

    def _insert_variant(
        self,
        cursor: sqlite3.Cursor,
        experiment_id: str,
        variant_name: str,
        variable_tested: str,
        variable_value: Any,
        base_prompt: str,
        fixed_params: Dict[str, Any],
        is_control: int,
        created_at: str
    ):
        import uuid
        variant_id = f"var_{uuid.uuid4().hex[:12]}"
        effective_params = dict(fixed_params)
        prompt = base_prompt
        seed = effective_params.get("seed")

        if variable_tested == "PROMPT_HOOK":
            prompt = f"{variable_value} {base_prompt}" if base_prompt else str(variable_value)
        elif variable_tested == "SEED":
            seed = int(variable_value)
            effective_params["seed"] = seed
        elif variable_tested == "NEGATIVE_PROMPT":
            effective_params["negative_prompt"] = str(variable_value)
        else:
            param_key = variable_tested.lower()
            effective_params[param_key] = variable_value

        cursor.execute("""
            INSERT INTO creative_experiment_variants (
                variant_id, experiment_id, variant_name, variable_value_json, prompt,
                parameters_json, seed, is_control, status, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'PENDING', ?)
        """, (
            variant_id,
            experiment_id,
            variant_name,
            json.dumps(variable_value, ensure_ascii=False),
            prompt,
            json.dumps(effective_params, ensure_ascii=False),
            seed,
            is_control,
            created_at
        ))

    def get_experiment(self, experiment_id: str) -> Optional[Dict[str, Any]]:
        self._ensure_db()
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM creative_experiments WHERE experiment_id = ?", (experiment_id,))
            exp_row = cursor.fetchone()
            if not exp_row:
                return None

            exp = dict(exp_row)
            try:
                exp["control_value"] = json.loads(exp.pop("control_value_json", "null"))
            except Exception:
                exp["control_value"] = None

            try:
                exp["fixed_parameters"] = json.loads(exp.pop("fixed_parameters_json", "{}"))
            except Exception:
                exp["fixed_parameters"] = {}

            try:
                exp["evaluation_summary"] = json.loads(exp.pop("evaluation_summary_json", "null"))
            except Exception:
                exp["evaluation_summary"] = None

            cursor.execute("SELECT * FROM creative_experiment_variants WHERE experiment_id = ? ORDER BY is_control DESC, variant_name ASC", (experiment_id,))
            variants = []
            for r in cursor.fetchall():
                v = dict(r)
                try:
                    v["variable_value"] = json.loads(v.pop("variable_value_json", "null"))
                    v["parameters"] = json.loads(v.pop("parameters_json", "{}"))
                except Exception:
                    pass
                variants.append(v)

            exp["variants"] = variants
            return exp

    def list_experiments(self, limit: int = 50, status: Optional[str] = None) -> List[Dict[str, Any]]:
        self._ensure_db()
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            if status:
                cursor.execute(
                    "SELECT experiment_id FROM creative_experiments WHERE status = ? ORDER BY created_at DESC LIMIT ?",
                    (status.upper(), limit)
                )
            else:
                cursor.execute(
                    "SELECT experiment_id FROM creative_experiments ORDER BY created_at DESC LIMIT ?",
                    (limit,)
                )
            ids = [r["experiment_id"] for r in cursor.fetchall()]

        return [self.get_experiment(e_id) for e_id in ids if e_id]

    async def run_experiment(self, experiment_id: str) -> Dict[str, Any]:
        """
        Executes all pending variants of an experiment via the public CreativeEngine interface.
        """
        exp = self.get_experiment(experiment_id)
        if not exp:
            raise ExperimentError(f"Experiment '{experiment_id}' not found.", error_code="EXPERIMENT_NOT_FOUND")

        if exp["status"] in TERMINAL_STATES:
            raise ExperimentError(
                f"Cannot run experiment in terminal state '{exp['status']}'.",
                error_code="EXPERIMENT_TERMINAL_STATE"
            )

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE creative_experiments SET status = 'RUNNING' WHERE experiment_id = ?", (experiment_id,))
            conn.commit()

        base_template = exp["base_template"]
        dispatched_count = 0
        failed_count = 0

        for variant in exp.get("variants", []):
            if variant["status"] != "PENDING":
                continue

            v_id = variant["variant_id"]
            prompt = variant["prompt"]
            params = variant["parameters"]
            seed = variant.get("seed")

            try:
                res = await creative_engine.run_workflow(
                    template_name_or_path=base_template,
                    prompt=prompt,
                    parameters=params,
                    seed=seed
                )
                job_id = res.get("job_id")
                v_status = "DISPATCHED" if res.get("status") in ("SUBMITTED", "COMPLETED", "RUNNING") else "FAILED"
                dispatched_count += 1
            except Exception as e:
                log.error(f"[ExperimentEngine] Variant '{v_id}' dispatch failed: {e}")
                job_id = None
                v_status = "FAILED"
                failed_count += 1

            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE creative_experiment_variants
                    SET job_id = ?, status = ?
                    WHERE variant_id = ?
                """, (job_id, v_status, v_id))
                conn.commit()

        log.info(f"[ExperimentEngine] Dispatched experiment '{experiment_id}' ({dispatched_count} dispatched, {failed_count} failed)")
        return self.get_experiment(experiment_id)

    def evaluate_experiment(
        self,
        experiment_id: str,
        minimum_variant_samples: int = 3,
        minimum_lift: float = 0.05
    ) -> Dict[str, Any]:
        """
        Evaluates performance telemetry across experiment variants and detects winners under statistical evidence constraints.
        """
        exp = self.get_experiment(experiment_id)
        if not exp:
            raise ExperimentError(f"Experiment '{experiment_id}' not found.", error_code="EXPERIMENT_NOT_FOUND")

        if exp["status"] in TERMINAL_STATES:
            return exp

        variants = exp.get("variants", [])
        control_variant = next((v for v in variants if v.get("is_control") == 1), None)
        candidate_variants = [v for v in variants if v.get("is_control") == 0]

        # Update metrics for each variant from content_metrics_store
        variant_evals = []
        for v in variants:
            j_id = v.get("job_id")
            metrics = self.metrics_store.get_metrics_by_job(j_id) if j_id else []
            valid_scores = [m["performance_score"] for m in metrics if m.get("performance_score") is not None]
            sample_count = len(valid_scores)
            avg_score = round(sum(valid_scores) / sample_count, 2) if sample_count > 0 else 0.0

            # Update database row
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE creative_experiment_variants
                    SET avg_performance_score = ?, sample_count = ?
                    WHERE variant_id = ?
                """, (avg_score, sample_count, v["variant_id"]))
                conn.commit()

            variant_evals.append({
                "variant_id": v["variant_id"],
                "variant_name": v["variant_name"],
                "job_id": j_id,
                "is_control": bool(v.get("is_control")),
                "sample_count": sample_count,
                "avg_performance_score": avg_score,
                "has_sufficient_evidence": (sample_count >= minimum_variant_samples)
            })

        control_eval = next((ve for ve in variant_evals if ve["is_control"]), None)
        control_score = control_eval["avg_performance_score"] if control_eval else 0.0
        control_samples = control_eval["sample_count"] if control_eval else 0

        # Check evidence threshold
        if not control_eval or control_samples < minimum_variant_samples:
            status = "INSUFFICIENT_EVIDENCE"
            decision_reason = f"Control variant has insufficient samples ({control_samples} < {minimum_variant_samples})."
            winning_v_id = None
            winning_j_id = None
        else:
            # Check candidate variants
            sufficient_candidates = [ce for ce in variant_evals if not ce["is_control"] and ce["sample_count"] >= minimum_variant_samples]
            if not sufficient_candidates:
                status = "INSUFFICIENT_EVIDENCE"
                decision_reason = "No candidate variant has accumulated the minimum required sample size."
                winning_v_id = None
                winning_j_id = None
            else:
                # Rank candidates by score
                sorted_candidates = sorted(sufficient_candidates, key=lambda x: x["avg_performance_score"], reverse=True)
                top_candidate = sorted_candidates[0]
                lift = round(top_candidate["avg_performance_score"] - control_score, 2)

                if lift >= minimum_lift:
                    # Check if top candidate strictly beats second candidate (if exists)
                    if len(sorted_candidates) > 1 and (top_candidate["avg_performance_score"] - sorted_candidates[1]["avg_performance_score"] < minimum_lift):
                        status = "INSUFFICIENT_EVIDENCE"
                        decision_reason = f"Top candidate {top_candidate['variant_name']} leads but margin over second candidate is below threshold ({minimum_lift})."
                        winning_v_id = None
                        winning_j_id = None
                    else:
                        status = "CONCLUDED"
                        decision_reason = f"Variant {top_candidate['variant_name']} outperformed control by +{lift} points with sufficient evidence."
                        winning_v_id = top_candidate["variant_id"]
                        winning_j_id = top_candidate["job_id"]
                else:
                    status = "CONCLUDED"
                    decision_reason = f"No variant outperformed control by required minimum lift ({minimum_lift}). Control maintained."
                    winning_v_id = control_eval["variant_id"]
                    winning_j_id = control_eval["job_id"]

        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        summary = {
            "evaluation_timestamp": now,
            "decision_reason": decision_reason,
            "control_score": control_score,
            "control_samples": control_samples,
            "variant_evaluations": variant_evals
        }

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE creative_experiments
                SET status = ?, winning_variant_id = ?, winning_job_id = ?,
                    evaluation_summary_json = ?, concluded_at = ?
                WHERE experiment_id = ?
            """, (status, winning_v_id, winning_j_id, json.dumps(summary, ensure_ascii=False), now, experiment_id))
            conn.commit()

        log.info(f"[ExperimentEngine] Evaluated experiment '{experiment_id}': status={status}, winner={winning_v_id}")
        return self.get_experiment(experiment_id)

    def abort_experiment(self, experiment_id: str, reason: str = "User aborted") -> Dict[str, Any]:
        """Aborts an active experiment and transitions it to the terminal ABORTED state."""
        exp = self.get_experiment(experiment_id)
        if not exp:
            raise ExperimentError(f"Experiment '{experiment_id}' not found.", error_code="EXPERIMENT_NOT_FOUND")

        if exp["status"] == "CONCLUDED":
            raise ExperimentError("Cannot abort an already CONCLUDED experiment.", error_code="EXPERIMENT_ALREADY_CONCLUDED")

        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        summary = {
            "aborted_at": now,
            "abort_reason": reason
        }

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE creative_experiments
                SET status = 'ABORTED', evaluation_summary_json = ?, concluded_at = ?
                WHERE experiment_id = ?
            """, (json.dumps(summary, ensure_ascii=False), now, experiment_id))
            conn.commit()

        log.warning(f"[ExperimentEngine] Aborted experiment '{experiment_id}': {reason}")
        return self.get_experiment(experiment_id)

# Global singleton
experiment_engine = ExperimentEngine()
