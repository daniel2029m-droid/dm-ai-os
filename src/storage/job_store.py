"""
JobStore — Persistent SQLite store for Creative Engine jobs in DM AI OS v1.5.1.
Tracks full job lifecycle (SUBMITTED, RUNNING, COMPLETED, FAILED, TIMEOUT, CANCELLED, LOST, RECOVERED).
"""
import sqlite3
import os
import json
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional

log = logging.getLogger("job_store")

class JobStore:
    def __init__(self, db_path: Optional[str] = None):
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
                CREATE TABLE IF NOT EXISTS creative_jobs (
                    job_id TEXT PRIMARY KEY,
                    idempotency_key TEXT,
                    status TEXT NOT NULL,
                    workflow_name TEXT NOT NULL,
                    workflow_template_sha256 TEXT,
                    workflow_effective_sha256 TEXT,
                    backend_type TEXT,
                    provider TEXT,
                    model_checkpoint TEXT,
                    prompt TEXT,
                    negative_prompt TEXT,
                    parameters_json TEXT,
                    input_assets_json TEXT,
                    output_assets_json TEXT,
                    output_sha256 TEXT,
                    output_size_bytes INTEGER,
                    dispatch_duration_sec REAL,
                    gpu_execution_duration_sec REAL,
                    total_e2e_duration_sec REAL,
                    attempt INTEGER DEFAULT 1,
                    max_retries INTEGER DEFAULT 3,
                    estimated_cost_usd REAL,
                    error_code TEXT,
                    error_message TEXT,
                    last_error TEXT,
                    recovery_count INTEGER DEFAULT 0,
                    last_poll_at TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    started_at TIMESTAMP,
                    completed_at TIMESTAMP
                );
            """)
            # Migration check for existing databases
            cursor.execute("PRAGMA table_info(creative_jobs);")
            existing_cols = {row[1] for row in cursor.fetchall()}
            for col_name, col_type in [
                ("last_error", "TEXT"),
                ("recovery_count", "INTEGER DEFAULT 0"),
                ("last_poll_at", "TIMESTAMP")
            ]:
                if col_name not in existing_cols:
                    try:
                        cursor.execute(f"ALTER TABLE creative_jobs ADD COLUMN {col_name} {col_type};")
                    except Exception:
                        pass

            cursor.execute("CREATE INDEX IF NOT EXISTS idx_creative_jobs_status ON creative_jobs(status);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_creative_jobs_idempotency ON creative_jobs(idempotency_key);")
            conn.commit()

    def create_job(self, job_data: Dict[str, Any]) -> Dict[str, Any]:
        self._ensure_db()
        params_json = json.dumps(job_data.get("parameters", {}), ensure_ascii=False)
        input_json = json.dumps(job_data.get("input_assets", []), ensure_ascii=False)
        output_json = json.dumps(job_data.get("output_assets", []), ensure_ascii=False)

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO creative_jobs (
                    job_id, idempotency_key, status, workflow_name,
                    workflow_template_sha256, workflow_effective_sha256,
                    backend_type, provider, model_checkpoint,
                    prompt, negative_prompt, parameters_json,
                    input_assets_json, output_assets_json,
                    output_sha256, output_size_bytes,
                    dispatch_duration_sec, gpu_execution_duration_sec, total_e2e_duration_sec,
                    attempt, max_retries, estimated_cost_usd,
                    error_code, error_message, last_error, recovery_count, last_poll_at,
                    created_at, started_at, completed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                job_data.get("job_id"),
                job_data.get("idempotency_key"),
                job_data.get("status", "SUBMITTED"),
                job_data.get("workflow_name", ""),
                job_data.get("workflow_template_sha256", ""),
                job_data.get("workflow_effective_sha256", ""),
                job_data.get("backend_type", "REMOTE_COMFYUI"),
                job_data.get("provider", "auto"),
                job_data.get("model_checkpoint"),
                job_data.get("prompt", ""),
                job_data.get("negative_prompt"),
                params_json,
                input_json,
                output_json,
                job_data.get("output_sha256"),
                job_data.get("output_size_bytes"),
                job_data.get("dispatch_duration_sec", 0.0),
                job_data.get("gpu_execution_duration_sec"),
                job_data.get("total_e2e_duration_sec"),
                job_data.get("attempt", 1),
                job_data.get("max_retries", 3),
                job_data.get("estimated_cost_usd"),
                job_data.get("error_code"),
                job_data.get("error_message"),
                job_data.get("last_error"),
                job_data.get("recovery_count", 0),
                job_data.get("last_poll_at"),
                job_data.get("created_at"),
                job_data.get("started_at"),
                job_data.get("completed_at")
            ))
            conn.commit()
        return job_data

    def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        self._ensure_db()
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM creative_jobs WHERE job_id = ?", (job_id,))
            row = cursor.fetchone()
            if not row:
                return None
            return self._row_to_dict(row)

    def get_job_by_idempotency_key(self, idempotency_key: str) -> Optional[Dict[str, Any]]:
        """Finds existing job record by unique idempotency hash."""
        if not idempotency_key:
            return None
        self._ensure_db()
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM creative_jobs WHERE idempotency_key = ? ORDER BY created_at DESC LIMIT 1",
                (idempotency_key,)
            )
            row = cursor.fetchone()
            if not row:
                return None
            return self._row_to_dict(row)

    def update_job(self, job_id: str, updates: Dict[str, Any]) -> bool:
        self._ensure_db()
        if not updates:
            return False

        fields = []
        values = []
        for k, v in updates.items():
            if k in ("parameters", "input_assets", "output_assets"):
                fields.append(f"{k}_json = ?")
                values.append(json.dumps(v, ensure_ascii=False))
            else:
                fields.append(f"{k} = ?")
                values.append(v)

        values.append(job_id)
        query = f"UPDATE creative_jobs SET {', '.join(fields)} WHERE job_id = ?"

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(query, tuple(values))
            conn.commit()
            return cursor.rowcount > 0

    def list_jobs(self, limit: int = 50, status: Optional[str] = None) -> List[Dict[str, Any]]:
        self._ensure_db()
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            if status:
                cursor.execute(
                    "SELECT * FROM creative_jobs WHERE status = ? ORDER BY created_at DESC LIMIT ?",
                    (status, limit)
                )
            else:
                cursor.execute(
                    "SELECT * FROM creative_jobs ORDER BY created_at DESC LIMIT ?",
                    (limit,)
                )
            return [self._row_to_dict(r) for r in cursor.fetchall()]

    def find_active_jobs(self) -> List[Dict[str, Any]]:
        self._ensure_db()
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM creative_jobs WHERE status IN ('SUBMITTED', 'RUNNING', 'LOST') ORDER BY created_at ASC"
            )
            return [self._row_to_dict(r) for r in cursor.fetchall()]

    def find_jobs_by_status(self, status: str) -> List[Dict[str, Any]]:
        return self.list_jobs(limit=1000, status=status)

    def _row_to_dict(self, row: sqlite3.Row) -> Dict[str, Any]:
        d = dict(row)
        for json_col in ("parameters_json", "input_assets_json", "output_assets_json"):
            target_key = json_col.replace("_json", "")
            raw = d.pop(json_col, None)
            try:
                d[target_key] = json.loads(raw) if raw else ([] if "assets" in target_key else {})
            except Exception:
                d[target_key] = [] if "assets" in target_key else {}
        return d

# Global singleton
job_store = JobStore()
